# Data Catalog: MoEngage Raw Layer

Reference date for row counts: **2026-06-22** (validated from E2E run: 599 campaigns, 4712 stats rows).

---

## Overview

| Endpoint | BQ Table | Rows (one-time full pull) | Columns |
|---|---|---|---|
| `/core-services/v1/campaigns/search` (POST) | `moengage_raw.raw_campaigns` | 599 | 9 source + 7 meta |
| `/core-services/v1/campaign-stats` (POST) | `moengage_raw.raw_campaign_stats` | 4712 | 15 source + 7 meta |

> `raw_campaign_stats` rows = campaigns x platforms x variations x locale x date windows. 599 campaigns x ~8 platforms/variations average = 4712.

---

## API Details

| Field | Value |
|---|---|
| Base URL | `https://api-01.moengage.com` |
| Auth | HTTP Basic (`WORKSPACE_ID:API_KEY`) + header `MOE-APPKEY: WORKSPACE_ID` |
| Credentials secret | `moengage-api-creds` (format: `WORKSPACE_ID:API_KEY`, colon-delimited) |
| Format | JSON |

---

## Endpoints

### 1. /campaigns/search

- **URL:** `/core-services/v1/campaigns/search`
- **Method:** POST (body: `request_id`, `campaign_fields`, `page`, `limit`)
- **Pagination:** page-based via `page` field in request body (not query param)
- **BQ table:** `moengage_raw.raw_campaigns`
- **Response shape:** bare `list[dict]` (NOT wrapped - no outer key)
- **Pagination:** page-based. Total 599 campaigns; 40 pages at limit=15.
- **Rate limit:** no documented per-minute limit; use small sleep between pages to be safe

**Source columns (9):**

| Column | Type in raw (STRING) | Description |
|---|---|---|
| campaign_id | STRING | Unique campaign identifier |
| channel | STRING | Delivery channel: PUSH / EMAIL / SMS / IN_APP / CARDS / CONNECTOR / ON_SITE |
| status | STRING | Campaign status: ACTIVE / INACTIVE / DRAFT / COMPLETED |
| campaign_delivery_type | STRING | SCHEDULED / TRIGGERED / PERIODIC |
| created_at | STRING (ISO timestamp) | Campaign creation time |
| sent_time | STRING (ISO timestamp) | Last send time (null if never sent) |
| basic_details | STRING (Python dict repr) | Campaign name, tags, app_id - stored as opaque string |
| segmentation_details | STRING (Python dict repr) | Audience segmentation config - opaque string |
| conversion_goal_details | STRING (Python dict repr) | Conversion goal config - null/`{}` if not configured |

> **Note on nested fields:** `basic_details`, `segmentation_details`, `conversion_goal_details` are stored via Python `str(dict)`, which uses single quotes - NOT valid JSON. Cannot use BigQuery `json_value()` on these. Access campaign name from `basic_details` requires string parsing or re-extraction at the source level.

---

### 2. /campaign-stats

- **URL:** `/core-services/v1/campaign-stats`
- **Method:** POST
- **Body:** `{"campaign_ids": [...], "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD", "attribution_type": "...", "metric_type": "...", "request_id": "..."}`
- **BQ table:** `moengage_raw.raw_campaign_stats`
- **Response shape:** wrapped dict; the per-campaign stats live under the `data` key (`resp.json()["data"]`, keyed by campaign_id). The dict also carries `response_id`, `total_campaigns`, `current_page`, `total_pages`.
- **API constraints:**
  - Max **10 campaign IDs per request** (hard limit)
  - Max **30-day date window** per request
  - Double-chunking required: chunk campaigns (10/batch) AND chunk date range (30-day windows)
- **Chunking in practice:** 599 campaigns / 10 = 60 chunks per date window

**Source columns (15):**

