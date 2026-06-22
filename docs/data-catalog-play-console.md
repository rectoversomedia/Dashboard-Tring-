# Data Catalog: Play Console Raw Layer

Status: **FULLY DONE (2026-06-22)** - ingestion code, GCP infra, dbt models, pipeline.yaml, E2E all verified. Raw: 3,580 rows across 7 tables. dbt: PASS=140 WARN=0 ERROR=0.

---

## Overview

| Data Type | BQ Table | Source API | Columns |
|---|---|---|---|
| Crash rate | `play_raw.raw_crash_rate` | Play Developer Reporting API | 3 metrics + CI bounds + versionCode + 8 meta |
| ANR rate | `play_raw.raw_anr_rate` | Play Developer Reporting API | 3 metrics + CI bounds + versionCode + 8 meta |
| Stuck background wakelock rate | `play_raw.raw_stuck_bg_wakelock_rate` | Play Developer Reporting API | 3 metrics + versionCode + 8 meta (no CI) |
| Excessive wakeup rate | `play_raw.raw_excessive_wakeup_rate` | Play Developer Reporting API | 3 metrics + versionCode + 8 meta (no CI) |
| Error count | `play_raw.raw_error_count` | Play Developer Reporting API | 2 metrics + reportType + versionCode + 8 meta |
| Slow start rate | `play_raw.raw_slow_start_rate` | Play Developer Reporting API | 3 metrics + versionCode + startType + 8 meta (no CI) |
| Reviews | `play_raw.raw_reviews` | Android Publisher API | 16 source + 8 meta |

---

## API Details

| Field | Value |
|---|---|
| Reporting API base URL | `https://playdeveloperreporting.googleapis.com/v1beta1` |
| Publisher API base URL | `https://androidpublisher.googleapis.com/androidpublisher/v3` |
| Auth | OAuth2 via Service Account JSON (google-auth library) |
| Credentials secret | `play-console-sa-key` (full SA key JSON stored as raw string) |
| Package name | `com.pegadaiandigital` |
| Format | JSON |

### Required API scopes

The service account needs these OAuth scopes (set in `client.py`):
- `https://www.googleapis.com/auth/playdeveloperreporting`
- `https://www.googleapis.com/auth/androidpublisher`

### Service account used

Two GCP projects are involved here, do not mix them up:

1. **The data pipeline project** (`$PROJECT`, the one you deploy everything to). It holds the `play-console-sa-key` secret and the runtime SA `sa-extract-play-console`.
2. **The Play Console source project** (`pgd-prd-digital-rating-tring`). It owns the SA `dashboard-monitoring-aiinsight` that already has Play Console API access. You do NOT create a new SA for Play Console access; you reuse this existing one by storing its key JSON in the secret.

| Field | Value |
|---|---|
| Play Console SA email | `dashboard-monitoring-aiinsight@pgd-prd-digital-rating-tring.iam.gserviceaccount.com` |
| Project that owns that SA | `pgd-prd-digital-rating-tring` (the Play Console source project) |
| Secret name (in your pipeline project) | `play-console-sa-key` |
| Key file (gitignored, kept only at repo root, never committed) | the SA key JSON downloaded from the source project |

The Cloud Run Job runtime SA (`sa-extract-play-console@$PROJECT.iam.gserviceaccount.com`) only needs BQ + Secret Manager access in your pipeline project. The Play Console API auth is handled separately, by the SA key JSON loaded from Secret Manager at runtime.

> **How to obtain the key JSON (do this before creating the secret):** You need a key for the `dashboard-monitoring-aiinsight` SA in `pgd-prd-digital-rating-tring`. If you have IAM access to that project: GCP Console > IAM & Admin > Service Accounts > select the SA > Keys > Add Key > Create new key > JSON, then download it. If you do NOT have access to that project (likely, it is a separate production project owned by another team), ask whoever owns `pgd-prd-digital-rating-tring` to generate the JSON key and send it to you over a secure channel (a secret-sharing tool, never email or chat). The SA must already have Play Console access granted in the Google Play Console; that grant is one-time and is assumed already done.

---

## Metric Sets (Play Developer Reporting API)

All metric set endpoints are POST `.../{metricSetName}:query` with a JSON body specifying `timelineSpec`, `metrics`, and `dimensions`. Results are DAILY aggregated.

> **Adding another metric set:** append an entry to `METRIC_SETS` in `ingestion/src/tring_ingest/sources/play_console/endpoints.py`, then rebuild the image. Step by step in `docs/adding-endpoints.md` (section B).

