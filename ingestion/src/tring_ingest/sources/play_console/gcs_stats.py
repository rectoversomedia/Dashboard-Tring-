import csv
import io
from datetime import date, timedelta

from google.cloud import storage
from google.oauth2 import service_account

from tring_ingest.common.bq_loader import load_json_rows_to_raw
from tring_ingest.common.config import (
    BQ_DATASET_RAW_PLAY_CONSOLE,
    GCP_PROJECT,
    GCS_BUCKET_PLAY_CONSOLE,
    PLAY_CONSOLE_PACKAGE_NAME,
)
from tring_ingest.common.logging import get_logger

logger = get_logger(__name__)

_GCS_SCOPES = ["https://www.googleapis.com/auth/devstorage.read_only"]

# (gcs_prefix, file_suffix, bq_table)
_REPORT_TARGETS = [
    ("stats/installs", "overview", "raw_gcs_installs"),
    ("stats/crashes", "overview", "raw_gcs_crashes"),
    ("stats/store_performance", "country", "raw_gcs_store_performance_country"),
    ("stats/store_performance", "traffic_source", "raw_gcs_store_performance_traffic"),
]


def _make_gcs_client(sa_key_json: str | None = None) -> storage.Client:
    # GCS uses ADC (the Cloud Run job's SA identity) — not the play-console SA key,
    # which is for the Play Developer Reporting API only.
    if sa_key_json:
        import json

        key_data = json.loads(sa_key_json)
        creds = service_account.Credentials.from_service_account_info(key_data, scopes=_GCS_SCOPES)
        return storage.Client(credentials=creds, project=GCP_PROJECT)
    return storage.Client(project=GCP_PROJECT)


def _list_blobs_for_months(
    bucket: storage.Bucket, prefix: str, suffix: str, months: list[str]
) -> list[storage.Blob]:
    """Return blobs matching package + suffix for given YYYYMM list."""
    blobs = []
    for ym in months:
        # e.g. stats/installs/installs_co.id.pegadaian.aralia_202606_overview.csv
        report_type = prefix.split("/")[-1]
        blob_name = f"{prefix}/{report_type}_{PLAY_CONSOLE_PACKAGE_NAME}_{ym}_{suffix}.csv"
        blob = bucket.blob(blob_name)
        if blob.exists():
            blobs.append(blob)
        else:
            logger.warning(f"blob not found: {blob_name}")
    return blobs


def _months_in_range(date_from: str, date_to: str) -> list[str]:
    """Return list of YYYYMM strings covering date_from..date_to (inclusive)."""
    start = date.fromisoformat(date_from).replace(day=1)
    end = date.fromisoformat(date_to).replace(day=1)
    months = []
    cur = start
    while cur <= end:
        months.append(cur.strftime("%Y%m"))
        # advance to next month
        cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
    return months


def _parse_csv_blob(blob: storage.Blob) -> list[dict]:
    """Download blob, parse CSV, return list of dicts (all values as strings)."""
    raw_bytes = blob.download_as_bytes()
    # GCS stats files are UTF-16 LE with BOM; fall back to UTF-8 for any future format changes
    if raw_bytes[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw_bytes.decode("utf-16")
    else:
        text = raw_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    return [dict(row) for row in reader]


def _snake(col: str) -> str:
    return col.strip().lower().replace(" ", "_").replace("/", "_").replace("-", "_")


def _normalize_rows(rows: list[dict], blob_name: str) -> list[dict]:
    """Normalize column names to snake_case, filter to target package only."""
    out = []
    for row in rows:
        normed = {_snake(k): v for k, v in row.items()}
        pkg_val = normed.get("package_name") or normed.get("package name", "")
        if pkg_val != PLAY_CONSOLE_PACKAGE_NAME:
            continue
        normed["_gcs_blob"] = blob_name
        out.append(normed)
    return out


def run_gcs_stats(date_from: str, date_to: str, sa_key_json: str | None = None) -> None:
    client = _make_gcs_client(sa_key_json)
    bucket = client.bucket(GCS_BUCKET_PLAY_CONSOLE)
    months = _months_in_range(date_from, date_to)

    errors = []
    total_rows = 0

    for prefix, suffix, table in _REPORT_TARGETS:
        blobs = _list_blobs_for_months(bucket, prefix, suffix, months)
        rows = []
        for blob in blobs:
            parsed = _parse_csv_blob(blob)
            rows.extend(_normalize_rows(parsed, blob.name))

        if not rows:
            logger.info(f"{table}: 0 rows (no blobs or no matching package)")
            continue

        # filter to date range
        rows = [r for r in rows if date_from <= r.get("date", "") <= date_to]

        if rows:
            load_json_rows_to_raw(
                rows=rows,
                dataset_id=BQ_DATASET_RAW_PLAY_CONSOLE,
                table_id=table,
                source="play_console_gcs",
                date_from=date_from,
                date_to=date_to,
                project_id=GCP_PROJECT,
            )
            total_rows += len(rows)

        logger.info(f"{table}: {len(rows)} rows from {len(blobs)} blob(s)")

    if errors:
        raise RuntimeError(f"GCS stats extract failed for: {errors}")

    logger.info(f"GCS stats complete: {total_rows} total rows")