| Column | Type in raw (STRING) | Description |
|---|---|---|
| campaign_id | STRING | Campaign identifier (matches raw_campaigns.campaign_id) |
| platform | STRING | ANDROID / IOS / UNKNOWN / ALL_PLATFORMS |
| locale | STRING | Language/locale code (e.g. `en`, `id`) |
| variation | STRING | `all_variations` (aggregate) or specific A/B variation name |
| sent | STRING (INT64) | Messages sent to device |
| impression | STRING (INT64) | Push shown on device (open proxy - no native open event for push) |
| click | STRING (INT64) | Push tapped by user |
| ctr | STRING (FLOAT64) | Click-through rate as **0-100 percentage** (e.g. 25.0 = 25%) - NOT ratio |
| attempted | STRING (INT64) | Messages attempted to send (including failed) |
| failed | STRING (INT64) | Messages that failed to deliver |
| device_start | STRING (INT64) | App opens attributed to this campaign |
| delivery_rate | STRING (FLOAT64) | sent / attempted (API-provided) |
| sent_rate | STRING (FLOAT64) | Proportion of audience reached (API-provided) |
| failure_rate | STRING (FLOAT64) | failed / attempted (API-provided) |
| delivery_funnel | STRING (Python dict repr) | Delivery funnel breakdown - opaque string |
| conversion_goal_stats | STRING (Python dict repr) | Conversion goal metrics - `'{}'` if no goal configured |

> **CTR scale warning:** `ctr` is on a 0-100 percentage scale (e.g. `25.0` means 25%). This differs from AppsFlyer where ratios are 0-1. Do NOT compare CTR values between the two sources directly. CTR can exceed 100 when `sent=0` but `click>0` - this is a MoEngage data edge case, not a pipeline bug.

> **ALL_PLATFORMS:** A valid MoEngage platform value representing a cross-platform aggregate row. Appears alongside per-platform rows. Filter to `variation = 'all_variations'` and the platform you need to avoid double-counting.

> **impression as open proxy:** Push notifications have no native open event. MoEngage records `impression` when the notification appears on the device screen. In staging and mart layers, `impression` is relabeled `open_proxy` to make this semantic explicit.

> **delivery_rate can exceed 1.0:** MoEngage can show `sent > attempted` in edge cases (timing between SDK acknowledgement and attempt count). `delivery_rate` in mart is recomputed via `safe_divide(sent, attempted)` with no upper cap - values slightly above 1.0 are expected and not a data error.

---

## Meta columns (both tables, 7)

All meta columns are injected by the ingestion layer at load time.

| Column | Type | Description |
|---|---|---|
| `_ingested_at` | TIMESTAMP | When this row was written to BQ |
| `_source` | STRING | Always `moengage` |
| `_run_id` | STRING | UUID identifying the extract run |
| `_extract_from` | STRING (DATE) | Start of date window passed to the extractor |
| `_extract_to` | STRING (DATE) | End of date window |
| `_app_id` | STRING | Empty string for MoEngage (workspace-level, not app-level) |
| `_platform` | STRING | Empty string for MoEngage (platform comes from API response column) |

---

## dbt Models

| Raw Table | Staging View | Mart Table |
|---|---|---|
| `moengage_raw.raw_campaigns` | `moengage_staging.stg_moengage_campaigns` | - |
| `moengage_raw.raw_campaign_stats` | `moengage_staging.stg_moengage_campaign_stats` | `moengage_mart.mart_moengage_push` |
| (both) | - | `moengage_mart.mart_moengage_campaign_analytics` |

### Staging: stg_moengage_campaigns
- Dedup: latest row per `campaign_id` by `_ingested_at DESC`
- Casts: `created_at`, `sent_time` to TIMESTAMP; `_extract_from`, `_extract_to` to DATE
- Nested fields (`basic_details`, `segmentation_details`, `conversion_goal_details`) kept as opaque strings

### Staging: stg_moengage_campaign_stats
- Dedup: latest row per `campaign_id, platform, locale, variation, _extract_from`
- Casts: `sent`, `impression`, `click`, `attempted`, `failed`, `device_start` to INT64; `ctr`, `delivery_rate`, `sent_rate`, `failure_rate` to FLOAT64
- `delivery_funnel`, `conversion_goal_stats` kept as opaque strings

### Mart: mart_moengage_push (Group A - Push Metrics)
- Grain: `campaign_id x platform x stats_date_from x stats_date_to` (the GROUP BY also carries `channel`, `campaign_status`, `campaign_delivery_type` from the joined campaigns table, but those are functionally dependent on `campaign_id`, so the effective grain is one row per campaign x platform x stats window)
- Filter: `variation = 'all_variations'` (avoids double-counting per-variation rows)
- Metrics: `sent`, `open_proxy` (= impression), `click`, `click_rate`, `open_proxy_rate`
- Partition: `stats_date_from` (DATE); Cluster: `platform, channel`