### raw_crash_rate

- **Endpoint:** `/apps/com.pegadaiandigital/crashRateMetricSet:query`
- **Dimensions:** `versionCode`
- **Metrics:** `crashRate`, `crashRate7dUserWeighted`, `crashRate28dUserWeighted`

| Column | Type in raw (STRING) | Description |
|---|---|---|
| metric_set | STRING | Always `crashRateMetricSet` |
| date | STRING (YYYY-MM-DD) | Start date of the daily window |
| aggregation_period | STRING | Always `DAILY` |
| versionCode | STRING | App version code |
| crashRate | STRING (decimal) | Distinct users who experienced a crash / total daily active users |
| crashRate7dUserWeighted | STRING (decimal) | 7-day user-weighted rolling average |
| crashRate28dUserWeighted | STRING (decimal) | 28-day user-weighted rolling average |
| crashRate_ci_lower | STRING (decimal) | Lower bound of 95% confidence interval |
| crashRate_ci_upper | STRING (decimal) | Upper bound of 95% confidence interval |
| (same _ci_lower/_ci_upper for 7d and 28d variants) | | |

### raw_anr_rate

- **Endpoint:** `/apps/com.pegadaiandigital/anrRateMetricSet:query`
- **Dimensions:** `versionCode`
- **Metrics:** `anrRate`, `anrRate7dUserWeighted`, `anrRate28dUserWeighted`

Same structure as `raw_crash_rate` but with `anr*` column names. **Includes CI bounds** (`anrRate_ci_lower`, `anrRate_ci_upper`); the ANR rate metric set returns confidence interval data, same as crash rate.

### raw_stuck_bg_wakelock_rate

- **Endpoint:** `/apps/com.pegadaiandigital/stuckBackgroundWakelockRateMetricSet:query`
- **Dimensions:** `versionCode`
- **Metrics:** `stuckBgWakelockRate`, `stuckBgWakelockRate7dUserWeighted`, `stuckBgWakelockRate28dUserWeighted`

Same structure as `raw_anr_rate` with `stuckBgWakelockRate*` column names. **No CI bounds.**

### raw_excessive_wakeup_rate

- **Endpoint:** `/apps/com.pegadaiandigital/excessiveWakeupRateMetricSet:query`
- **Dimensions:** `versionCode`
- **Metrics:** `excessiveWakeupRate`, `excessiveWakeupRate7dUserWeighted`, `excessiveWakeupRate28dUserWeighted`

Same structure as `raw_anr_rate` with `excessiveWakeupRate*` column names. **No CI bounds.**

### raw_error_count

- **Endpoint:** `/apps/com.pegadaiandigital/errorCountMetricSet:query`
- **Dimensions:** `reportType`, `versionCode`
- **Metrics:** `errorReportCount`, `distinctUsers`

> `reportType` is a REQUIRED dimension for `errorCountMetricSet` (API constraint, verified live). Omitting it returns a 400 error.

| Column | Type in raw (STRING) | Description |
|---|---|---|
| metric_set | STRING | Always `errorCountMetricSet` |
| date | STRING (YYYY-MM-DD) | Start date of the daily window |
| aggregation_period | STRING | Always `DAILY` |
| reportType | STRING | Type of error report: `ANR` or `CRASH` |
| versionCode | STRING | App version code |
| errorReportCount | STRING (integer) | Total number of error reports |
| distinctUsers | STRING (integer) | Number of distinct users affected |

No confidence interval columns (this metric set does not return CI bounds).

### raw_slow_start_rate

- **Endpoint:** `/apps/com.pegadaiandigital/slowStartRateMetricSet:query`
- **Dimensions:** `versionCode`, `startType`
- **Metrics:** `slowStartRate`, `slowStartRate7dUserWeighted`, `slowStartRate28dUserWeighted`

| Column | Type in raw (STRING) | Description |
|---|---|---|
| metric_set | STRING | Always `slowStartRateMetricSet` |
| date | STRING (YYYY-MM-DD) | Start date of the daily window |
| aggregation_period | STRING | Always `DAILY` |
| versionCode | STRING | App version code |
| startType | STRING | `COLD`, `WARM`, or `HOT` |
| slowStartRate | STRING (decimal) | Fraction of sessions with slow start time |
| slowStartRate7dUserWeighted | STRING (decimal) | 7-day user-weighted rolling average |
| slowStartRate28dUserWeighted | STRING (decimal) | 28-day user-weighted rolling average |

