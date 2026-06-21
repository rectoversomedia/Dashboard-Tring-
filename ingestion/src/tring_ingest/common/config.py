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
