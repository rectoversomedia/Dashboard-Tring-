# Data Catalog: AppsFlyer Raw Layer

Reference date for row counts: **2026-06-13 to 2026-06-14** (2-day window, validated from local test run).

---

## Overview

| Endpoint | BQ Table | Platform | Rows (2d sample) | Columns |
|---|---|---|---|---|
| installs_report/v5 | `appsflyer_raw.raw_installs` | Android | ~2,086 | 81 source + 8 meta |
| installs_report/v5 | `appsflyer_raw.raw_installs` | iOS | ~88 | 81 source + 8 meta |
| in_app_events_report/v5 | `appsflyer_raw.raw_in_app_events` | Android | ~200,000+ | 81 source + 8 meta |
| in_app_events_report/v5 | `appsflyer_raw.raw_in_app_events` | iOS | ~84,961 | 81 source + 8 meta |
| blocked_installs_report/v5 | `appsflyer_raw.raw_blocked_installs` | Android | ~86 | 81 source + 8 meta |
| blocked_installs_report/v5 | `appsflyer_raw.raw_blocked_installs` | iOS | ~234 | 81 source + 8 meta |
| master-agg-data/v4 | `appsflyer_raw.raw_campaign_performance` | Android | ~189 | 8 source + 8 meta |
| master-agg-data/v4 | `appsflyer_raw.raw_campaign_performance` | iOS | ~107 | 8 source + 8 meta |

> `in_app_events` Android volume is very high (~100k rows/day). AppsFlyer enforces a daily download limit per app  -  see Known Issues below.

---

## App IDs

| Platform | App ID |
|---|---|
| Android | `com.pegadaiandigital` |
| iOS | `id1350501409` |

---

## API Details

| Field | Value |
|---|---|
| Base URL | `https://hq1.appsflyer.com` |
| Auth | Bearer token v3, from Secret Manager `appsflyer-api-token` |
| Timezone | `Asia/Jakarta` |
| Format | CSV (UTF-8 with BOM) |

---

## Endpoints

### 1. installs_report/v5

- **URL:** `/api/raw-data/export/app/{app_id}/installs_report/v5`
- **Params:** `from`, `to`, `timezone`
- **BQ table:** `appsflyer_raw.raw_installs`
- **Volume:** Android ~1,000-2,000/day, iOS ~40-100/day
- **81 source columns:**

| Column | Description |
|---|---|
| Attributed Touch Type | Click / impression / TV |
| Attributed Touch Time | Timestamp of ad touch |
| Install Time | App install timestamp |
| Event Time | Same as install time for installs |
| Event Name | Always "install" |
| Event Value | JSON event data |
| Event Revenue | Revenue value |
| Event Revenue Currency | Currency code |
| Event Revenue USD | Revenue in USD |
| Event Source | SDK / S2S |
| Is Receipt Validated | Boolean |
| Partner | Attribution partner |
| Media Source | Traffic source (e.g. Facebook, Google) |
| Channel | Sub-channel |
| Keywords | Paid search keywords |
| Campaign | Campaign name |
| Campaign ID | Campaign identifier |
| Adset | Ad set name |
| Adset ID | Ad set identifier |
| Ad | Ad name |
| Ad ID | Ad identifier |
| Ad Type | Banner / interstitial / etc |
| Site ID | Publisher site |
| Sub Site ID | Sub-publisher |
| Sub Param 1-5 | Custom sub-parameters |
| Cost Model | CPI / CPM / CPC |
| Cost Value | Bid value |
| Cost Currency | Cost currency |
| Contributor 1-3 Partner | Multi-touch partner |
| Contributor 1-3 Media Source | Multi-touch source |
| Contributor 1-3 Campaign | Multi-touch campaign |
| Contributor 1-3 Touch Type | Multi-touch type |
| Contributor 1-3 Touch Time | Multi-touch timestamp |
| Region | Geographic region |
| Country Code | ISO country code |
| State | State/province |
| City | City |
| Postal Code | Postal code |
| DMA | Designated market area (US) |
| IP | User IP address |
| WIFI | Boolean |
| Operator | Carrier operator |
| Carrier | Carrier name |
| Language | Device language |
| AppsFlyer ID | Unique AppsFlyer device ID |
| Advertising ID | GAID (Android) / IDFA (iOS) |
| IDFA | iOS identifier |
| Android ID | Android device ID |
| Customer User ID | App's own user ID |
| IMEI | Device IMEI (deprecated) |
| IDFV | iOS vendor identifier |
| Platform | android / ios |
| Device Type | Phone / tablet |
| OS Version | OS version string |
| App Version | App version string |
| SDK Version | AppsFlyer SDK version |
| App ID | App package/bundle ID |
| App Name | App display name |
| Bundle ID | Bundle identifier |
| Is Retargeting | Boolean |
| Retargeting Conversion Type | re-engagement / re-attribution |
| Attribution Lookback | Lookback window |
| Reengagement Window | Re-engagement window |
| Is Primary Attribution | Boolean |
| User Agent | Browser/app user agent |
| HTTP Referrer | HTTP referrer |
| Original URL | Click URL |

