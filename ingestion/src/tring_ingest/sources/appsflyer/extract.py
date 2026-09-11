from tring_ingest.common.bq_loader import load_csv_to_raw
from tring_ingest.common.config import (
    APPSFLYER_APP_IDS,
    APPSFLYER_RAW_REPORT_ROW_CAP,
    BQ_DATASET_RAW_APPSFLYER,
    GCP_PROJECT,
)
from tring_ingest.common.logging import get_logger
from tring_ingest.sources.appsflyer.client import AppsFlyerClient
from tring_ingest.sources.appsflyer.endpoints import ENDPOINTS, build_params, build_windows

logger = get_logger(__name__)


def run(date_from: str, date_to: str, token: str | None = None) -> None:
    # 4 endpoints x 2 apps (android, ios). in_app_events is split into hourly windows because
    # a whole day exceeds the API row cap, so the pull count is larger than 8. One bad pull
    # shouldn't kill the rest, so we collect failures and raise once at the end.
    client = AppsFlyerClient(token=token)
    errors = []
    truncated = []
    done = 0

    for app_id, platform in APPSFLYER_APP_IDS:
        for endpoint in ENDPOINTS:
            path = endpoint.path_template.format(app_id=app_id)
            for window_from, window_to in build_windows(date_from, date_to, endpoint.chunk_hours):
                params = build_params(window_from, window_to, endpoint.extra_params)
                try:
                    response = client.get(path, params)
                    rows = load_csv_to_raw(
                        csv_content=response.text,
                        dataset_id=BQ_DATASET_RAW_APPSFLYER,
                        table_id=endpoint.bq_table,
                        source="appsflyer",
                        app_id=app_id,
                        platform=platform,
                        # _extract_from/_extract_to are DATE columns, so the metadata stays
                        # day-level even when the request window is an hour slice.
                        date_from=date_from,
                        date_to=date_to,
                        project_id=GCP_PROJECT,
                    )
                    done += 1
                    logger.info(
                        f"{endpoint.name} {platform} {window_from}..{window_to}: {rows} rows",
                        extra={
                            "endpoint": endpoint.name,
                            "platform": platform,
                            "window_from": window_from,
                            "window_to": window_to,
                            "rows": rows,
                        },
                    )
                    # A pull sitting on the cap means the API truncated it and dropped events.
                    # This is silent in the response, so it has to be shouted about here.
                    if rows >= APPSFLYER_RAW_REPORT_ROW_CAP:
                        logger.error(
                            f"{endpoint.name} {platform} {window_from}..{window_to} hit the "
                            f"{APPSFLYER_RAW_REPORT_ROW_CAP} row cap  -  events were dropped. "
                            f"Lower APPSFLYER_CHUNK_HOURS and re-run this window.",
                            extra={
                                "endpoint": endpoint.name,
                                "platform": platform,
                                "window_from": window_from,
                                "window_to": window_to,
                                "rows": rows,
                            },
                        )
                        truncated.append((endpoint.name, platform, window_from, window_to))
                except Exception as exc:
                    logger.error(
                        f"{endpoint.name} {platform} {window_from}..{window_to} failed: {exc}",
                        extra={
                            "endpoint": endpoint.name,
                            "platform": platform,
                            "window_from": window_from,
                            "window_to": window_to,
                            "error": str(exc),
                        },
                    )
                    errors.append((endpoint.name, app_id, platform, window_from, window_to))

    if errors:
        raise RuntimeError(f"Extract failed for {len(errors)} pull(s): {errors}")

    if truncated:
        # Not fatal  -  the rows that did arrive are still valid and downstream needs them.
        # Surfaced here so a truncated run is visible in the final log line, not just mid-run.
        logger.error(f"Extract complete with {len(truncated)} truncated window(s): {truncated}")

    logger.info(f"Extract complete: {done}/{done} pulls succeeded")
