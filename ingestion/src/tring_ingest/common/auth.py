import os

from tring_ingest.common.config import GCP_PROJECT
from tring_ingest.common.logging import get_logger

logger = get_logger(__name__)


def get_secret(secret_id: str, project_id: str = GCP_PROJECT) -> str:
    # local/dev can shortcut Secret Manager by exporting the token as an env var,
    # e.g. appsflyer-api-token -> APPSFLYER_API_TOKEN
    env_var = secret_id.upper().replace("-", "_")
    value = os.environ.get(env_var)
    if value:
        logger.info("secret loaded from env var", extra={"secret_id": secret_id})
        return value

    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("utf-8")
