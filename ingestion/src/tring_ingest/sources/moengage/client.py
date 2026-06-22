import base64

import requests

from tring_ingest.common.auth import get_secret
from tring_ingest.common.config import MOENGAGE_BASE_URL, MOENGAGE_SECRET_NAME
from tring_ingest.common.http import RetryableHTTPError
from tring_ingest.common.logging import get_logger

logger = get_logger(__name__)

_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


class MoEngageClient:
    # creds arg is for tests; in prod they come from Secret Manager.
    # Secret Manager value format: "WORKSPACE_ID:API_KEY"
    def __init__(self, creds: str | None = None):
        raw = creds or get_secret(MOENGAGE_SECRET_NAME)
        workspace_id, api_key = raw.split(":", 1)
        self._workspace_id = workspace_id
        self._base_url = MOENGAGE_BASE_URL
        token = base64.b64encode(f"{workspace_id}:{api_key}".encode()).decode()
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Basic {token}",
            "MOE-APPKEY": workspace_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def post(self, path: str, payload: dict) -> requests.Response:
        from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

        @retry(
            retry=retry_if_exception_type(RetryableHTTPError),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=2, min=4, max=30),
            reraise=True,
        )
        def _post() -> requests.Response:
            url = f"{self._base_url}{path}"
            response = self._session.post(url, json=payload, timeout=120)
            if response.status_code in _RETRY_STATUS_CODES:
                logger.warning("retrying http error", extra={"status": response.status_code, "url": url})
                raise RetryableHTTPError(f"HTTP {response.status_code} from {url}")
            if not response.ok:
                logger.error(
                    "http error",
                    extra={"status": response.status_code, "url": url, "body": response.text[:500]},
                )
                response.raise_for_status()
            return response

        return _post()
