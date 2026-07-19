import gzip
import io

from tring_ingest.common.bq_loader import load_json_rows_to_raw, load_tsv_stream_to_raw
from tring_ingest.common.config import APPSTORE_APP_ID, BQ_DATASET_RAW_APPSTORE, GCP_PROJECT
from tring_ingest.common.logging import get_logger
from tring_ingest.sources.app_store import endpoints as ep
from tring_ingest.sources.app_store.client import AppStoreClient

logger = get_logger(__name__)


def _pull_reviews(client: AppStoreClient, date_from: str) -> list[dict]:
    # incremental: apple returns newest-first, stop when createdDate < date_from
    url = f"{ep.BASE}/v1/apps/{APPSTORE_APP_ID}/customerReviews"
    params: dict = {"limit": ep.REVIEWS_PAGE_SIZE, "sort": "-createdDate"}
    out: list[dict] = []
    while url:
        data = client.get(url, params=params).json()
        for r in data.get("data", []):
            created = r.get("attributes", {}).get("createdDate", "")
            if created[:10] < date_from:
                logger.info(f"reached date_from={date_from}, stopping pagination")
                return out
            out.append(ep.flatten_review(r))
        url = data.get("links", {}).get("next")
        params = {}
    return out


def _resolve_report_ids(client: AppStoreClient, request_id: str) -> dict:
    # map exact report name -> (report_id, table) by paging all reports for the ongoing request
    wanted = {r["name"]: r["table"] for r in ep.ANALYTICS_REPORTS}
    found: dict = {}
    url = f"{ep.BASE}/v1/analyticsReportRequests/{request_id}/reports?limit=200"
    while url:
        data = client.get(url).json()
        for rep in data.get("data", []):
            name = rep["attributes"]["name"]
            if name in wanted:
                found[name] = (rep["id"], wanted[name])
        url = data.get("links", {}).get("next")
    return found  # {name: (report_id, table)}


def _stream_analytics_report(
    client: AppStoreClient,
    report_id: str,
    table: str,
    source: str,
    date_from: str,
    date_to: str,
) -> int:
    # stream per-segment directly to BQ -- re-fetch segment URL just before download
    # (signed S3 URLs expire in 5 min; re-fetching gives a fresh URL each time)
    total = 0
    url = f"{ep.BASE}/v1/analyticsReports/{report_id}/instances?limit=200"
    while url:
        data = client.get(url).json()
        for inst in data.get("data", []):
            seg_list_url = f"{ep.BASE}/v1/analyticsReportInstances/{inst['id']}/segments"
            seg_ids = [s["id"] for s in client.get(seg_list_url).json().get("data", [])]
            for seg_id in seg_ids:
                # re-fetch this single segment to get a fresh signed URL
                fresh = client.get(f"{ep.BASE}/v1/analyticsReportSegments/{seg_id}").json()
                dl_url = fresh.get("data", {}).get("attributes", {}).get("url")
                if not dl_url:
                    continue
                raw = client.get_unsigned(dl_url).content
                with gzip.open(io.BytesIO(raw)) as f:
                    text = f.read().decode("utf-8")
                n = load_tsv_stream_to_raw(
                    tsv_text=text,
                    dataset_id=BQ_DATASET_RAW_APPSTORE,
                    table_id=table,
                    source=source,
                    date_from=date_from,
                    date_to=date_to,
                    project_id=GCP_PROJECT,
                )
                del text
                if n:
                    total += n
                    logger.info(f"loaded {n} rows to {table} (seg {seg_id[:8]})")
        url = data.get("links", {}).get("next")
    return total


def _pull_analytics_report(client: AppStoreClient, report_id: str) -> list[dict]:
    # kept for normal run() which still collects all rows (daily window is small)
    rows: list[dict] = []
    url = f"{ep.BASE}/v1/analyticsReports/{report_id}/instances?limit=200"
    while url:
        data = client.get(url).json()
        for inst in data.get("data", []):
            seg_url = f"{ep.BASE}/v1/analyticsReportInstances/{inst['id']}/segments"
            segs = client.get(seg_url).json().get("data", [])
            for seg in segs:
                dl_url = seg["attributes"].get("url")
                if not dl_url:
                    continue
                raw = client.get_unsigned(dl_url).content
                with gzip.open(io.BytesIO(raw)) as f:
                    text = f.read().decode("utf-8")
                rows.extend(ep.flatten_tsv(text))
        url = data.get("links", {}).get("next")
    return rows


def run_snapshot(creds: str | None = None) -> None:
    """Backfill from ONE_TIME_SNAPSHOT request (Nov 2024 - Jun 2026 historical data). Run once."""
    client = AppStoreClient(creds=creds)
    errors: list[str] = []
    total = 0

    try:
        report_map = _resolve_report_ids(client, ep.SNAPSHOT_REQUEST_ID)
    except Exception as exc:
        logger.error(f"snapshot resolve report ids failed: {exc}")
        raise

    for name, (report_id, table) in report_map.items():
        try:
            n = _stream_analytics_report(
                client=client,
                report_id=report_id,
                table=table,
                source="app_store_snapshot",
                date_from="2024-11-01",
                date_to="2026-06-26",
            )
            total += n
            logger.info(f"snapshot {name}: {n} rows -> {table}")
        except Exception as exc:
            logger.error(f"snapshot {name} failed: {exc}")
            errors.append(table)

    if errors:
        raise RuntimeError(f"Snapshot extract failed for: {errors}")
    logger.info(f"Snapshot extract complete: {total} total rows")


def run(date_from: str, date_to: str, creds: str | None = None) -> None:
    client = AppStoreClient(creds=creds)
    errors: list[str] = []
    total = 0

    # reviews (incremental by date_from)
    try:
        reviews = _pull_reviews(client, date_from=date_from)
        if reviews:
            load_json_rows_to_raw(
                rows=reviews,
                dataset_id=BQ_DATASET_RAW_APPSTORE,
                table_id="raw_reviews",
                source="app_store",
                date_from=date_from,
                date_to=date_to,
                project_id=GCP_PROJECT,
            )
            total += len(reviews)
        logger.info(f"reviews: {len(reviews)} rows")
    except Exception as exc:
        logger.error(f"reviews failed: {exc}")
        errors.append("reviews")

    # analytics -- all 5 reports, all available instances each run; stateless, dbt staging dedups
    try:
        report_map = _resolve_report_ids(client, ep.ONGOING_REQUEST_ID)
    except Exception as exc:
        logger.error(f"resolve report ids failed: {exc}")
        report_map = {}
        errors.append("analytics_resolve")

    for name, (report_id, table) in report_map.items():
        try:
            rows = _pull_analytics_report(client, report_id)
            if rows:
                load_json_rows_to_raw(
                    rows=rows,
                    dataset_id=BQ_DATASET_RAW_APPSTORE,
                    table_id=table,
                    source="app_store",
                    date_from=date_from,
                    date_to=date_to,
                    project_id=GCP_PROJECT,
                )
                total += len(rows)
            logger.info(f"{name}: {len(rows)} rows -> {table}")
        except Exception as exc:
            logger.error(f"{name} failed: {exc}")
            errors.append(table)

    if errors:
        raise RuntimeError(f"Extract failed for: {errors}")
    logger.info(f"Extract complete: {total} total rows")
