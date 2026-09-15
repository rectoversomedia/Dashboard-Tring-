"""Tests for App Store extract: flatten helpers, pagination, analytics flow, collect-errors."""

import gzip
import io
from unittest.mock import MagicMock, patch

import pytest
from tring_ingest.sources.app_store.endpoints import (
    ANALYTICS_REPORTS,
    _snake,
    flatten_review,
    flatten_tsv,
)
from tring_ingest.sources.app_store.extract import (
    _pull_reviews,
    _resolve_report_ids,
    _stream_analytics_report,
)

# --- _snake / flatten_tsv ---


def test_snake_basic():
    assert _snake("Download Type") == "download_type"
    assert _snake("App Apple Identifier") == "app_apple_identifier"
    assert _snake("Avg Install Duration") == "avg_install_duration"


def test_flatten_tsv_header_and_rows():
    tsv = "Date\tDownload Type\tCounts\n2026-06-01\tFirst-time download\t42"
    rows = flatten_tsv(tsv)
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-06-01"
    assert rows[0]["download_type"] == "First-time download"
    assert rows[0]["counts"] == "42"


def test_flatten_tsv_empty():
    assert flatten_tsv("") == []


# --- flatten_review ---


def test_flatten_review_fields():
    r = {
        "id": "rev-1",
        "attributes": {
            "rating": 4,
            "title": "Good",
            "body": "Works well",
            "reviewerNickname": "User A",
            "createdDate": "2026-06-01T10:00:00+00:00",
            "territory": "IDN",
        },
    }
    flat = flatten_review(r)
    assert flat["review_id"] == "rev-1"
    assert flat["rating"] == "4"
    assert flat["title"] == "Good"
    assert flat["territory"] == "IDN"
    assert flat["created_date"] == "2026-06-01T10:00:00+00:00"


# --- _resolve_report_ids ---


def _mock_reports_page(names, next_url=None):
    data = [{"id": f"r{i}-abc", "attributes": {"name": name}} for i, name in enumerate(names)]
    body = {"data": data, "links": {}}
    if next_url:
        body["links"]["next"] = next_url
    m = MagicMock()
    m.json.return_value = body
    return m


def test_resolve_report_ids_matches_wanted():
    client = MagicMock()
    wanted_names = [r["name"] for r in ANALYTICS_REPORTS]
    extra = ["Some Framework Usage Report"]
    client.get.return_value = _mock_reports_page(wanted_names + extra)

    result = _resolve_report_ids(client, "req-id-123")

    assert len(result) == len(ANALYTICS_REPORTS)
    for r in ANALYTICS_REPORTS:
        assert r["name"] in result
        report_id, table = result[r["name"]]
        assert table == r["table"]
        assert report_id.startswith("r")


def test_resolve_report_ids_paginates():
    client = MagicMock()
    page1 = _mock_reports_page(
        [ANALYTICS_REPORTS[0]["name"]], next_url="https://api.example.com/page2"
    )
    page2 = _mock_reports_page([ANALYTICS_REPORTS[1]["name"]])
    client.get.side_effect = [page1, page2]

    result = _resolve_report_ids(client, "req-id-123")

    assert client.get.call_count == 2
    assert ANALYTICS_REPORTS[0]["name"] in result
    assert ANALYTICS_REPORTS[1]["name"] in result


# --- _stream_analytics_report ---


def _make_gzip_tsv(tsv_text: str) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as f:
        f.write(tsv_text.encode("utf-8"))
    return buf.getvalue()


def _stream(client):
    return _stream_analytics_report(
        client=client,
        report_id="r3-abc",
        table="raw_app_downloads",
        source="app_store",
        date_from="2026-06-01",
        date_to="2026-06-02",
    )


def test_stream_analytics_report_streams_segment_to_bq():
    client = MagicMock()

    gzip_bytes = _make_gzip_tsv("Date\tCounts\n2026-06-01\t10\n2026-06-02\t20")

    instances_resp = MagicMock()
    instances_resp.json.return_value = {"data": [{"id": "inst-1"}], "links": {}}
    seg_list_resp = MagicMock()
    seg_list_resp.json.return_value = {"data": [{"id": "seg-1"}]}
    seg_fresh_resp = MagicMock()
    seg_fresh_resp.json.return_value = {
        "data": {"attributes": {"url": "https://s3.example.com/seg?sig=abc"}}
    }
    download_resp = MagicMock()
    download_resp.content = gzip_bytes

    client.get.side_effect = [instances_resp, seg_list_resp, seg_fresh_resp]
    client.get_unsigned.return_value = download_resp

    seen = {}

    def _capture(**kwargs):
        stream = kwargs["tsv_text"]
        # must be a file-like object, never a fully materialised str
        assert not isinstance(stream, str)
        seen["text"] = stream.read()
        return 2

    with patch(
        "tring_ingest.sources.app_store.extract.load_tsv_stream_to_raw", side_effect=_capture
    ):
        total = _stream(client)

    assert total == 2
    assert seen["text"] == "Date\tCounts\n2026-06-01\t10\n2026-06-02\t20"


