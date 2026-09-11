import os

GCP_PROJECT = os.environ.get("GCP_PROJECT")  # validated in cli.py before anything runs
REGION = os.environ.get("REGION", "asia-southeast2")

BQ_DATASET_RAW_APPSFLYER = os.environ.get("BQ_DATASET_RAW", "appsflyer_raw")
BQ_DATASET_STAGING_APPSFLYER = "appsflyer_staging"
BQ_DATASET_MART_APPSFLYER = "appsflyer_mart"

APPSFLYER_BASE_URL = "https://hq1.appsflyer.com"
APPSFLYER_SECRET_NAME = os.environ.get("APPSFLYER_SECRET_NAME", "appsflyer-api-token")

# (app_id, platform) - we pull every endpoint once per pair
APPSFLYER_APP_IDS = [
    ("com.pegadaiandigital", "android"),
    ("id1350501409", "ios"),
]

APPSFLYER_TIMEZONE = "Asia/Jakarta"

# Rows requested per raw-data report. The API defaults to 200,000 and answers an over-cap
# window with only its MOST RECENT rows  -  no error, no warning. That silently reduced a full
# Android day to its last ~3.5 hours (verified 2026-07-25: a date-only request returned exactly
# 200,000 rows spanning only 20:00-23:59). AppsFlyer documents 1M rows per request as the
# ceiling, and this parameter is accepted by the API, so asking for 1M should cover a whole day
# in one request. NOT yet proven to actually lift the cap  -  see APPSFLYER_CHUNK_HOURS.
APPSFLYER_MAXIMUM_ROWS = int(os.environ.get("APPSFLYER_MAXIMUM_ROWS", "1000000"))

# Row ceiling of a single raw-data report response, used to flag pulls that came back truncated.
APPSFLYER_RAW_REPORT_ROW_CAP = 200_000

# Splits each day into slices of this many hours for in-app events, one request per slice.
# DISABLED (0) on purpose: AppsFlyer also caps the NUMBER of report downloads per day per app,
# and hourly slicing blows through it  -  verified 2026-07-25, the 11th in-app-events pull of the
# day returned HTTP 400 "You've reached your maximum number of in-app event reports that can be
# downloaded today for this app". Only turn this on if APPSFLYER_MAXIMUM_ROWS turns out not to
# lift the row cap, and then keep slices few enough to stay inside the daily download quota
# (roughly 24 per report type per account, so ~12 per app across the two apps).
APPSFLYER_CHUNK_HOURS = int(os.environ.get("APPSFLYER_CHUNK_HOURS", "0"))

# master-agg params, taken from the working postman collection
APPSFLYER_MASTER_AGG_GROUPINGS = "pid,c,install_time,geo"
APPSFLYER_MASTER_AGG_KPIS = "impressions,clicks,installs,cost"
APPSFLYER_MASTER_AGG_CURRENCY = "USD"

# MoEngage
BQ_DATASET_RAW_MOENGAGE = os.environ.get("BQ_DATASET_RAW_MOENGAGE", "moengage_raw")
BQ_DATASET_STAGING_MOENGAGE = "moengage_staging"
BQ_DATASET_MART_MOENGAGE = "moengage_mart"

MOENGAGE_BASE_URL = "https://api-01.moengage.com"
MOENGAGE_SECRET_NAME = os.environ.get("MOENGAGE_SECRET_NAME", "moengage-api-creds")

# confirmed with live test; client to confirm final values before go-live
MOENGAGE_ATTRIBUTION_TYPE = os.environ.get("MOENGAGE_ATTRIBUTION_TYPE", "VIEW_THROUGH")
MOENGAGE_METRIC_TYPE = os.environ.get("MOENGAGE_METRIC_TYPE", "TOTAL")

# Play Console
BQ_DATASET_RAW_PLAY_CONSOLE = os.environ.get("BQ_DATASET_RAW_PLAY_CONSOLE", "play_raw")
BQ_DATASET_STAGING_PLAY_CONSOLE = "play_staging"
BQ_DATASET_MART_PLAY_CONSOLE = "play_mart"

# SA JSON stored in Secret Manager as a raw JSON string
PLAY_CONSOLE_SECRET_NAME = os.environ.get("PLAY_CONSOLE_SECRET_NAME", "play-console-sa-key")

# Play Console GCS stats (install/uninstall/store_performance/crashes)
GCS_BUCKET_PLAY_CONSOLE = os.environ.get(
    "GCS_BUCKET_PLAY_CONSOLE", "pubsite__rev_00060605014151750029"
)
# Must match endpoints.PACKAGE_NAME -- the bucket holds 21 Pegadaian packages and
# co.id.pegadaian.aralia is a different, near-empty app (52 installs/day vs 17k).
PLAY_CONSOLE_PACKAGE_NAME = os.environ.get("PLAY_CONSOLE_PACKAGE_NAME", "com.pegadaiandigital")

# App Store Connect
BQ_DATASET_RAW_APPSTORE = os.environ.get("BQ_DATASET_RAW_APPSTORE", "appstore_raw")
BQ_DATASET_STAGING_APPSTORE = "appstore_staging"
BQ_DATASET_MART_APPSTORE = "appstore_mart"

# Secret format: "KEY_ID:ISSUER_ID:P8_CONTENT" (single secret, all creds concatenated)
APPSTORE_SECRET_NAME = os.environ.get("APPSTORE_SECRET_NAME", "appstore-connect-key")
APPSTORE_APP_ID = os.environ.get("APPSTORE_APP_ID", "1350501409")
