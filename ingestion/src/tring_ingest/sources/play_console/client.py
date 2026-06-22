import requests
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import service_account

from tring_ingest.common.auth import get_secret
from tring_ingest.common.config import PLAY_CONSOLE_SECRET_NAME
from tring_ingest.common.http import RetryableHTTPError
from tring_ingest.common.logging import get_logger

logger = get_logger(__name__)

_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}

_SCOPES = [
    "https://www.googleapis.com/auth/androidpublisher",
    "https://www.googleapis.com/auth/playdeveloperreporting",
]


class PlayConsoleClient:
    # sa_key_json arg is for tests; in prod it comes from Secret Manager.
    # Secret Manager value: the full service account JSON as a string.
    def __init__(self, sa_key_json: str | None = None):
        import json

        raw = sa_key_json or get_secret(PLAY_CONSOLE_SECRET_NAME)
        key_data = json.loads(raw)
        self._creds = service_account.Credentials.from_service_account_info(
            key_data, scopes=_SCOPES
        )
        self._session = requests.Session()

    def _ensure_token(self) -> None:
        if not self._creds.valid:
            self._creds.refresh(GoogleRequest())
        self._session.headers.update({"Authorization": f"Bearer {self._creds.token}"})

    def get(self, url: str, params: dict | None = None) -> requests.Response:
        from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

        @retry(
            retry=retry_if_exception_type(RetryableHTTPError),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=2, min=4, max=30),
            reraise=True,
        )
        def _get() -> requests.Response:
            self._ensure_token()
            response = self._session.get(url, params=params, timeout=120)
            if response.status_code in _RETRY_STATUS_CODES:
                logger.warning(
                    "retrying http error", extra={"status": response.status_code, "url": url}
                )
                raise RetryableHTTPError(f"HTTP {response.status_code} from {url}")
            if not response.ok:
                logger.error(
                    "http error",
                    extra={"status": response.status_code, "url": url, "body": response.text[:500]},
                )
                response.raise_for_status()
            return response

        return _get()

    def post(self, url: str, payload: dict) -> requests.Response:
        from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

        @retry(
            retry=retry_if_exception_type(RetryableHTTPError),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=2, min=4, max=30),
            reraise=True,
        )
        def _post() -> requests.Response:
            self._ensure_token()
            response = self._session.post(url, json=payload, timeout=120)
            if response.status_code in _RETRY_STATUS_CODES:
                logger.warning(
                    "retrying http error", extra={"status": response.status_code, "url": url}
                )
                raise RetryableHTTPError(f"HTTP {response.status_code} from {url}")
            if not response.ok:
                logger.error(
                    "http error",
                    extra={"status": response.status_code, "url": url, "body": response.text[:500]},
                )
                response.raise_for_status()
            return response

        return _post()