---

### 2. in_app_events_report/v5

- **URL:** `/api/raw-data/export/app/{app_id}/in_app_events_report/v5`
- **Params:** `from`, `to`, `timezone`
- **BQ table:** `appsflyer_raw.raw_in_app_events`
- **Volume:** Android ~100,000-200,000+/day, iOS ~40,000-85,000/day
- **81 source columns:** Same schema as `raw_installs`  -  `Event Name` contains the in-app event name (e.g. `SplashScreen_Loading`, `Login_PreLogin_Masuk`, `BeliTE_TransaksiSukses`)
- **Key column:** `Event Name`  -  used by dbt seed `event_mapping.csv` to categorize into `open_app`, `login`, `purchase`, `registration`

---

### 3. blocked_installs_report/v5

- **URL:** `/api/raw-data/export/app/{app_id}/blocked_installs_report/v5`
- **Params:** `from`, `to`, `timezone`
- **BQ table:** `appsflyer_raw.raw_blocked_installs`
- **Volume:** Android ~40-90/day, iOS ~100-250/day
- **81 source columns:** Same schema as `raw_installs`  -  these are installs AppsFlyer flagged as fraudulent/invalid

---

### 4. master-agg-data/v4 (campaign performance)

- **URL:** `/api/master-agg-data/v4/app/{app_id}`
- **Params:** `from`, `to`, `timezone`, `groupings=pid,c,install_time,geo`, `kpis=impressions,clicks,installs,cost`, `currency=USD`
- **BQ table:** `appsflyer_raw.raw_campaign_performance`
- **Volume:** Android ~100-200 rows/day, iOS ~50-110 rows/day
- **8 source columns:**

| Column | Description |
|---|---|
| Media Source | Traffic source |
| Campaign | Campaign name |
| Install Time | Date (grouped by install date) |
| GEO | Country code |
| Impressions | Ad impressions count |
| Clicks | Ad clicks count |
| Installs | Install count |
| Cost | Total cost in USD |

---

## Raw Table Schema (all tables)

All source columns are stored as `STRING`. Eight metadata columns appended by the ingestion layer:

| Metadata Column | Type | Description |
|---|---|---|
| `_ingested_at` | TIMESTAMP | UTC timestamp of BQ load |
| `_source` | STRING | Always `appsflyer` |
| `_app_id` | STRING | App package/bundle ID |
| `_platform` | STRING | `android` or `ios` |
| `_run_id` | STRING | Unique ID per extract run (groups all pulls in one job execution) |
| `_extract_from` | DATE | `from` param used in API call |
| `_extract_to` | DATE | `to` param used in API call |
| `_schema_flag` | STRING | Schema-version marker for the raw load |

---

## AppsFlyer API Rate Limits

Source: https://support.appsflyer.com/hc/en-us/articles/207034366

| Report Type | App-level daily quota | Account-level daily quota |
|---|---|---|
| Installs (Pull API raw) | 24 calls/day/app | 120 calls/day |
| In-app events (Pull API raw) | **12 calls/day/app** | 60 calls/day |
| Blocked installs (Pull API raw) | 24 calls/day/app | 120 calls/day |
| Master API (aggregate) | Unlimited | Unlimited |

**Key rules:**
- Quota per **report type**, per **day**, per **app**  -  separate for each
- Day resets at **00:00 UTC**
- Agency token vs advertiser token counted separately  -  if agency uses advertiser's token, counts against advertiser quota
- Pull API quota and export page quota are **separate**

**Pipeline usage per scheduled run:**
- `in_app_events`: 1 call (Android) + 1 call (iOS) = **2 calls per run**
- 2 runs/day (scheduler) = **4 calls/day**  -  safely under 12 limit

**Why limit was hit during dev (2026-06-20):**
Multiple job executions during OOM debugging consumed the 12-call daily quota for `in_app_events` Android:
- Each execution retries 3x = 3 API calls per execution
- 4-5 executions × 3 retries = ~12-15 calls → limit exhausted
- This is a dev/debugging artifact, not a production issue

---

## Known Issues

### in_app_events Android  -  Rate Limit Hit During Dev (RESOLVED next UTC 00:00)

| Field | Detail |
|---|---|
| Error | `400 Bad Request`  -  "You've reached your maximum number of in-app event reports that can be downloaded today for this app" |
| Endpoint | `in_app_events_report/v5`  -  Android only |
| Platform affected | Android (`com.pegadaiandigital`) |
| iOS | Not affected |
| Root cause | 12 calls/day/app limit exhausted during OOM debug session (multiple retried executions) |
| Production impact | None  -  normal 2x/day schedule uses only 4 calls/day, well under 12 limit |
| Recovery | Automatic  -  resets at 00:00 UTC daily |
| Action needed | None for production. If hit again in prod, check for runaway executions or excessive manual runs. |
| Reference | https://support.appsflyer.com/hc/en-us/articles/207034366 |

