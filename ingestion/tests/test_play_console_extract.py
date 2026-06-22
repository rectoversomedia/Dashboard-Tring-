"""Tests for Play Console extract: flatten helpers, pagination, extract flow."""

from unittest.mock import MagicMock, patch

import pytest

from tring_ingest.sources.play_console.endpoints import (
    METRIC_SETS,
    date_str_to_dict,
    flatten_reporting_row,
    flatten_review,
)
from tring_ingest.sources.play_console.extract import _pull_all_reviews, _pull_metric_set

# --- date_str_to_dict ---


def test_date_str_to_dict():
    assert date_str_to_dict("2026-05-01") == {"year": 2026, "month": 5, "day": 1}


def test_date_str_to_dict_zero_pad():
    result = date_str_to_dict("2026-01-09")
    assert result == {"year": 2026, "month": 1, "day": 9}


# --- flatten_reporting_row ---


def _make_reporting_row(metric_name="crashRate", metric_value="0.0013"):
    return {
        "aggregationPeriod": "DAILY",
        "startTime": {
            "year": 2026,
            "month": 5,
            "day": 1,
            "timeZone": {"id": "America/Los_Angeles"},
        },
        "dimensions": [{"dimension": "versionCode", "stringValue": "191"}],
        "metrics": [
            {
                "metric": metric_name,
                "decimalValue": {"value": metric_value},
                "decimalValueConfidenceInterval": {
                    "lowerBound": {"value": "0.0000"},
                    "upperBound": {"value": "0.0086"},
                },
            }
        ],
    }


def test_flatten_reporting_row_basic():
    row = _make_reporting_row()
    flat = flatten_reporting_row(row, "crashRateMetricSet")
    assert flat["metric_set"] == "crashRateMetricSet"
    assert flat["date"] == "2026-05-01"
    assert flat["versionCode"] == "191"
    assert flat["crashRate"] == "0.0013"
    assert flat["aggregation_period"] == "DAILY"


def test_flatten_reporting_row_confidence_interval():
    flat = flatten_reporting_row(_make_reporting_row(), "crashRateMetricSet")
    assert flat["crashRate_ci_lower"] == "0.0000"
    assert flat["crashRate_ci_upper"] == "0.0086"


def test_flatten_reporting_row_no_ci():
    row = _make_reporting_row()
    row["metrics"][0].pop("decimalValueConfidenceInterval")
    flat = flatten_reporting_row(row, "anrRateMetricSet")
    assert "anrRate_ci_lower" not in flat


def test_flatten_reporting_row_multi_dimension():
    row = {
        "aggregationPeriod": "DAILY",
        "startTime": {"year": 2026, "month": 5, "day": 3},
        "dimensions": [
            {"dimension": "versionCode", "stringValue": "200"},
            {"dimension": "startType", "stringValue": "COLD"},
        ],
        "metrics": [{"metric": "slowStartRate", "decimalValue": {"value": "0.05"}}],
    }
    flat = flatten_reporting_row(row, "slowStartRateMetricSet")
    assert flat["versionCode"] == "200"
    assert flat["startType"] == "COLD"
    assert flat["slowStartRate"] == "0.05"
    assert flat["date"] == "2026-05-03"


# --- flatten_review ---


def _make_review(star=4, has_reply=False):
    review = {
        "reviewId": "abc-123",
        "authorName": "User A",
        "comments": [
            {
                "userComment": {
                    "text": "Good app",
                    "lastModified": {"seconds": "1781852861", "nanos": 0},
                    "starRating": star,
                    "reviewerLanguage": "id",
                    "device": "a16",
                    "androidOsVersion": 36,
                    "appVersionCode": 191,
                    "appVersionName": "3.0.1",
                    "deviceMetadata": {
                        "productName": "Galaxy A16",
                        "manufacturer": "Samsung",
                        "deviceClass": "FORM_FACTOR_PHONE",
                        "ramMb": 3649,
                    },
                }
            }
        ],
    }
    if has_reply:
        review["comments"].append(
            {
                "developerComment": {
                    "text": "Thanks!",
                    "lastModified": {"seconds": "1781900000"},
                }
            }
        )
    return review


