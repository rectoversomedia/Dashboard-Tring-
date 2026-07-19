import os

APP_ID = os.environ.get("APPSTORE_APP_ID", "1350501409")
BASE = "https://api.appstoreconnect.apple.com"

# ongoing request created 2026-06-26; override via env if recreated
# this is a report request UUID, not a creds; useless without JWT auth
ONGOING_REQUEST_ID = os.environ.get(
    "APPSTORE_ANALYTICS_REQUEST_ID", "77203237-b1c3-40ed-bccf-ce4345c7d5ab"
)

# one-time snapshot request created 2026-06-26; covers Nov 2024 - Jun 2026 historical data
# report request UUID only, not a creds
SNAPSHOT_REQUEST_ID = os.environ.get(
    "APPSTORE_SNAPSHOT_REQUEST_ID", "f8470156-c123-49cf-860d-bed40475e688"
)

REVIEWS_PAGE_SIZE = 200

# the 5 reports the dashboard needs; resolved by exact Apple report name at runtime
# (do not hardcode r3-/r6-/... ids -- they change if the ongoing request is recreated)
ANALYTICS_REPORTS = [
    {"name": "App Downloads Standard", "table": "raw_app_downloads"},
    {"name": "App Store Installation and Deletion Standard", "table": "raw_app_installs_deletions"},
    {"name": "App Sessions Standard", "table": "raw_app_sessions"},
    {
        "name": "App Store Discovery and Engagement Standard",
        "table": "raw_app_discovery_engagement",
    },
    {"name": "App Install Performance", "table": "raw_app_install_performance"},
]


def _snake(col: str) -> str:
    # tsv header -> snake_case column name
    return col.strip().lower().replace(" ", "_").replace("-", "_")


def flatten_tsv(text: str) -> list[dict]:
    # parse gzip-decoded tsv into list of dicts; all values stay as strings
    lines = text.strip().splitlines()
    if not lines:
        return []
    header = [_snake(h) for h in lines[0].split("\t")]
    return [dict(zip(header, line.split("\t"), strict=False)) for line in lines[1:]]


def flatten_review(r: dict) -> dict:
    a = r.get("attributes", {})
    return {
        "review_id": r["id"],
        "rating": str(a.get("rating", "")),
        "title": a.get("title", ""),
        "body": a.get("body", ""),
        "reviewer_nickname": a.get("reviewerNickname", ""),
        "created_date": a.get("createdDate", ""),
        "territory": a.get("territory", ""),
    }
