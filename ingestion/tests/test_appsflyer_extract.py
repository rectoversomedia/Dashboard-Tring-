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

    def test_schema_flag_set_on_drift(self):
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
                expected_columns=["Install Time", "Media Source", "Campaign"],
                project_id="test-project",
            )

        assert loaded_rows[0]["_schema_flag"] != ""

    def test_schema_flag_empty_when_no_drift(self):
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
                expected_columns=["Install Time", "Media Source"],
                project_id="test-project",
            )

        assert loaded_rows[0]["_schema_flag"] == ""


class TestExtractRun:
    def test_run_calls_8_pulls(self):
        """4 endpoints x 2 app IDs = 8 pulls."""
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
