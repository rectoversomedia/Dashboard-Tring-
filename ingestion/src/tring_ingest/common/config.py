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
PLAY_CONSOLE_PACKAGE_NAME = os.environ.get("PLAY_CONSOLE_PACKAGE_NAME", "co.id.pegadaian.aralia")

# App Store Connect
BQ_DATASET_RAW_APPSTORE = os.environ.get("BQ_DATASET_RAW_APPSTORE", "appstore_raw")
BQ_DATASET_STAGING_APPSTORE = "appstore_staging"
BQ_DATASET_MART_APPSTORE = "appstore_mart"

# Secret format: "KEY_ID:ISSUER_ID:P8_CONTENT" (single secret, all creds concatenated)
APPSTORE_SECRET_NAME = os.environ.get("APPSTORE_SECRET_NAME", "appstore-connect-key")
APPSTORE_APP_ID = os.environ.get("APPSTORE_APP_ID", "1350501409")
