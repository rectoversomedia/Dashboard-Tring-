"""Tests for AppsFlyer extract. All HTTP calls mocked. No real GCP or API calls."""

from unittest.mock import MagicMock, patch

import pytest


class TestEndpoints:
    def test_endpoint_count(self):
        from tring_ingest.sources.appsflyer.endpoints import ENDPOINTS

        assert len(ENDPOINTS) == 4

    def test_endpoint_names(self):
        from tring_ingest.sources.appsflyer.endpoints import ENDPOINTS

        names = {e.name for e in ENDPOINTS}
        assert names == {"installs", "master_agg", "in_app_events", "blocked_installs"}

    def test_endpoint_bq_tables(self):
        from tring_ingest.sources.appsflyer.endpoints import ENDPOINTS

        tables = {e.bq_table for e in ENDPOINTS}
        assert tables == {
            "raw_installs",
            "raw_campaign_performance",
            "raw_in_app_events",
            "raw_blocked_installs",
        }

    def test_build_params_includes_timezone(self):
        from tring_ingest.sources.appsflyer.endpoints import build_params

        params = build_params("2026-06-13", "2026-06-14")
        assert params["timezone"] == "Asia/Jakarta"
        assert params["from"] == "2026-06-13"
        assert params["to"] == "2026-06-14"

    def test_master_agg_params_include_geo_grouping(self):
        from tring_ingest.sources.appsflyer.endpoints import ENDPOINTS

        master = next(e for e in ENDPOINTS if e.name == "master_agg")
        assert "geo" in master.extra_params["groupings"]

    def test_chunking_is_disabled_by_default(self):
        """Hourly slicing exceeds the daily report-download quota, so it ships off.

        See APPSFLYER_CHUNK_HOURS in config: the 11th in-app-events pull of a day is rejected
        with HTTP 400. maximum_rows is the primary fix; chunking is the fallback knob.
        """
        from tring_ingest.sources.appsflyer.endpoints import ENDPOINTS

        assert {e.name for e in ENDPOINTS if e.chunk_hours} == set()

    def test_in_app_events_requests_one_million_rows(self):
        """Default 200k silently truncates a full Android day to its last ~3.5 hours."""
        from tring_ingest.sources.appsflyer.endpoints import ENDPOINTS, build_params

        events = next(e for e in ENDPOINTS if e.name == "in_app_events")
        assert events.extra_params["maximum_rows"] == 1_000_000
        assert build_params("2026-06-13", "2026-06-14", events.extra_params)["maximum_rows"] == (
            1_000_000
        )


class TestBuildWindows:
    def test_no_chunking_keeps_single_date_window(self):
        from tring_ingest.sources.appsflyer.endpoints import build_windows

        assert build_windows("2026-06-13", "2026-06-14", None) == [("2026-06-13", "2026-06-14")]

    def test_hourly_chunking_covers_every_hour_of_each_day(self):
        from tring_ingest.sources.appsflyer.endpoints import build_windows

        windows = build_windows("2026-06-13", "2026-06-14", 1)
        assert len(windows) == 48  # 2 days x 24 hours
        assert windows[0] == ("2026-06-13 00:00", "2026-06-13 00:59")
        assert windows[23] == ("2026-06-13 23:00", "2026-06-13 23:59")
        assert windows[24] == ("2026-06-14 00:00", "2026-06-14 00:59")

    def test_windows_do_not_overlap_or_skip(self):
        """Slice N ends at :59 and slice N+1 starts on the next hour  -  no gap, no double count."""
        from tring_ingest.sources.appsflyer.endpoints import build_windows

        for chunk_hours in (1, 2, 4, 6):
            windows = build_windows("2026-06-13", "2026-06-13", chunk_hours)
            assert len(windows) == 24 // chunk_hours
            assert windows[0][0].endswith(" 00:00")
            assert windows[-1][1].endswith(" 23:59")
            for (_, prev_to), (next_from, _) in zip(windows, windows[1:], strict=False):
                prev_hour = int(prev_to[-5:-3])
                next_hour = int(next_from[-5:-3])
                assert prev_to.endswith(":59")
                assert next_hour == prev_hour + 1

    def test_chunk_hours_not_dividing_24_still_ends_at_last_hour(self):
        from tring_ingest.sources.appsflyer.endpoints import build_windows

        windows = build_windows("2026-06-13", "2026-06-13", 5)
        assert windows[-1] == ("2026-06-13 20:00", "2026-06-13 23:59")

    def test_rejects_reversed_range(self):
        from tring_ingest.sources.appsflyer.endpoints import build_windows

        with pytest.raises(ValueError, match="before date_from"):
            build_windows("2026-06-14", "2026-06-13", 1)

    def test_rejects_out_of_range_chunk_hours(self):
        from tring_ingest.sources.appsflyer.endpoints import build_windows

        with pytest.raises(ValueError, match="between 1 and 24"):
            build_windows("2026-06-13", "2026-06-13", 25)


