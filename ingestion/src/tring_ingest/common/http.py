import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from tring_ingest.common.logging import get_logger

logger = get_logger(__name__)

# transient codes worth a retry; everything else fails fast
_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


# tenacity retries on this; raising it (not the raw response) is what triggers backoff
class RetryableHTTPError(Exception):
    pass


def build_session(bearer_token: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {bearer_token}"})
    return session


@retry(
    retry=retry_if_exception_type(RetryableHTTPError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=4, max=30),
    reraise=True,
)
def get_with_retry(session: requests.Session, url: str, params: dict) -> requests.Response:
    response = session.get(url, params=params, timeout=120)

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
