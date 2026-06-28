"""Tests for bq_loader row serialization. No real BQ calls."""

import json
from unittest.mock import MagicMock, patch


class TestLoadJsonRowsSerialization:
    def _make_bq_mock(self):
        from google.api_core.exceptions import NotFound

        mock_client = MagicMock()
        # raise NotFound so _get_existing_columns returns None (new table = keep all columns)
        mock_client.get_table.side_effect = NotFound("table not found")
        mock_client.create_dataset.return_value = None
        mock_client.load_table_from_json.return_value.result.return_value = None
        return mock_client

    def test_dict_field_serialized_as_valid_json(self):
        rows = [
            {
                "campaign_id": "c1",
                "basic_details": {"name": "Test Campaign", "tags": ["promo"]},
            }
        ]

        with patch("tring_ingest.common.bq_loader.bigquery.Client") as mock_cls:
            mock_cls.return_value = self._make_bq_mock()
            from tring_ingest.common.bq_loader import load_json_rows_to_raw

            load_json_rows_to_raw(
                rows=rows,
                dataset_id="raw",
                table_id="raw_campaigns",
                source="moengage",
                date_from="2026-06-01",
                date_to="2026-06-01",
            )

        loaded = mock_cls.return_value.load_table_from_json.call_args[0][0]
        assert len(loaded) == 1
        val = loaded[0]["basic_details"]
        # must be valid JSON, not Python repr
        parsed = json.loads(val)
        assert parsed["name"] == "Test Campaign"
        assert parsed["tags"] == ["promo"]

    def test_list_field_serialized_as_valid_json(self):
        rows = [{"campaign_id": "c1", "tags": ["a", "b"]}]

        with patch("tring_ingest.common.bq_loader.bigquery.Client") as mock_cls:
            mock_cls.return_value = self._make_bq_mock()
            from tring_ingest.common.bq_loader import load_json_rows_to_raw

            load_json_rows_to_raw(
                rows=rows,
                dataset_id="raw",
                table_id="t",
                source="s",
                date_from="2026-06-01",
                date_to="2026-06-01",
            )

        loaded = mock_cls.return_value.load_table_from_json.call_args[0][0]
        parsed = json.loads(loaded[0]["tags"])
        assert parsed == ["a", "b"]

    def test_scalar_field_stays_string(self):
        rows = [{"campaign_id": "c1", "status": "ACTIVE"}]

        with patch("tring_ingest.common.bq_loader.bigquery.Client") as mock_cls:
            mock_cls.return_value = self._make_bq_mock()
            from tring_ingest.common.bq_loader import load_json_rows_to_raw

            load_json_rows_to_raw(
                rows=rows,
                dataset_id="raw",
                table_id="t",
                source="s",
                date_from="2026-06-01",
                date_to="2026-06-01",
            )

        loaded = mock_cls.return_value.load_table_from_json.call_args[0][0]
        assert loaded[0]["status"] == "ACTIVE"
