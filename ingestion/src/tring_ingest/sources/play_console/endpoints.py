from dataclasses import dataclass

PACKAGE_NAME = "com.pegadaiandigital"

REPORTING_BASE = "https://playdeveloperreporting.googleapis.com/v1beta1"
PUBLISHER_BASE = "https://androidpublisher.googleapis.com/androidpublisher/v3"


# --- Reporting API metric sets ---
# Each entry: name, metrics list, dimensions list.
# Verified live against the API (2026-06-28).
METRIC_SETS = [
    {
        "name": "crashRateMetricSet",
        "table": "raw_crash_rate",
        "metrics": ["crashRate", "crashRate7dUserWeighted", "crashRate28dUserWeighted"],
        "dimensions": ["versionCode", "deviceModel", "apiLevel", "countryCode"],
    },
    {
        "name": "anrRateMetricSet",
        "table": "raw_anr_rate",
        "metrics": ["anrRate", "anrRate7dUserWeighted", "anrRate28dUserWeighted"],
        "dimensions": ["versionCode", "deviceModel", "apiLevel", "countryCode"],
    },
    {
        "name": "stuckBackgroundWakelockRateMetricSet",
        "table": "raw_stuck_bg_wakelock_rate",
        "metrics": [
            "stuckBgWakelockRate",
            "stuckBgWakelockRate7dUserWeighted",
            "stuckBgWakelockRate28dUserWeighted",
        ],
        "dimensions": ["versionCode", "deviceModel", "apiLevel", "countryCode"],
    },
    {
        "name": "excessiveWakeupRateMetricSet",
        "table": "raw_excessive_wakeup_rate",
        "metrics": [
            "excessiveWakeupRate",
            "excessiveWakeupRate7dUserWeighted",
            "excessiveWakeupRate28dUserWeighted",
        ],
        "dimensions": ["versionCode", "deviceModel", "apiLevel", "countryCode"],
    },
    {
        "name": "errorCountMetricSet",
        "table": "raw_error_count",
        # requires reportType as a dimension (API constraint, verified live)
        "metrics": ["errorReportCount", "distinctUsers"],
        # countryCode not supported by errorCountMetricSet (API constraint)
        "dimensions": ["reportType", "versionCode", "deviceModel", "apiLevel"],
    },
    {
        "name": "slowStartRateMetricSet",
        "table": "raw_slow_start_rate",
        "metrics": ["slowStartRate", "slowStartRate7dUserWeighted", "slowStartRate28dUserWeighted"],
        "dimensions": ["versionCode", "startType", "deviceModel", "apiLevel", "countryCode"],
    },
]


@dataclass
class ReportingQueryPayload:
    metric_set_name: str
    metrics: list[str]
    dimensions: list[str]
    date_from: dict  # {"year": int, "month": int, "day": int}
    date_to: dict

    def url(self) -> str:
        return f"{REPORTING_BASE}/apps/{PACKAGE_NAME}/{self.metric_set_name}:query"

    def to_dict(self) -> dict:
        return {
            "timelineSpec": {
                "aggregationPeriod": "DAILY",
                "startTime": self.date_from,
                "endTime": self.date_to,
            },
            "metrics": self.metrics,
            "dimensions": self.dimensions,
        }


def date_str_to_dict(date_str: str) -> dict:
    """Convert 'YYYY-MM-DD' to the dict format the Reporting API expects."""
    y, m, d = date_str.split("-")
    return {"year": int(y), "month": int(m), "day": int(d)}


def flatten_reporting_row(row: dict, metric_set_name: str) -> dict:
    """Flatten one Reporting API row into a single dict of strings for BQ load."""
    out: dict = {"metric_set": metric_set_name}

    start = row.get("startTime", {})
    out["date"] = (
        f"{start.get('year', '')}-{str(start.get('month', '')).zfill(2)}-{str(start.get('day', '')).zfill(2)}"
    )
    out["aggregation_period"] = row.get("aggregationPeriod", "")

    for dim in row.get("dimensions", []):
        out[dim["dimension"]] = dim.get("stringValue", dim.get("int64Value", ""))

    for met in row.get("metrics", []):
        key = met["metric"]
        val = met.get("decimalValue", {}).get("value", "")
        out[key] = str(val)
        # store confidence interval bounds if present
        ci = met.get("decimalValueConfidenceInterval", {})
        if ci:
            out[f"{key}_ci_lower"] = str(ci.get("lowerBound", {}).get("value", ""))
            out[f"{key}_ci_upper"] = str(ci.get("upperBound", {}).get("value", ""))

    return out


def reviews_url() -> str:
    return f"{PUBLISHER_BASE}/applications/{PACKAGE_NAME}/reviews"


def flatten_review(review: dict) -> dict:
    """Flatten one review object into a single dict of strings for BQ load."""
    out: dict = {
        "review_id": review.get("reviewId", ""),
        "author_name": review.get("authorName", ""),
    }
    user_comment = {}
    dev_reply = {}
    for comment in review.get("comments", []):
        if "userComment" in comment:
            user_comment = comment["userComment"]
        if "developerComment" in comment:
            dev_reply = comment["developerComment"]

    out["text"] = user_comment.get("text", "")
    last_mod = user_comment.get("lastModified", {})
    out["last_modified_seconds"] = str(last_mod.get("seconds", ""))
    out["star_rating"] = str(user_comment.get("starRating", ""))
    out["reviewer_language"] = user_comment.get("reviewerLanguage", "")
    out["device"] = user_comment.get("device", "")
    out["android_os_version"] = str(user_comment.get("androidOsVersion", ""))
    out["app_version_code"] = str(user_comment.get("appVersionCode", ""))
    out["app_version_name"] = user_comment.get("appVersionName", "")

    dm = user_comment.get("deviceMetadata", {})
    out["device_product_name"] = dm.get("productName", "")
    out["device_manufacturer"] = dm.get("manufacturer", "")
    out["device_class"] = dm.get("deviceClass", "")
    out["device_ram_mb"] = str(dm.get("ramMb", ""))

    out["developer_reply_text"] = dev_reply.get("text", "")
    last_reply = dev_reply.get("lastModified", {})
    out["developer_reply_seconds"] = str(last_reply.get("seconds", ""))

    return out
