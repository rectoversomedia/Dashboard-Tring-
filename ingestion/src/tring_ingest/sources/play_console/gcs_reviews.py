"""Ingest Play Console review exports from GCS.

Unlike the reviews.list API (~7-day window, comment-bearing reviews only), these
monthly CSVs include rating-only reviews -- roughly 55% of all ratings -- and carry
the real submit timestamp instead of only lastModified.

File layout: reviews/reviews_<package>_<YYYYMM>.csv, UTF-16 LE with BOM.
"""

from datetime import date, timedelta

from tring_ingest.common.bq_loader import load_json_rows_to_raw
from tring_ingest.common.config import (
    BQ_DATASET_RAW_PLAY_CONSOLE,
    GCP_PROJECT,
    GCS_BUCKET_PLAY_CONSOLE,
    PLAY_CONSOLE_PACKAGE_NAME,
)
from tring_ingest.common.logging import get_logger
from tring_ingest.sources.play_console.gcs_stats import (
    _make_gcs_client,
    _months_in_range,
    _parse_csv_blob,
    _snake,
)

logger = get_logger(__name__)

_GCS_PREFIX = "reviews"
_BQ_TABLE = "raw_gcs_reviews"

# Months past date_to to scan for late-updated reviews. Two covers a reply that
# lands a month or so after the review; beyond that the tail is negligible.
_LOOKAHEAD_MONTHS = 2


def _normalize_review_rows(rows: list[dict], blob_name: str) -> list[dict]:
    """Snake_case the columns and keep only rows for the target package."""
    out = []
    for row in rows:
        normed = {_snake(k): v for k, v in row.items()}
        if normed.get("package_name") != PLAY_CONSOLE_PACKAGE_NAME:
            continue
        normed["_gcs_blob"] = blob_name
        out.append(normed)
    return out


def _submit_date(row: dict) -> str:
    """Extract YYYY-MM-DD from 'review_submit_date_and_time' (ISO, e.g. 2026-07-01T01:49:52Z)."""
    return (row.get("review_submit_date_and_time") or "")[:10]


def _months_to_scan(date_from: str, date_to: str) -> list[str]:
    """Months whose files can hold reviews submitted in the window.

    Files are bucketed by Review Last Update, not submit date, so a review
    submitted in July but replied to in September lands in the September file.
    Scan a lookahead past date_to to catch those; a review submitted before
    date_from can never appear, so there is nothing to scan backwards for.
    """
    end = date.fromisoformat(date_to).replace(day=1)
    for _ in range(_LOOKAHEAD_MONTHS):
        end = (end.replace(day=28) + timedelta(days=4)).replace(day=1)
    return _months_in_range(date_from, end.isoformat())


def run_gcs_reviews(date_from: str, date_to: str, sa_key_json: str | None = None) -> None:
    client = _make_gcs_client(sa_key_json)
    bucket = client.bucket(GCS_BUCKET_PLAY_CONSOLE)
    months = _months_to_scan(date_from, date_to)

    # One list call beats one exists() probe per month; future months have no file yet.
    prefix = f"{_GCS_PREFIX}/{_GCS_PREFIX}_{PLAY_CONSOLE_PACKAGE_NAME}_"
    available = {b.name: b for b in bucket.list_blobs(prefix=prefix)}

    rows: list[dict] = []
    found_blobs = 0

    for ym in months:
        blob = available.get(f"{prefix}{ym}.csv")
        if blob is None:
            logger.info(f"no review file for {ym} (not generated yet)")
            continue
        found_blobs += 1
        rows.extend(_normalize_review_rows(_parse_csv_blob(blob), blob.name))

    # Each file spans a whole month and may carry reviews submitted years earlier,
    # so trim by submit date. Reviews with no submit timestamp cannot be dated.
    rows = [r for r in rows if date_from <= _submit_date(r) <= date_to]

    if not rows:
        logger.info(f"{_BQ_TABLE}: 0 rows from {found_blobs} blob(s)")
        return

    load_json_rows_to_raw(
        rows=rows,
        dataset_id=BQ_DATASET_RAW_PLAY_CONSOLE,
        table_id=_BQ_TABLE,
        source="play_console_gcs_reviews",
        date_from=date_from,
        date_to=date_to,
        project_id=GCP_PROJECT,
    )

    rating_only = sum(1 for r in rows if not (r.get("review_text") or "").strip())
    logger.info(
        f"{_BQ_TABLE}: {len(rows)} rows from {found_blobs} blob(s) "
        f"({rating_only} rating-only, {len(rows) - rating_only} with text)"
    )