class TestBqLoader:
    def test_empty_csv_returns_zero(self):
        from tring_ingest.common.bq_loader import load_csv_to_raw

        with patch("tring_ingest.common.bq_loader.bigquery.Client"):
            result = load_csv_to_raw(
                csv_content="col1,col2\n",  # header only, no data rows
                dataset_id="appsflyer_raw",
                table_id="raw_installs",
                source="appsflyer",
                app_id="com.pegadaiandigital",
                platform="android",
                date_from="2026-06-13",
                date_to="2026-06-14",
                project_id="test-project",
            )
        assert result == 0

    def test_metadata_columns_stamped(self):
        """Rows loaded to BQ must contain all metadata columns."""
        from tring_ingest.common.bq_loader import load_csv_to_raw

        loaded_rows = []

        def capture_load(rows, *args, **kwargs):
            loaded_rows.extend(rows)
            job = MagicMock()
            job.result.return_value = None
            return job

        with patch("tring_ingest.common.bq_loader.bigquery.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.load_table_from_json.side_effect = capture_load

            load_csv_to_raw(
                csv_content="Install Time,Media Source\n2026-06-13 10:00:00,organic\n",
                dataset_id="appsflyer_raw",
                table_id="raw_installs",
                source="appsflyer",
                app_id="com.pegadaiandigital",
                platform="android",
                date_from="2026-06-13",
                date_to="2026-06-14",
                project_id="test-project",
            )

        assert len(loaded_rows) == 1
        row = loaded_rows[0]
        assert row["_source"] == "appsflyer"
        assert row["_app_id"] == "com.pegadaiandigital"
        assert row["_platform"] == "android"
        assert row["_extract_from"] == "2026-06-13"
        assert row["_extract_to"] == "2026-06-14"
        assert "_run_id" in row
        assert "_ingested_at" in row


class TestExtractRun:
    def test_run_calls_8_pulls_with_chunking_off(self):
        """4 endpoints x 2 app IDs = 8 pulls, one per endpoint per app (the shipped default)."""
        mock_response = MagicMock()
        mock_response.text = "col1\nval1\n"

        with (
            patch("tring_ingest.sources.appsflyer.extract.AppsFlyerClient") as mock_client_cls,
            patch("tring_ingest.sources.appsflyer.extract.load_csv_to_raw") as mock_load,
        ):
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.get.return_value = mock_response
            mock_load.return_value = 1

            from tring_ingest.sources.appsflyer.extract import run

            run(date_from="2026-06-13", date_to="2026-06-14", token="fake-token")

        assert mock_client.get.call_count == 8
        assert mock_load.call_count == 8

    def test_metadata_stays_day_level(self):
        """_extract_from/_extract_to are DATE columns, so they never carry an hour slice."""
        mock_response = MagicMock()
        mock_response.text = "col1\nval1\n"

        with (
            patch("tring_ingest.sources.appsflyer.extract.AppsFlyerClient") as mock_client_cls,
            patch("tring_ingest.sources.appsflyer.extract.load_csv_to_raw") as mock_load,
        ):
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.get.return_value = mock_response
            mock_load.return_value = 1

            from tring_ingest.sources.appsflyer.extract import run

            run(date_from="2026-06-13", date_to="2026-06-14", token="fake-token")

        for call in mock_load.call_args_list:
            assert call.kwargs["date_from"] == "2026-06-13"
            assert call.kwargs["date_to"] == "2026-06-14"

    def test_truncated_pull_is_logged_but_not_fatal(self):
        """Hitting the row cap means dropped events. It must be loud, not silent, not fatal."""
        mock_response = MagicMock()
        mock_response.text = "col1\nval1\n"

        with (
            patch("tring_ingest.sources.appsflyer.extract.AppsFlyerClient") as mock_client_cls,
            patch("tring_ingest.sources.appsflyer.extract.load_csv_to_raw") as mock_load,
            patch("tring_ingest.sources.appsflyer.extract.logger") as mock_logger,
        ):
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.get.return_value = mock_response
            mock_load.return_value = 200_000  # exactly the cap

            from tring_ingest.sources.appsflyer.extract import run

            run(date_from="2026-06-13", date_to="2026-06-13", token="fake-token")

        assert any("row cap" in str(c) for c in mock_logger.error.call_args_list)

    def test_run_raises_on_partial_failure(self):
        mock_response = MagicMock()
        mock_response.text = "col1\nval1\n"

        call_count = 0

        def flaky_get(path, params):
            nonlocal call_count
            call_count += 1
            if call_count == 3:
                raise RuntimeError("Simulated HTTP failure")
            return mock_response

        with (
            patch("tring_ingest.sources.appsflyer.extract.AppsFlyerClient") as mock_client_cls,
            patch("tring_ingest.sources.appsflyer.extract.load_csv_to_raw") as mock_load,
        ):
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.get.side_effect = flaky_get
            mock_load.return_value = 1

            from tring_ingest.sources.appsflyer.extract import run

            with pytest.raises(RuntimeError, match="Extract failed"):
                run(date_from="2026-06-13", date_to="2026-06-14", token="fake-token")


class TestHttpRetry:
    def test_retryable_status_raises(self):
        import responses as rsps_lib
        from tring_ingest.common.http import RetryableHTTPError, build_session, get_with_retry

        with rsps_lib.RequestsMock() as rsps:
            rsps.add(rsps_lib.GET, "https://example.com/test", status=503)
            rsps.add(rsps_lib.GET, "https://example.com/test", status=503)
            rsps.add(rsps_lib.GET, "https://example.com/test", status=503)

            session = build_session("fake-token")
            with pytest.raises(RetryableHTTPError):
                get_with_retry(session, "https://example.com/test", {})
