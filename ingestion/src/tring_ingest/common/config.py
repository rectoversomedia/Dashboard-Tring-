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
