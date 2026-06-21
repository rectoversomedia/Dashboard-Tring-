import requests

from tring_ingest.common.auth import get_secret
from tring_ingest.common.config import APPSFLYER_BASE_URL, APPSFLYER_SECRET_NAME
from tring_ingest.common.http import build_session, get_with_retry


class AppsFlyerClient:
    # token arg is for tests; in prod it comes from Secret Manager
    def __init__(self, token: str | None = None):
        self._session = build_session(token or get_secret(APPSFLYER_SECRET_NAME))
        self._base_url = APPSFLYER_BASE_URL

    def get(self, path: str, params: dict) -> requests.Response:
        return get_with_retry(self._session, f"{self._base_url}{path}", params)
