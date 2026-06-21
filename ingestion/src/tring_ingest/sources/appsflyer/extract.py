from tring_ingest.common.bq_loader import load_csv_to_raw
from tring_ingest.common.config import APPSFLYER_APP_IDS, BQ_DATASET_RAW_APPSFLYER, GCP_PROJECT
from tring_ingest.common.logging import get_logger
from tring_ingest.sources.appsflyer.client import AppsFlyerClient
from tring_ingest.sources.appsflyer.endpoints import ENDPOINTS, build_params

logger = get_logger(__name__)


def run(date_from: str, date_to: str, token: str | None = None) -> None:
    # 4 endpoints x 2 apps (android, ios) = 8 pulls. one bad pull shouldn't kill the
    # rest, so we collect failures and raise once at the end.
    client = AppsFlyerClient(token=token)
    total = len(APPSFLYER_APP_IDS) * len(ENDPOINTS)
    errors = []

    for app_id, platform in APPSFLYER_APP_IDS:
        for endpoint in ENDPOINTS:
            path = endpoint.path_template.format(app_id=app_id)
            params = build_params(date_from, date_to, endpoint.extra_params)
            try:
                response = client.get(path, params)
                rows = load_csv_to_raw(
                    csv_content=response.text,
                    dataset_id=BQ_DATASET_RAW_APPSFLYER,
                    table_id=endpoint.bq_table,
                    source="appsflyer",
                    app_id=app_id,
                    platform=platform,
                    date_from=date_from,
                    date_to=date_to,
                    project_id=GCP_PROJECT,
                )
                logger.info(
                    f"{endpoint.name} {platform}: {rows} rows",
                    extra={"endpoint": endpoint.name, "platform": platform, "rows": rows},
                )
            except Exception as exc:
                logger.error(
                    f"{endpoint.name} {platform} failed: {exc}",
                    extra={"endpoint": endpoint.name, "platform": platform, "error": str(exc)},
                )
                errors.append((endpoint.name, app_id, platform))

    if errors:
        raise RuntimeError(f"Extract failed for {len(errors)} pull(s): {errors}")

    logger.info(f"Extract complete: {total}/{total} succeeded")