> No CI bounds for slow start rate (API does not return confidence interval data for this metric set, verified live 2026-06-22).

---

## Reviews (Android Publisher API)

- **Endpoint:** `/applications/com.pegadaiandigital/reviews`
- **Method:** GET with `maxResults=100`, paginated via `tokenPagination.nextPageToken`
- **BQ table:** `play_raw.raw_reviews`
- **Note:** Not date-scoped. The API always returns the current state of all reviews (no start/end date filter). Run periodically to capture new and updated reviews.

| Column | Type in raw (STRING) | Description |
|---|---|---|
| review_id | STRING | Unique review identifier |
| author_name | STRING | Display name of the reviewer |
| text | STRING | Review text body |
| last_modified_seconds | STRING (Unix epoch) | When the review was last modified |
| star_rating | STRING (1-5) | Star rating given by the reviewer |
| reviewer_language | STRING | BCP-47 language tag (e.g. `id`, `en`) |
| device | STRING | Device code name (e.g. `a16`) |
| android_os_version | STRING (integer) | Android API level |
| app_version_code | STRING (integer) | App version code at time of review |
| app_version_name | STRING | App version name at time of review |
| device_product_name | STRING | Device marketing name (e.g. `Galaxy A16`) |
| device_manufacturer | STRING | Device manufacturer (e.g. `Samsung`) |
| device_class | STRING | `FORM_FACTOR_PHONE`, `FORM_FACTOR_TABLET`, etc. |
| device_ram_mb | STRING (integer) | Device RAM in MB |
| developer_reply_text | STRING | Developer reply text (empty string if no reply) |
| developer_reply_seconds | STRING (Unix epoch) | When the developer replied (empty string if no reply) |

---

## Metadata Columns (all tables)

All raw tables include 8 standard metadata columns appended by the loader:

| Column | Type | Description |
|---|---|---|
| _ingested_at | TIMESTAMP | When the row was loaded into BigQuery |
| _source | STRING | Always `play_console` |
| _run_id | STRING | UUID identifying this extract run |
| _extract_from | DATE | date_from passed to the extract job |
| _extract_to | DATE | date_to passed to the extract job |
| _schema_flag | STRING | Non-empty if new columns appeared vs previous run (schema drift detection) |
| _app_id | STRING | Not used for Play Console (empty string) |
| _platform | STRING | Not used for Play Console (empty string) |

---

## GCP Infra (DONE - provisioned and E2E verified 2026-06-22 in the consultant dev project; reproduce in the client project with the commands below)

| Resource | Status |
|---|---|
| SA `sa-extract-play-console` (runtime) | DONE |
| IAM: bigquery.dataEditor + jobUser | DONE |
| Secret `play-console-sa-key` (client prod SA key JSON, version 2 active) | DONE |
| IAM: secretmanager.secretAccessor on play-console-sa-key | DONE |
| BQ datasets: play_raw, play_staging, play_mart | DONE |
| Cloud Run Job: extract-play-console | DONE |
| dbt models (7 staging + 2 mart) | DONE |
| pipeline.yaml (3 parallel branches) | DONE |
| Workflow deployed (revision 000012-e43) | DONE |

Commands used (reference for reproducing in client prod):

```bash
export PROJECT=YOUR_GCP_PROJECT

# Runtime SA
gcloud iam service-accounts create sa-extract-play-console \
  --display-name="Play Console extractor runtime" --project=$PROJECT

# IAM
gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:sa-extract-play-console@${PROJECT}.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor"
gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:sa-extract-play-console@${PROJECT}.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"

# Secret - store Play Console SA key JSON (from client's prod project)
# The SA must already have Play Console access granted via Google Play Console UI
gcloud secrets create play-console-sa-key --replication-policy="automatic" --project=$PROJECT
cat play-console-sa-key.json | gcloud secrets versions add play-console-sa-key \
  --data-file=- --project=$PROJECT
rm play-console-sa-key.json   # delete local copy immediately

gcloud secrets add-iam-policy-binding play-console-sa-key \
  --member="serviceAccount:sa-extract-play-console@${PROJECT}.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" --project=$PROJECT

# BQ datasets
bq --project_id=$PROJECT mk --location=asia-southeast2 play_raw
bq --project_id=$PROJECT mk --location=asia-southeast2 play_staging
bq --project_id=$PROJECT mk --location=asia-southeast2 play_mart

# Cloud Run Job
REGISTRY=asia-southeast2-docker.pkg.dev
gcloud run jobs create extract-play-console \
  --image=${REGISTRY}/${PROJECT}/tring-service/ingestion:latest \
  --region=asia-southeast2 \
  --service-account=sa-extract-play-console@${PROJECT}.iam.gserviceaccount.com \
  --set-env-vars="GCP_PROJECT=${PROJECT},BQ_DATASET_RAW_PLAY_CONSOLE=play_raw,REGION=asia-southeast2" \
  --set-secrets="PLAY_CONSOLE_SA_KEY=play-console-sa-key:latest" \
  --command=python \
  --args="-m,tring_ingest,--source,play_console" \
  --memory=2Gi --cpu=1 \
  --max-retries=0 \
  --project=$PROJECT
```