def test_stream_analytics_report_skips_missing_url():
    client = MagicMock()

    instances_resp = MagicMock()
    instances_resp.json.return_value = {"data": [{"id": "inst-1"}], "links": {}}
    seg_list_resp = MagicMock()
    seg_list_resp.json.return_value = {"data": [{"id": "seg-1"}]}
    seg_fresh_resp = MagicMock()
    seg_fresh_resp.json.return_value = {"data": {"attributes": {}}}

    client.get.side_effect = [instances_resp, seg_list_resp, seg_fresh_resp]

    assert _stream(client) == 0
    client.get_unsigned.assert_not_called()


# --- _pull_reviews ---


def _review_item(review_id, created_date, rating=4):
    return {
        "id": review_id,
        "attributes": {
            "rating": rating,
            "title": "",
            "body": "",
            "reviewerNickname": "",
            "createdDate": created_date,
            "territory": "IDN",
        },
    }


def test_pull_reviews_stops_at_date_from():
    client = MagicMock()
    client.get.return_value.json.return_value = {
        "data": [
            _review_item("r1", "2026-06-05T00:00:00+00:00"),
            _review_item("r2", "2026-05-20T00:00:00+00:00"),  # before date_from
        ],
        "links": {},
    }
    reviews = _pull_reviews(client, date_from="2026-06-01")
    assert len(reviews) == 1
    assert reviews[0]["review_id"] == "r1"


def test_pull_reviews_paginates_via_links_next():
    client = MagicMock()
    page1 = MagicMock()
    page1.json.return_value = {
        "data": [_review_item("r1", "2026-06-10T00:00:00+00:00")],
        "links": {"next": "https://api.apple.com/reviews?cursor=abc"},
    }
    page2 = MagicMock()
    page2.json.return_value = {
        "data": [_review_item("r2", "2026-06-08T00:00:00+00:00")],
        "links": {},
    }
    client.get.side_effect = [page1, page2]

    reviews = _pull_reviews(client, date_from="2026-06-01")

    assert len(reviews) == 2
    assert client.get.call_count == 2


# --- run: collect-errors ---


@patch("tring_ingest.sources.app_store.extract.load_tsv_stream_to_raw")
@patch("tring_ingest.sources.app_store.extract.AppStoreClient")
def test_run_collect_errors_one_report_fails_others_load(mock_client_cls, mock_loader):
    instance = mock_client_cls.return_value

    # reviews: empty (no load call)
    # resolve: returns 2 reports
    # analytics report 1: raises; report 2: succeeds

    tsv = "Date\tCounts\n2026-06-01\t5"
    gzip_bytes = _make_gzip_tsv(tsv)

    reviews_resp = MagicMock()
    reviews_resp.json.return_value = {"data": [], "links": {}}

    resolve_resp = MagicMock()
    resolve_resp.json.return_value = {
        "data": [
            {"id": "r1-abc", "attributes": {"name": ANALYTICS_REPORTS[0]["name"]}},
            {"id": "r2-abc", "attributes": {"name": ANALYTICS_REPORTS[1]["name"]}},
        ],
        "links": {},
    }

    # report 1 instances -> raise
    fail_resp = MagicMock()
    fail_resp.json.side_effect = Exception("API error")

    # report 2 instances + segments + download ok
    inst2_resp = MagicMock()
    inst2_resp.json.return_value = {"data": [{"id": "inst-2"}], "links": {}}
    seg2_resp = MagicMock()
    seg2_resp.json.return_value = {"data": [{"id": "seg-2"}]}
    seg2_fresh_resp = MagicMock()
    seg2_fresh_resp.json.return_value = {
        "data": {"attributes": {"url": "https://s3.example.com/seg"}}
    }
    dl2_resp = MagicMock()
    dl2_resp.content = gzip_bytes

    instance.get.side_effect = [
        reviews_resp,  # reviews
        resolve_resp,  # resolve report ids
        fail_resp,  # report 1 instances -> fails
        inst2_resp,  # report 2 instances
        seg2_resp,  # report 2 segment list
        seg2_fresh_resp,  # report 2 fresh signed url
    ]
    instance.get_unsigned.return_value = dl2_resp

    from tring_ingest.sources.app_store.extract import run

    with pytest.raises(RuntimeError, match="Extract failed"):
        run(date_from="2026-06-01", date_to="2026-06-28", creds="KEY:ISSUER:FAKEP8")

    # report 2 still loaded despite report 1 failing
    assert mock_loader.call_count == 1
