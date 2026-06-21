from dataclasses import dataclass

from tring_ingest.common.config import (
    APPSFLYER_MASTER_AGG_CURRENCY,
    APPSFLYER_MASTER_AGG_GROUPINGS,
    APPSFLYER_MASTER_AGG_KPIS,
    APPSFLYER_TIMEZONE,
)


@dataclass
class Endpoint:
    name: str
    bq_table: str
    path_template: str
    extra_params: dict


def build_params(date_from: str, date_to: str, extra: dict | None = None) -> dict:
    params = {
        "from": date_from,
        "to": date_to,
        "timezone": APPSFLYER_TIMEZONE,
    }
    if extra:
        params.update(extra)
    return params


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
        extra_params={},
    ),
    Endpoint(
        name="blocked_installs",
        bq_table="raw_blocked_installs",
        path_template="/api/raw-data/export/app/{app_id}/blocked_installs_report/v5",
        extra_params={},
    ),
]
