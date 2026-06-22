"""Tests for MoEngage extract. All HTTP calls mocked. No real GCP or API calls."""

from unittest.mock import MagicMock, patch

import pytest


class TestStatsChunking:
    def test_single_chunk_under_30_days(self):
        from tring_ingest.sources.moengage.endpoints import build_stats_chunks

        chunks = build_stats_chunks(["id1"], "2026-06-01", "2026-06-20")
        assert len(chunks) == 1
        assert chunks[0]["start_date"] == "2026-06-01"
        assert chunks[0]["end_date"] == "2026-06-20"

    def test_exactly_30_days_is_one_chunk(self):
        from tring_ingest.sources.moengage.endpoints import build_stats_chunks

        chunks = build_stats_chunks(["id1"], "2026-06-01", "2026-06-30")
        assert len(chunks) == 1

    def test_31_days_splits_into_two_chunks(self):
        from tring_ingest.sources.moengage.endpoints import build_stats_chunks

        chunks = build_stats_chunks(["id1"], "2026-06-01", "2026-07-01")
        assert len(chunks) == 2
        assert chunks[0]["start_date"] == "2026-06-01"
        assert chunks[0]["end_date"] == "2026-06-30"
        assert chunks[1]["start_date"] == "2026-07-01"
        assert chunks[1]["end_date"] == "2026-07-01"

    def test_chunks_cover_full_range_contiguously(self):
        from datetime import date, timedelta

        from tring_ingest.sources.moengage.endpoints import build_stats_chunks

        chunks = build_stats_chunks(["id1"], "2026-01-01", "2026-03-31")
        # verify no gaps: each chunk_end + 1 == next chunk_start
        for i in range(len(chunks) - 1):
            end = date.fromisoformat(chunks[i]["end_date"])
            next_start = date.fromisoformat(chunks[i + 1]["start_date"])
            assert end + timedelta(days=1) == next_start

    def test_attribution_and_metric_type_passed_through(self):
        from tring_ingest.sources.moengage.endpoints import build_stats_chunks

        chunks = build_stats_chunks(["id1"], "2026-06-01", "2026-06-10", "CLICK_THROUGH", "UNIQUE")
        assert chunks[0]["attribution_type"] == "CLICK_THROUGH"
        assert chunks[0]["metric_type"] == "UNIQUE"


class TestFlattenStats:
    def test_flatten_single_platform(self):
        from tring_ingest.sources.moengage.extract import _flatten_stats

        stats_data = {
            "platforms": {
                "ANDROID": {
                    "locales": {
                        "default": {
                            "variations": {
                                "all_variations": {
                                    "performance_stats": {
                                        "sent": 100,
                                        "impression": 80,
                                        "click": 20,
                                        "ctr": 0.25,
                                    },
                                    "delivery_funnel": {},
                                    "conversion_goal_stats": {},
                                }
                            }
                        }
                    }
                }
            }
        }
        rows = _flatten_stats("campaign-abc", stats_data)
        assert len(rows) == 1
        assert rows[0]["campaign_id"] == "campaign-abc"
        assert rows[0]["platform"] == "ANDROID"
        assert rows[0]["sent"] == 100

    def test_flatten_two_platforms(self):
        from tring_ingest.sources.moengage.extract import _flatten_stats

        stats_data = {
            "platforms": {
                "ANDROID": {
                    "locales": {
                        "default": {
                            "variations": {
                                "all_variations": {
                                    "performance_stats": {"sent": 100},
                                    "delivery_funnel": {},
                                    "conversion_goal_stats": {},
                                }
                            }
                        }
                    }
                },
                "IOS": {
                    "locales": {
                        "default": {
                            "variations": {
                                "all_variations": {
                                    "performance_stats": {"sent": 10},
                                    "delivery_funnel": {},
                                    "conversion_goal_stats": {},
                                }
                            }
                        }
                    }
                },
            }
        }
        rows = _flatten_stats("campaign-abc", stats_data)
        platforms = {r["platform"] for r in rows}
        assert platforms == {"ANDROID", "IOS"}

    def test_flatten_empty_platforms(self):
        from tring_ingest.sources.moengage.extract import _flatten_stats

        rows = _flatten_stats("campaign-abc", {"platforms": {}})
        assert rows == []


class TestExtractRun:
    def _make_search_response(self, campaigns: list[dict]) -> MagicMock:
        # actual API returns bare list, not wrapped dict
        resp = MagicMock()
        resp.json.return_value = campaigns
        return resp

    def _make_stats_response(self, campaign_id: str) -> MagicMock:
        resp = MagicMock()
        resp.json.return_value = {
            "data": {
                campaign_id: [
                    {
                        "platforms": {
                            "ANDROID": {
                                "locales": {
                                    "default": {
                                        "variations": {
                                            "all_variations": {
                                                "performance_stats": {"sent": 50},
                                                "delivery_funnel": {},
                                                "conversion_goal_stats": {},
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                ]
            }
        }
        return resp

    def test_run_calls_search_then_stats(self):
        campaigns = [{"campaign_id": "cid-001", "channel": "PUSH"}]

        with (
            patch("tring_ingest.sources.moengage.extract.MoEngageClient") as mock_cls,
            patch("tring_ingest.sources.moengage.extract.load_json_rows_to_raw") as mock_load,
        ):
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.post.side_effect = [
                self._make_search_response(campaigns),
                self._make_stats_response("cid-001"),
            ]
            mock_load.return_value = 1

            from tring_ingest.sources.moengage.extract import run

            run(date_from="2026-06-01", date_to="2026-06-20", creds="WS_ID:API_KEY")

        # post called twice: once for search, once for stats chunk
        assert mock_client.post.call_count == 2
        assert mock_load.call_count == 2  # raw_campaigns + raw_campaign_stats

    def test_run_raises_on_stats_chunk_failure(self):
        campaigns = [{"campaign_id": "cid-001"}]

        with (
            patch("tring_ingest.sources.moengage.extract.MoEngageClient") as mock_cls,
            patch("tring_ingest.sources.moengage.extract.load_json_rows_to_raw") as mock_load,
        ):
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.post.side_effect = [
                self._make_search_response(campaigns),
                RuntimeError("simulated stats failure"),
            ]
            mock_load.return_value = 1

            from tring_ingest.sources.moengage.extract import run

            with pytest.raises(RuntimeError, match="Extract failed"):
                run(date_from="2026-06-01", date_to="2026-06-20", creds="WS_ID:API_KEY")

    def test_run_no_campaigns_skips_stats(self):
        with (
            patch("tring_ingest.sources.moengage.extract.MoEngageClient") as mock_cls,
            patch("tring_ingest.sources.moengage.extract.load_json_rows_to_raw") as mock_load,
        ):
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.post.return_value = self._make_search_response([])
            mock_load.return_value = 0

            from tring_ingest.sources.moengage.extract import run

            run(date_from="2026-06-01", date_to="2026-06-20", creds="WS_ID:API_KEY")

        # only search called, no stats
        assert mock_client.post.call_count == 1


class TestMoEngageClient:
    def test_auth_header_set_correctly(self):
        import base64

        with patch("tring_ingest.sources.moengage.client.get_secret", return_value="MY_WS:MY_KEY"):
            from tring_ingest.sources.moengage.client import MoEngageClient

            client = MoEngageClient()
            expected_token = base64.b64encode(b"MY_WS:MY_KEY").decode()
            assert client._session.headers["Authorization"] == f"Basic {expected_token}"
            assert client._session.headers["MOE-APPKEY"] == "MY_WS"
