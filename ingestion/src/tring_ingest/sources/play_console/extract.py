from tring_ingest.common.bq_loader import load_json_rows_to_raw
from tring_ingest.common.config import (
    BQ_DATASET_RAW_PLAY_CONSOLE,
    GCP_PROJECT,
)
from tring_ingest.common.logging import get_logger
from tring_ingest.sources.play_console.client import PlayConsoleClient
from tring_ingest.sources.play_console.endpoints import (
    METRIC_SETS,
    ReportingQueryPayload,
    date_str_to_dict,
    flatten_reporting_row,
    flatten_review,
    reviews_url,
)

logger = get_logger(__name__)

# max reviews per page (API limit)
_REVIEWS_PAGE_SIZE = 100


def _pull_metric_set(
    client: PlayConsoleClient, ms: dict, date_from: dict, date_to: dict
) -> list[dict]:
    payload = ReportingQueryPayload(
        metric_set_name=ms["name"],
        metrics=ms["metrics"],
        dimensions=ms["dimensions"],
        date_from=date_from,
        date_to=date_to,
    )
    resp = client.post(payload.url(), payload.to_dict())
    rows = resp.json().get("rows", [])
    return [flatten_reporting_row(r, ms["name"]) for r in rows]


def _pull_all_reviews(client: PlayConsoleClient) -> list[dict]:
    url = reviews_url()
    all_reviews = []
    next_token = None
    while True:
        params: dict = {"maxResults": _REVIEWS_PAGE_SIZE}
        if next_token:
            params["token"] = next_token
        resp = client.get(url, params=params)
        data = resp.json()
        batch = data.get("reviews", [])
        all_reviews.extend(flatten_review(r) for r in batch)
        next_token = data.get("tokenPagination", {}).get("nextPageToken")
        if not next_token:
            break
    return all_reviews


def run(date_from: str, date_to: str, sa_key_json: str | None = None) -> None:
    client = PlayConsoleClient(sa_key_json=sa_key_json)
    start = date_str_to_dict(date_from)
    end = date_str_to_dict(date_to)

    errors = []
    total_rows = 0

    # pull each metric set independently; one failure does not stop the rest
    for ms in METRIC_SETS:
        try:
            rows = _pull_metric_set(client, ms, start, end)
            if rows:
                load_json_rows_to_raw(
                    rows=rows,
                    dataset_id=BQ_DATASET_RAW_PLAY_CONSOLE,
                    table_id=ms["table"],
                    source="play_console",
                    date_from=date_from,
                    date_to=date_to,
                    project_id=GCP_PROJECT,
                )
                total_rows += len(rows)
            logger.info(f"{ms['name']}: {len(rows)} rows")
        except Exception as exc:
            logger.error(f"{ms['name']} failed: {exc}")
            errors.append(ms["name"])

    # pull reviews (not date-scoped; returns current state of all reviews)
    try:
        reviews = _pull_all_reviews(client)
        if reviews:
            load_json_rows_to_raw(
                rows=reviews,
                dataset_id=BQ_DATASET_RAW_PLAY_CONSOLE,
                table_id="raw_reviews",
                source="play_console",
                date_from=date_from,
                date_to=date_to,
                project_id=GCP_PROJECT,
            )
            total_rows += len(reviews)
        logger.info(f"reviews: {len(reviews)} rows")
    except Exception as exc:
        logger.error(f"reviews failed: {exc}")
        errors.append("reviews")

    if errors:
        raise RuntimeError(f"Extract failed for: {errors}")

    logger.info(f"Extract complete: {len(METRIC_SETS) + 1} pulls, {total_rows} total rows")