---

## Volume Estimates (daily, single date)

| Endpoint | Android | iOS | Notes |
|---|---|---|---|
| installs | ~1,000-2,000 rows | ~40-100 rows | Higher Android volume expected |
| in_app_events | ~100,000-200,000 rows | ~40,000-85,000 rows | Largest table. Android rate-limited. |
| blocked_installs | ~40-90 rows | ~100-250 rows | Small, fraud signals |
| master_agg | ~100-200 rows | ~50-110 rows | Aggregated, smallest table |

> Estimates based on 2-day sample (2026-06-13 to 2026-06-14). Volume varies by campaign activity.

---

## Known Metric Behavior

### conversion_rate > 1.0 (mart_appsflyer_user_quality)

| Field | Detail |
|---|---|
| Metric | `conversion_rate = registrations / installs` |
| Issue | Value can exceed 1.0 (> 100%) |
| Root cause | Date grain mismatch: `events` uses `event_date`, `installs` uses `install_date`. User who installs on day T and completes registration on day T+3 creates registrations with no matching installs on that date in the same campaign grain. |
| Is it a bug? | No  -  expected behavior given date-based join design |
| Fix considered | User-level join (appsflyer_id) would fix it but adds complexity and is out of scope |
| Action | No range test on this column. Comment added in SQL and YAML. Dashboard consumers should note this metric may show > 100% for small campaign/date combinations. |

---

## Data Layers & BQ Datasets

| Layer | BQ Dataset | Type | Who writes |
|---|---|---|---|
| Raw | `appsflyer_raw` | Append-only tables | ingestion Cloud Run Job |
| Staging | `appsflyer_staging` | Views (no materialization) | dbt |
| Mart | `appsflyer_staging` | Tables (full refresh each run) | dbt |

> Staging dan mart sama-sama di dataset `appsflyer_staging`. Dibedakan dari nama tabel: `stg_*` vs `mart_*`.

---

## SCD Strategy

**Tidak ada SCD (Slowly Changing Dimensions).** Semua tables adalah fact tables, bukan dimensi.

| Layer | Strategy | Detail |
|---|---|---|
| Raw | Append-only | Setiap extract run append rows baru. Duplikat bisa ada jika job re-run. |
| `stg_appsflyer_installs` | Dedup (SCD-0) | `QUALIFY ROW_NUMBER() OVER (PARTITION BY appsflyer_id, install_date, _platform ORDER BY _ingested_at DESC) = 1`  -  ambil 1 row terbaru per device per hari. History tidak di-track. |
| `stg_appsflyer_in_app_events` | No dedup | Semua events diambil as-is. Event bisa duplikat jika raw duplikat. |
| `stg_appsflyer_blocked_installs` | Dedup by appsflyer_id + install_date | Same pattern as installs. |
| Mart | Full refresh | DROP + CREATE TABLE setiap dbt build. Tidak ada incremental. |

---

## dbt Tests (63 total  -  PASS=63 WARN=0 ERROR=0)

| Test type | Count | Contoh yang dicek |
|---|---|---|
| `not_null` | ~20 | `appsflyer_id`, `install_date`, `media_source`, `platform` tidak boleh NULL |
| `accepted_values` | 4 | `_platform` ∈ {android, ios}; `event_category` ∈ {open_app, login, purchase, registrations} |
| `unique_combination_of_columns` | 1 | `stg_appsflyer_installs`: appsflyer_id + install_date + platform unik (verifikasi dedup) |
| `accepted_range` | ~10 | Numeric columns ≥ 0: impressions, clicks, installs, cost, fraud_rate, cohort_size, dll |
| `expression_is_true` | 4 | Staging campaign_performance: impressions/clicks/installs/cost >= 0 |
| **Total** | **63** | |

> `event_category` test pakai `severity: warn`  -  event names tidak ada di seed mapping akan di-warn, bukan error. Ini expected karena AppsFlyer bisa kirim event baru yang belum di-map.

---

## Downstream (staging + mart)

| Raw Table | Staging Model | Mart Model(s) |
|---|---|---|
| raw_installs | `stg_appsflyer_installs` | `install_attribution`, `campaign_performance`, `fraud` |
| raw_in_app_events | `stg_appsflyer_in_app_events` | `user_quality`, `retention` |
| raw_blocked_installs | `stg_appsflyer_blocked_installs` | `fraud` |
| raw_campaign_performance | `stg_appsflyer_campaign_performance` | `campaign_performance` |
