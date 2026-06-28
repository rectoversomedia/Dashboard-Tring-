# Data Catalog: App Store Connect

Status: **CODE DONE - GCP PENDING (2026-06-28)**. Ingestion + dbt models built and tested. GCP infra provisioning is the remaining step.

---

## What is ingested

| Data Type | Raw BQ Table | Source API | Status |
|---|---|---|---|
| Customer reviews | `appstore_raw.raw_reviews` | App Store Connect v1 `/customerReviews` | Built |
| App downloads | `appstore_raw.raw_app_downloads` | Analytics Reports API (App Downloads Standard) | Built |
| Installs / deletions | `appstore_raw.raw_app_installs_deletions` | Analytics Reports API (App Store Installation and Deletion Standard) | Built |
| App sessions | `appstore_raw.raw_app_sessions` | Analytics Reports API (App Sessions Standard) | Built |
| Discovery / engagement | `appstore_raw.raw_app_discovery_engagement` | Analytics Reports API (App Store Discovery and Engagement Standard) | Built |
| Install performance | `appstore_raw.raw_app_install_performance` | Analytics Reports API (App Install Performance) | Built |
| Sales reports | `appstore_raw.raw_sales` | Sales Reports API | Deferred (vendor number needed) |
| Finance reports | `appstore_raw.raw_finance` | Finance Reports API | Deferred (vendor number needed) |

---

## API Overview

| Field | Value |
|---|---|
| Base URL | `https://api.appstoreconnect.apple.com` |
| Auth | ES256 JWT, signed with .p8 private key, 20-min expiry |
| Key ID + Issuer ID | In Secret Manager as `appstore-connect-key` (format: `KEY_ID:ISSUER_ID`) |
| .p8 private key content | In Secret Manager as `appstore-connect-key-p8` |
| App ID | `1350501409` |
| Bundle ID | `com.pegadaian.digital` |

The JWT is generated and cached in `client.py`. It auto-refreshes 60 seconds before the 20-minute Apple-imposed expiry. No manual token management needed.

---

## Analytics Reports API: how the async flow works

The analytics API is not a simple GET. It is a 4-step async process:

1. **POST request** (once, ever): create an ONGOING analytics report request for the app. Returns a `request_id`. Apple generates 156 report types for this request automatically each day.
2. **GET reports** (by request ID): list all 156 reports. The pipeline matches by report name to get the 5 relevant `report_id` values.
3. **GET instances** (by report ID): list available daily data files. Each instance is one day of data Apple has processed.
4. **GET segments** (by instance ID): get pre-signed S3 download URLs. Each URL expires roughly 5 minutes after the GET call.
5. **Download** (via unsigned GET): download the pre-signed URL immediately. Response is gzip-compressed TSV. Decompress with `gzip.open()`.

**Critical design note:** The S3 signed URL expires about 5 minutes after the GET-segments call. The pipeline fetches and downloads each segment immediately within the same loop iteration. Do not batch URLs and download later.

**Active ONGOING request ID:** `77203237-b1c3-40ed-bccf-ce4345c7d5ab` (created 2026-06-26). Override via `APPSTORE_ANALYTICS_REQUEST_ID` env var if the request is ever recreated.

**Analytics download is stateless.** All available instances are downloaded on each run. dbt staging deduplicates by natural key. No state table needed, because the files are small (3-130 KB each).

---

## Reviews API: how it works

- **Endpoint:** `GET /v1/apps/1350501409/customerReviews`
- **Pagination:** follow `links.next` until absent (cursor-based)
- **Incremental:** extractor pulls reviews with `createdDate >= date_from`. Apple returns reviews newest-first. Pagination stops when the next page's oldest review is older than `date_from`.
- **All-time available:** Apple keeps all reviews since app launch (March 2018). Current count: ~11,488+ reviews.

---

## Raw table schemas

### `appstore_raw.raw_reviews`

| Column | Type | Description |
|---|---|---|
| `review_id` | STRING | Apple's unique review identifier |
| `rating` | STRING | Star rating as string (1-5) |
| `title` | STRING | Review title |
| `body` | STRING | Review text |
| `reviewer_nickname` | STRING | Display name |
| `created_date` | STRING | ISO8601 creation date |
| `territory` | STRING | 3-letter country code (e.g. `IDN`) |
| `_ingested_at` | TIMESTAMP | When the row was loaded into BigQuery |
| `_source` | STRING | Always `app_store` |
| `_run_id` | STRING | UUID for this extract run |
| `_extract_from` | DATE | date_from passed to the extract job |
| `_extract_to` | DATE | date_to passed to the extract job |
| `_app_id` | STRING | Always `1350501409` |
| `_platform` | STRING | Always `ios` |

### `appstore_raw.raw_app_downloads`