def test_flatten_review_basic():
    flat = flatten_review(_make_review())
    assert flat["review_id"] == "abc-123"
    assert flat["author_name"] == "User A"
    assert flat["star_rating"] == "4"
    assert flat["reviewer_language"] == "id"
    assert flat["app_version_code"] == "191"
    assert flat["device_manufacturer"] == "Samsung"
    assert flat["developer_reply_text"] == ""


def test_flatten_review_with_reply():
    flat = flatten_review(_make_review(has_reply=True))
    assert flat["developer_reply_text"] == "Thanks!"
    assert flat["developer_reply_seconds"] == "1781900000"


def test_flatten_review_star_rating():
    flat = flatten_review(_make_review(star=1))
    assert flat["star_rating"] == "1"


# --- _pull_metric_set ---


def test_pull_metric_set_returns_flattened():
    client = MagicMock()
    client.post.return_value.json.return_value = {
        "rows": [_make_reporting_row("crashRate", "0.001")]
    }
    ms = METRIC_SETS[0]  # crashRateMetricSet
    rows = _pull_metric_set(
        client, ms, {"year": 2026, "month": 5, "day": 1}, {"year": 2026, "month": 6, "day": 1}
    )
    assert len(rows) == 1
    assert rows[0]["metric_set"] == "crashRateMetricSet"
    assert rows[0]["crashRate"] == "0.001"


def test_pull_metric_set_empty_response():
    client = MagicMock()
    client.post.return_value.json.return_value = {"rows": []}
    rows = _pull_metric_set(client, METRIC_SETS[0], {}, {})
    assert rows == []


# --- _pull_all_reviews ---


def test_pull_all_reviews_single_page():
    client = MagicMock()
    client.get.return_value.json.return_value = {
        "reviews": [_make_review(star=5)],
        "tokenPagination": {},
    }
    reviews = _pull_all_reviews(client)
    assert len(reviews) == 1
    assert reviews[0]["star_rating"] == "5"
    assert client.get.call_count == 1


def test_pull_all_reviews_pagination():
    responses = [
        {"reviews": [_make_review(star=5)], "tokenPagination": {"nextPageToken": "tok1"}},
        {"reviews": [_make_review(star=3)], "tokenPagination": {}},
    ]
    client = MagicMock()
    client.get.return_value.json.side_effect = responses
    reviews = _pull_all_reviews(client)
    assert len(reviews) == 2
    assert client.get.call_count == 2


def test_pull_all_reviews_empty():
    client = MagicMock()
    client.get.return_value.json.return_value = {"reviews": [], "tokenPagination": {}}
    reviews = _pull_all_reviews(client)
    assert reviews == []


# --- extract run flow ---


@patch("tring_ingest.sources.play_console.extract.load_json_rows_to_raw")
@patch("tring_ingest.sources.play_console.extract.PlayConsoleClient")
def test_run_calls_all_metric_sets_and_reviews(mock_client_cls, mock_loader):
    instance = mock_client_cls.return_value
    instance.post.return_value.json.return_value = {"rows": [_make_reporting_row()]}
    instance.get.return_value.json.return_value = {
        "reviews": [_make_review()],
        "tokenPagination": {},
    }

    from tring_ingest.sources.play_console.extract import run

    run(date_from="2026-05-01", date_to="2026-06-01", sa_key_json='{"type":"service_account"}')

    # 6 metric sets + 1 reviews call
    assert mock_loader.call_count == len(METRIC_SETS) + 1


@patch("tring_ingest.sources.play_console.extract.load_json_rows_to_raw")
@patch("tring_ingest.sources.play_console.extract.PlayConsoleClient")
def test_run_collects_errors_raises_at_end(mock_client_cls, mock_loader):
    instance = mock_client_cls.return_value
    # first metric set fails, rest OK, reviews OK
    instance.post.return_value.json.side_effect = [
        Exception("API down"),
        *[{"rows": [_make_reporting_row()]}] * (len(METRIC_SETS) - 1),
    ]
    instance.get.return_value.json.return_value = {
        "reviews": [_make_review()],
        "tokenPagination": {},
    }

    from tring_ingest.sources.play_console.extract import run

    with pytest.raises(RuntimeError, match="Extract failed"):
        run(date_from="2026-05-01", date_to="2026-06-01", sa_key_json='{"type":"service_account"}')