E2E verified 2026-06-22: 3,580 raw rows across 7 tables. dbt PASS=140 WARN=0 ERROR=0.

---

## dbt Models

### Staging (play_staging dataset)

Views. Dedup by natural key on latest `_ingested_at`. All STRING fields cast to typed columns.

| Model | Grain | Key columns |
|---|---|---|
| `stg_play_console_crash_rate` | date x version_code | crash_rate, crash_rate_7d, crash_rate_28d, crash_rate_ci_lower/upper |
| `stg_play_console_anr_rate` | date x version_code | anr_rate, anr_rate_7d, anr_rate_28d, anr_rate_ci_lower/upper |
| `stg_play_console_stuck_bg_wakelock_rate` | date x version_code | stuck_bg_wakelock_rate, _7d, _28d |
| `stg_play_console_excessive_wakeup_rate` | date x version_code | excessive_wakeup_rate, _7d, _28d |
| `stg_play_console_error_count` | date x report_type x version_code | error_report_count, distinct_users |
| `stg_play_console_slow_start_rate` | date x version_code x start_type | slow_start_rate, _7d, _28d |
| `stg_play_console_reviews` | review_id | star_rating, last_modified_at_ts, developer_reply_text, review_text |

> Only `stg_play_console_crash_rate` and `stg_play_console_anr_rate` have CI columns. The other metric sets (stuck bg wakelock, excessive wakeup, error count, slow start) do not return CI bounds (verified live against the API and the raw BQ table schemas 2026-06-22).

> `has_developer_reply` is a mart-only computed column (`mart_play_console_reviews`), not in staging. Staging passes through `developer_reply_text` as-is; the mart derives the flag from it.

> `stg_play_console_reviews` does not include `_extract_from`/`_extract_to` meta columns. Reviews are not date-scoped (the API returns all reviews regardless of date range), so these columns have no meaningful value for reviews and are intentionally omitted.

### Mart (play_mart dataset)

Tables. Full refresh each run. Partitioned + clustered for query efficiency.

| Model | Grain | Partition | Description |
|---|---|---|---|
| `mart_play_console_app_health` | date x version_code | date | FULL OUTER JOIN of crash/ANR/wakelock/wakeup rates in one wide table. CI bounds included for crash rate and ANR rate. |
| `mart_play_console_reviews` | review_id | review_date | All reviews with `has_developer_reply` and `is_negative_review` flags |

---

## Known Behaviors and Limitations

- **Metric set data lag:** Play Developer Reporting API data lags by ~2-3 days. Querying today's data returns nothing; always query with a date_to at least 3 days in the past for complete data.
- **Reviews not date-scoped:** The reviews endpoint returns all reviews regardless of date range. Re-running produces duplicates in raw; staging deduplicates by `review_id` and `last_modified_seconds`.
- **errorCountMetricSet requires reportType dimension:** Omitting `reportType` returns HTTP 400. This is an API constraint, not optional.
- **Confidence intervals only for crash rate and ANR rate:** Only `crashRateMetricSet` and `anrRateMetricSet` return CI bounds in practice (verified live and against the raw BQ table schemas 2026-06-22). Stuck bg wakelock, excessive wakeup, and slow start rate do NOT return CI columns. `errorCountMetricSet` also has no CI. The ingestion code handles both cases (only writes CI columns when the API returns them), so raw table schemas differ per metric set.
- **SA key rotation:** Unlike API tokens, the Play Console SA key is a full JSON file. Follow the rotation procedure in `docs/runbook.md` section 7 carefully (generate new key, add to Secret Manager, delete old key from GCP IAM).