Columns come from the TSV header (snake-cased). Common columns:

| Column | Type | Description |
|---|---|---|
| `date` | STRING | Report date (YYYY-MM-DD) |
| `download_type` | STRING | e.g. First Time, Redownload |
| `app_version` | STRING | App version string |
| `device` | STRING | Device family |
| `source_type` | STRING | Traffic source |
| `page_type` | STRING | Store page type |
| `territory` | STRING | 2-letter country code |
| `counts` | STRING | Download count (cast to INT64 in staging) |
| `_ingested_at` | TIMESTAMP | Standard metadata |
| `_source` | STRING | Always `app_store` |

### `appstore_raw.raw_app_installs_deletions`

| Column | Type | Description |
|---|---|---|
| `date` | STRING | Report date |
| `event` | STRING | Install or Delete |
| `download_type` | STRING | First Time, Redownload |
| `app_version` | STRING | App version |
| `device` | STRING | Device family |
| `source_type` | STRING | Traffic source |
| `territory` | STRING | Country code |
| `counts` | STRING | Event count |
| `unique_devices` | STRING | Distinct devices |
| `_ingested_at` | TIMESTAMP | Standard metadata |

### `appstore_raw.raw_app_sessions`

| Column | Type | Description |
|---|---|---|
| `date` | STRING | Report date |
| `app_version` | STRING | App version |
| `device` | STRING | Device family |
| `source_type` | STRING | Traffic source |
| `territory` | STRING | Country code |
| `sessions` | STRING | Session count |
| `total_session_duration` | STRING | Total seconds |
| `unique_devices` | STRING | Distinct devices |
| `_ingested_at` | TIMESTAMP | Standard metadata |

### `appstore_raw.raw_app_discovery_engagement`

| Column | Type | Description |
|---|---|---|
| `date` | STRING | Report date |
| `event` | STRING | Impression, Page view, or Tap |
| `page_type` | STRING | Store page type |
| `source_type` | STRING | Traffic source |
| `engagement_type` | STRING | Engagement category |
| `device` | STRING | Device family |
| `territory` | STRING | Country code |
| `counts` | STRING | Event count |
| `unique_counts` | STRING | Distinct user count |
| `_ingested_at` | TIMESTAMP | Standard metadata |

### `appstore_raw.raw_app_install_performance`

| Column | Type | Description |
|---|---|---|
| `date` | STRING | Report date |
| `download_type` | STRING | First Time, Redownload |
| `install_status` | STRING | e.g. Succeeded |
| `install_package_type` | STRING | On-Demand or App Clip |
| `device` | STRING | Device family |
| `territory` | STRING | Country code |
| `counts` | STRING | Install count |
| `avg_install_duration` | STRING | Average seconds to install |
| `_ingested_at` | TIMESTAMP | Standard metadata |

> All raw columns except `_ingested_at` and other `_` prefixed metadata columns are STRING. Casting to correct types happens in dbt staging models.

---

## dbt Models

### Staging (`appstore_staging` dataset)

| Model | Source table | Dedup key | Notes |
|---|---|---|---|
| `stg_appstore_reviews` | `raw_reviews` | `review_id` | Casts `created_date` to TIMESTAMP; derives `review_date` (DATE) |
| `stg_appstore_app_downloads` | `raw_app_downloads` | date + download_type + app_version + device + source_type + page_type + territory | Casts `counts` to INT64 |
| `stg_appstore_app_installs_deletions` | `raw_app_installs_deletions` | date + event + download_type + app_version + device + source_type + territory | Casts `counts`, `unique_devices` to INT64 |
| `stg_appstore_app_sessions` | `raw_app_sessions` | date + app_version + device + source_type + territory | Casts `sessions`, `total_session_duration`, `unique_devices` to INT64 |
| `stg_appstore_app_discovery_engagement` | `raw_app_discovery_engagement` | date + event + page_type + source_type + engagement_type + device + territory | Casts `counts`, `unique_counts` to INT64 |
| `stg_appstore_app_install_performance` | `raw_app_install_performance` | date + download_type + install_status + install_package_type + device + territory | Casts `counts` to INT64; `avg_install_duration` to FLOAT64 |

All staging models deduplicate using `qualify row_number() over (partition by <dedup key> order by _ingested_at desc) = 1`.

### Mart (`appstore_mart` dataset)

| Model | Sources | Partition | Key metrics |
|---|---|---|---|
| `mart_appstore_acquisition` | stg downloads + stg discovery engagement | DATE(`date`) | app_units (first_time + redownloads), impressions, page_views, conversion_rate |
| `mart_appstore_engagement` | stg installs_deletions + stg sessions | DATE(`date`) | installs, deletions, sessions, avg_session_duration, sessions_per_device |
| `mart_appstore_reviews` | stg reviews | DATE(`review_date`) | All review fields + is_negative_review (rating <= 2), clustered by rating |

