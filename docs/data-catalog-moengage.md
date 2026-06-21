# Data Catalog: MoEngage Raw Layer

Reference date for row counts: **2026-06-22** (validated from E2E run: 599 campaigns, 4712 stats rows).

---

## Overview

| Endpoint | BQ Table | Rows (one-time full pull) | Columns |
|---|---|---|---|
| /campaigns/search | `moengage_raw.raw_campaigns` | 599 | 9 source + 8 meta |
| /campaign-stats | `moengage_raw.raw_campaign_stats` | 4712 | 15 source + 8 meta |

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

- **URL:** `/v1/campaigns/search`
- **Method:** GET
- **Params:** `limit` (max 15), `offset` (pagination)
- **BQ table:** `moengage_raw.raw_campaigns`
- **Response shape:** bare `list[dict]` (NOT wrapped - no outer key)
- **Pagination:** offset-based. Total 599 campaigns; 40 pages at limit=15.
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

- **URL:** `/v1/campaign-stats`
- **Method:** POST
- **Body:** `{"campaign_ids": [...], "from": "YYYY-MM-DD", "to": "YYYY-MM-DD"}`
- **BQ table:** `moengage_raw.raw_campaign_stats`
- **Response shape:** wrapped dict with `stats_summary` key
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

## Meta columns (both tables, 8)

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
| `_schema_flag` | STRING | `ok` if columns match contract; flagged if schema drifts |

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
- Grain: `campaign_id x platform x stats_date_from`
- Filter: `variation = 'all_variations'` (avoids double-counting per-variation rows)
- Metrics: `sent`, `open_proxy` (= impression), `click`, `click_rate`, `open_proxy_rate`
- Partition: `stats_date_from` (DATE); Cluster: `platform, channel`

### Mart: mart_moengage_campaign_analytics (Group E - Campaign Analytics)
- Grain: `campaign_id x platform x stats_date_from`
- Filter: `variation = 'all_variations'`
- Adds: `campaign_basic_details` (raw metadata string), full delivery funnel (`attempted`, `failed`)
- Metrics: `open_proxy_rate`, `click_rate`, `delivery_rate`, `conversion_goal_stats_raw`
- `conversion_goal_stats_raw` is null when no goal configured (`'{}'` input → null output)
- Partition: `stats_date_from` (DATE); Cluster: `platform, channel`

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
