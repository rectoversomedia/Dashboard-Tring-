from dataclasses import dataclass
from datetime import date, timedelta

from tring_ingest.common.config import (
    APPSFLYER_CHUNK_HOURS,
    APPSFLYER_MASTER_AGG_CURRENCY,
    APPSFLYER_MASTER_AGG_GROUPINGS,
    APPSFLYER_MASTER_AGG_KPIS,
    APPSFLYER_MAXIMUM_ROWS,
    APPSFLYER_TIMEZONE,
)


@dataclass
class Endpoint:
    name: str
    bq_table: str
    path_template: str
    extra_params: dict
    # None = one request for the whole date range. A number = split each day into slices of
    # that many hours, one request each. Only needed for endpoints whose daily volume can
    # exceed the API's 200k row cap (in_app_events); the rest return a few hundred rows.
    chunk_hours: int | None = None


def build_params(date_from: str, date_to: str, extra: dict | None = None) -> dict:
    params = {
        "from": date_from,
        "to": date_to,
        "timezone": APPSFLYER_TIMEZONE,
    }
    if extra:
        params.update(extra)
    return params


def build_windows(date_from: str, date_to: str, chunk_hours: int | None) -> list[tuple[str, str]]:
    """Request windows for one endpoint, as (from, to) pairs passed straight to the API.

    chunk_hours=None keeps the original single date-only window. Otherwise each day in the
    range is split into slices. Slice bounds are "HH:00" to "HH:59" so consecutive slices
    neither overlap (the next starts at the following hour) nor skip anything (":59" covers
    through :59:59).
    """
    if not chunk_hours:
        return [(date_from, date_to)]
    if chunk_hours < 1 or chunk_hours > 24:
        raise ValueError(f"chunk_hours must be between 1 and 24, got {chunk_hours}")

    start, end = date.fromisoformat(date_from), date.fromisoformat(date_to)
    if end < start:
        raise ValueError(f"date_to {date_to} is before date_from {date_from}")

    windows = []
    day = start
    while day <= end:
        for hour in range(0, 24, chunk_hours):
            last_hour = min(hour + chunk_hours - 1, 23)
            windows.append((f"{day} {hour:02d}:00", f"{day} {last_hour:02d}:59"))
        day += timedelta(days=1)
    return windows


ENDPOINTS: list[Endpoint] = [
    Endpoint(
        name="installs",
        bq_table="raw_installs",
        path_template="/api/raw-data/export/app/{app_id}/installs_report/v5",
        extra_params={},
    ),
    Endpoint(
        name="master_agg",
        bq_table="raw_campaign_performance",
        path_template="/api/master-agg-data/v4/app/{app_id}",
        extra_params={
            "groupings": APPSFLYER_MASTER_AGG_GROUPINGS,
            "kpis": APPSFLYER_MASTER_AGG_KPIS,
            "currency": APPSFLYER_MASTER_AGG_CURRENCY,
        },
    ),
    Endpoint(
        name="in_app_events",
        bq_table="raw_in_app_events",
        path_template="/api/raw-data/export/app/{app_id}/in_app_events_report/v5",
        # The only endpoint whose daily volume exceeds the default 200k row cap.
        extra_params={"maximum_rows": APPSFLYER_MAXIMUM_ROWS},
        chunk_hours=APPSFLYER_CHUNK_HOURS or None,
    ),
    Endpoint(
        name="blocked_installs",
        bq_table="raw_blocked_installs",
        path_template="/api/raw-data/export/app/{app_id}/blocked_installs_report/v5",
        extra_params={},
    ),
]