`conversion_rate = safe_divide(first_time_downloads, nullif(impressions, 0))`

`avg_session_duration = safe_divide(total_session_duration, nullif(sessions, 0))`

`sessions_per_device = safe_divide(sessions, nullif(unique_devices, 0))`

---

## Known Behaviors and Limitations

- **Analytics API is async:** Apple generates daily report files. New ONGOING instances appear 2-3 days after the event date (data lags). dbt freshness thresholds use warn 49h, error 73h to account for this.
- **Reviews are incremental:** `--from` controls the date threshold. Reviews are deduplicated in staging by `review_id`. Safe to re-run.
- **All reviews available:** Tring! launched March 2018. Run `--from 2018-01-01` for full backfill. Current count 11,488+.
- **Analytics download is stateless:** No state table. All available instances downloaded every run. dbt staging deduplicates. Small files (3-130 KB), so this is fast.
- **ONGOING report only covers data from request creation date onward:** The ONGOING analytics report request was created 2026-06-28. It returns instances from that date forward -- not historical data. Passing `--from 2026-01-01` does NOT backfill Jan-Jun; Apple API ignores date_from/date_to for analytics reports. The date params are metadata only. Historical data before 2026-06-28 requires ONE_TIME_SNAPSHOT (see below).
- **ONGOING request ID:** `77203237-b1c3-40ed-bccf-ce4345c7d5ab`. If this request is ever deleted and recreated, update `APPSTORE_ANALYTICS_REQUEST_ID` env var on the Cloud Run Job.
- **156 reports total, 5 used:** The other 151 are `FRAMEWORK_USAGE` category (ARKit, Metal, Bluetooth, etc.) not relevant to the product dashboard.
- **ONE_TIME_SNAPSHOT backfill (BLOCKED - needs client action):** Apple allows 1 snapshot per month per app to load historical analytics (2024-2025). A snapshot request already exists in Apple's system (created June 2026) but the request ID was not captured. Apple does not support GET collection for `analyticsReportRequests`, so we cannot retrieve or delete the existing request via API. To unblock: ask the App Store Connect account holder (Tri Bayu / Pegadaian) to open appstoreconnect.apple.com, go to Apps, select Tring!, open Analytics, find "Data Requests" or "Report Requests", and share the UUID of the ONE_TIME_SNAPSHOT entry. Once we have the ID, we can check if instances are ready and download them. If the UI shows no snapshot, it may have expired and we can create a new one via the API (1 per month limit resets monthly).
- **Sales/Finance:** Deferred. Requires vendor number from App Store Connect > Agreements, Tax, and Banking.
- **JWT auto-refresh:** `client.py` caches the token and refreshes 60 seconds before the 20-minute expiry. No manual intervention needed.
- **TSV column names with dashes:** Apple TSV headers like `Pre-Order` contain dashes. `endpoints.py _snake()` converts these to underscores (`pre_order`). Raw BQ data ingested before 2026-06-28 has the old column name `pre-order`; `stg_appstore_app_downloads` uses `coalesce(pre_order, \`pre-order\`)` to handle both.
- **New columns from Apple are automatically dropped at ingest:** `bq_loader.py` fetches the existing BQ table schema before loading and filters out any columns not already in the table. Pipeline won't fail when Apple adds new TSV fields — they're silently ignored with a warning log. To capture a new column, update BQ schema + staging model + rebuild dbt. See runbook.md §11.

---

## GCP Resources

| Resource | Description |
|---|---|
| SA `sa-extract-app-store` | Runtime identity for the extract job |
| IAM `roles/bigquery.dataEditor` | Write to appstore_raw dataset |
| IAM `roles/bigquery.jobUser` | Run BQ load jobs |
| IAM `roles/secretmanager.secretAccessor` on `appstore-connect-key` | Read KEY_ID + ISSUER_ID |
| IAM `roles/secretmanager.secretAccessor` on `appstore-connect-key-p8` | Read .p8 private key content |
| Secret `appstore-connect-key` | Format: `KEY_ID:ISSUER_ID` |
| Secret `appstore-connect-key-p8` | Raw .p8 PEM content |
| BQ dataset `appstore_raw` | Raw layer, `asia-southeast2` |
| BQ dataset `appstore_staging` | Staging views, `asia-southeast2` |
| BQ dataset `appstore_mart` | Mart tables, `asia-southeast2` |
| Cloud Run Job `extract-app-store` | Runs `python -m tring_ingest --source app_store` |

Provision commands are in `docs/gcp-setup.md` (sections 2, 3, 4, 6, 8). Shortcut: `make create-app-store PROJECT=...`