### Mart: mart_moengage_campaign_analytics (Group E - Campaign Analytics)
- Grain: `campaign_id x platform x stats_date_from x stats_date_to` (the GROUP BY also includes `channel`, `campaign_status`, `campaign_delivery_type`, `campaign_basic_details` and the `conversion_goal_stats_raw` expression, all functionally dependent on `campaign_id`, so the effective grain is one row per campaign x platform x stats window)
- Filter: `variation = 'all_variations'`
- Adds: `campaign_basic_details` (raw metadata string), full delivery funnel (`attempted`, `failed`)
- Metrics: `open_proxy_rate`, `click_rate`, `delivery_rate`, `conversion_goal_stats_raw`
- `conversion_goal_stats_raw` is null when no goal configured (`'{}'` input → null output)
- Partition: `stats_date_from` (DATE); Cluster: `platform, channel`

---

## Dashboard Requirement Coverage

The original dashboard requirement defines five metric groups (A-E) for MoEngage. Groups A and E are fully built using the public API. Groups B, C, D require a different API access path and are not built in v1.

| Group | Metrics required | Status | Mart table |
|---|---|---|---|
| A - Push Notification | Sent, Opened (proxy), Clicked, CTR, Conversion | BUILT | `mart_moengage_push` |
| E - Campaign Analytics | Target User, Sent, Open Rate, Click Rate, Conversion | BUILT | `mart_moengage_campaign_analytics` |
| B - User Engagement | MAU, DAU, Avg Session Duration | NOT BUILT - dashboard analytics API (JWT) only, not the public API |  - |
| B - MTU (Monthly Transacting User) | MTU | NOT AVAILABLE from MoEngage - financial metric, source from AppsFlyer or internal transaction DB | - |
| C - Funnel | Install to Register, Register to Login, Login to Transaction | NOT BUILT - dashboard analytics API only; alternatively derivable from AppsFlyer in-app events | - |
| D - Cohort/Retention | D1, D7, D30 Retention | NOT BUILT - dashboard analytics API only; alternatively derivable from AppsFlyer (same approach as AppsFlyer retention mart) | - |

**Notes on partially covered metrics:**
- **Opened / Open Rate:** No native open event for push. `impression` (notification shown on screen) is used as the proxy. Labeled `open_proxy` in marts.
- **Conversion:** `conversion_goal_stats` is empty unless a conversion goal is configured per campaign in the MoEngage dashboard. Treated as null in marts, not zero.
- **Delivered:** Not exposed by the MoEngage push stats API. Dropped from all mart tables.

**Path to Groups B, C, D:** Ask the MoEngage CSM whether the workspace plan includes an official analytics access path (OAuth/Data API) or event-level export (S3/Streams/Data Warehouse). See TSD §6.3 for full options and cost notes. Do not use the dashboard UI JWT token (session-based, ~2h expiry, fragile, unsupported in production).

---

## Known Behaviors and Gotchas

| Behavior | Detail |
|---|---|
| CTR scale | 0-100 percentage, not 0-1. Can exceed 100 when sent=0 but click>0 (MoEngage edge case). Do not compare to AppsFlyer CTR. |
| ALL_PLATFORMS | Valid platform value - cross-platform aggregate. Not a data error. |
| impression > sent | Can happen; impression = notification shown on screen (can be shown multiple times). open_proxy_rate can exceed 1.0. |
| delivery_rate > 1.0 | Timing artifact in MoEngage counts. Not capped in mart. |
| Nested fields not parseable as JSON | Python str(dict) uses single quotes. `json_value()` will fail on these columns. |
| conversion_goal_stats empty | Most campaigns have no conversion goal. `'{}'` in raw = null in mart. |
| _app_id and _platform empty | MoEngage is workspace-level; platform comes from the `platform` response field, not meta columns. |
| Secret format | `moengage-api-creds` holds `WORKSPACE_ID:API_KEY` as one colon-delimited string. |
| Attribution and metric type defaults | The campaign-stats pull defaults to `MOENGAGE_ATTRIBUTION_TYPE=VIEW_THROUGH` and `MOENGAGE_METRIC_TYPE=TOTAL` (set in `config.py`). These were confirmed against a live test but the client should confirm the final values before go-live. To change without a code change, set the env vars on the `extract-moengage` Cloud Run Job: `gcloud run jobs update extract-moengage --update-env-vars="MOENGAGE_ATTRIBUTION_TYPE=...,MOENGAGE_METRIC_TYPE=..." --region=asia-southeast2 --project=$PROJECT`. |
