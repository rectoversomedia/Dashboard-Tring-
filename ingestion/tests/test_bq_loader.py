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


class TestLoadTsvStream:
    def _make_bq_mock(self):
        from google.api_core.exceptions import NotFound

        mock_client = MagicMock()
        mock_client.get_table.side_effect = NotFound("table not found")
        mock_client.create_dataset.return_value = None
        mock_client.load_table_from_json.return_value.result.return_value = None
        return mock_client

    def _load(self, tsv, **kw):
        with patch("tring_ingest.common.bq_loader.bigquery.Client") as mock_cls:
            mock_cls.return_value = self._make_bq_mock()
            from tring_ingest.common.bq_loader import load_tsv_stream_to_raw

            total = load_tsv_stream_to_raw(
                tsv_text=tsv,
                dataset_id="raw",
                table_id="raw_app_downloads",
                source="app_store",
                date_from="2026-06-01",
                date_to="2026-06-02",
                **kw,
            )
        return total, mock_cls.return_value

    def test_parses_header_and_rows_from_str(self):
        total, client = self._load("Date\tDownload Type\n2026-06-01\tFirst-time\n")
        assert total == 1
        loaded = client.load_table_from_json.call_args[0][0]
        assert loaded[0]["date"] == "2026-06-01"
        assert loaded[0]["download_type"] == "First-time"

    def test_accepts_file_like_stream(self):
        import io

        total, client = self._load(io.StringIO("Date\tCounts\n2026-06-01\t10\n"))
        assert total == 1
        assert client.load_table_from_json.call_args[0][0][0]["counts"] == "10"

    def test_batches_flush_without_materialising_all_rows(self):
        import io

        lines = "Date\tCounts\n" + "".join(f"2026-06-{i:02d}\t{i}\n" for i in range(1, 6))
        total, client = self._load(io.StringIO(lines), batch_size=2)
        assert total == 5
        # 2 + 2 + 1 -> three separate load calls, never one 5-row list
        sizes = [len(c[0][0]) for c in client.load_table_from_json.call_args_list]
        assert sizes == [2, 2, 1]

    def test_empty_input_returns_zero(self):
        total, client = self._load("")
        assert total == 0
        client.load_table_from_json.assert_not_called()
