from dataclasses import dataclass, field
from datetime import date, timedelta


SEARCH_PATH = "/core-services/v1/campaigns/search"
STATS_PATH = "/core-services/v1/campaign-stats"

# campaign-stats hard limits from the API (empirically verified)
STATS_MAX_WINDOW_DAYS = 30
STATS_MAX_CAMPAIGN_IDS = 10


@dataclass
class SearchPayload:
    channels: list[str] = field(default_factory=lambda: ["PUSH", "EMAIL", "SMS"])
    page: int = 1
    limit: int = 15

    def to_dict(self, request_id: str) -> dict:
        return {
            "request_id": request_id,
            "campaign_fields": {"channels": self.channels},
            "page": self.page,
            "limit": self.limit,
        }


def build_stats_chunks(
    campaign_ids: list[str],
    date_from: str,
    date_to: str,
    attribution_type: str = "VIEW_THROUGH",
    metric_type: str = "TOTAL",
) -> list[dict]:
    """Split by <=30-day windows AND <=10 campaign IDs per request."""
    start = date.fromisoformat(date_from)
    end = date.fromisoformat(date_to)
    chunks = []
    chunk_start = start
    while chunk_start <= end:
        chunk_end = min(chunk_start + timedelta(days=STATS_MAX_WINDOW_DAYS - 1), end)
        for i in range(0, max(len(campaign_ids), 1), STATS_MAX_CAMPAIGN_IDS):
            id_batch = campaign_ids[i: i + STATS_MAX_CAMPAIGN_IDS]
            chunks.append({
                "campaign_ids": id_batch,
                "start_date": chunk_start.isoformat(),
                "end_date": chunk_end.isoformat(),
                "attribution_type": attribution_type,
                "metric_type": metric_type,
            })
        chunk_start = chunk_end + timedelta(days=1)
    return chunks
