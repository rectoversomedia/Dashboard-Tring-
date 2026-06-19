"""Fetch secrets from Secret Manager, with env var fallback for local/migration use."""

import os

from tring_ingest.common.config import GCP_PROJECT
from tring_ingest.common.logging import get_logger

logger = get_logger(__name__)

# Env var name pattern for fallback: secret_id uppercased, hyphens to underscores
# e.g. "appsflyer-api-token" -> APPSFLYER_API_TOKEN
def _env_var_name(secret_id: str) -> str:
    return secret_id.upper().replace("-", "_")


def get_secret(secret_id: str, project_id: str = GCP_PROJECT) -> str:
    """
    Fetch secret. Priority:
    1. Env var matching secret_id (e.g. APPSFLYER_API_TOKEN) — for local/migration
    2. Secret Manager — for Cloud Run production runtime
    """
    env_var = _env_var_name(secret_id)
    value = os.environ.get(env_var)
    if value:
        logger.info("Secret loaded from env var", extra={"secret_id": secret_id, "env_var": env_var})
        return value

    from google.cloud import secretmanager
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    payload = response.payload.data.decode("utf-8")
    logger.info("Secret fetched from Secret Manager", extra={"secret_id": secret_id})
    return payload
