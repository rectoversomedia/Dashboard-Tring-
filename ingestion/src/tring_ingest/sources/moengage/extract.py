import uuid

from tring_ingest.common.bq_loader import load_json_rows_to_raw
from tring_ingest.common.config import (
    BQ_DATASET_RAW_MOENGAGE,
    GCP_PROJECT,
    MOENGAGE_ATTRIBUTION_TYPE,
    MOENGAGE_METRIC_TYPE,
)
from tring_ingest.common.logging import get_logger
from tring_ingest.sources.moengage.client import MoEngageClient
from tring_ingest.sources.moengage.endpoints import (
    SEARCH_PATH,
    STATS_PATH,
    SearchPayload,
    build_stats_chunks,
)

logger = get_logger(__name__)


def _search_all_campaigns(client: MoEngageClient) -> list[dict]:
    """Paginate /campaigns/search, return flat list of campaign dicts."""
    campaigns = []
    page = 1
    while True:
        payload = SearchPayload(page=page).to_dict(
            request_id=f"tring-search-{uuid.uuid4().hex[:8]}"
        )
        resp = client.post(SEARCH_PATH, payload)
        batch = resp.json()
        if not isinstance(batch, list):
            logger.warning(f"unexpected search response type {type(batch).__name__}: {batch}")
            break
        if not batch:
            break
        campaigns.extend(batch)
        if len(batch) < payload["limit"]:
            break
        page += 1
    logger.info(f"campaign search: {len(campaigns)} campaigns found")
    return campaigns


def _flatten_stats(campaign_id: str, stats_data: dict) -> list[dict]:
    """Flatten nested platforms->locales->variations into one row per platform."""
    rows = []
    platforms = stats_data.get("platforms", {})
    for platform, locale_data in platforms.items():
        for locale, variation_data in locale_data.get("locales", {}).items():
            for variation, metrics in variation_data.get("variations", {}).items():
                row = {
                    "campaign_id": campaign_id,
                    "platform": platform,
                    "locale": locale,
                    "variation": variation,
                }
                row.update(metrics.get("performance_stats", {}))
                row["delivery_funnel"] = str(metrics.get("delivery_funnel", {}))
                row["conversion_goal_stats"] = str(metrics.get("conversion_goal_stats", {}))
                rows.append(row)
    return rows


def run(date_from: str, date_to: str, creds: str | None = None) -> None:
    client = MoEngageClient(creds=creds)

    # step 1: collect campaigns and load raw_campaigns
    campaigns = _search_all_campaigns(client)
    if campaigns:
        load_json_rows_to_raw(
            rows=campaigns,
            dataset_id=BQ_DATASET_RAW_MOENGAGE,
            table_id="raw_campaigns",
            source="moengage",
            date_from=date_from,
            date_to=date_to,
            project_id=GCP_PROJECT,
        )

    campaign_ids = [c["campaign_id"] for c in campaigns if "campaign_id" in c]
    if not campaign_ids:
        logger.warning("no campaign_ids found; skipping stats pull")
        return

    # step 2: pull stats in <=30-day chunks, collect failures
    chunks = build_stats_chunks(
        campaign_ids=campaign_ids,
        date_from=date_from,
        date_to=date_to,
        attribution_type=MOENGAGE_ATTRIBUTION_TYPE,
        metric_type=MOENGAGE_METRIC_TYPE,
    )

    errors = []
    total_stats_rows = 0

    for chunk in chunks:
        chunk_start = chunk["start_date"]
        chunk_end = chunk["end_date"]
        payload = {**chunk, "request_id": f"tring-stats-{uuid.uuid4().hex[:8]}"}
        try:
            resp = client.post(STATS_PATH, payload)
            data = resp.json().get("data", {})
            flat_rows = []
            for campaign_id, stat_list in data.items():
                for stat_entry in stat_list if isinstance(stat_list, list) else [stat_list]:
                    flat_rows.extend(_flatten_stats(campaign_id, stat_entry))
            if flat_rows:
                load_json_rows_to_raw(
                    rows=flat_rows,
                    dataset_id=BQ_DATASET_RAW_MOENGAGE,
                    table_id="raw_campaign_stats",
                    source="moengage",
                    date_from=chunk_start,
                    date_to=chunk_end,
                    project_id=GCP_PROJECT,
                )
                total_stats_rows += len(flat_rows)
            logger.info(
                f"stats chunk {chunk_start}..{chunk_end}: {len(flat_rows)} rows",
                extra={"chunk_start": chunk_start, "chunk_end": chunk_end, "rows": len(flat_rows)},
            )
        except Exception as exc:
            logger.error(
                f"stats chunk {chunk_start}..{chunk_end} failed: {exc}",
                extra={"chunk_start": chunk_start, "chunk_end": chunk_end, "error": str(exc)},
            )
            errors.append((chunk_start, chunk_end))

    if errors:
        raise RuntimeError(f"Extract failed for {len(errors)} stats chunk(s): {errors}")

    logger.info(
        f"Extract complete: {len(campaigns)} campaigns, {total_stats_rows} stats rows, "
        f"{len(chunks)} chunk(s)",
    )
