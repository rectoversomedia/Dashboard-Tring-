# Runbook: Dashboard Monitoring & AI Insight  -  Data Pipeline

> **Before you run any command here:** set your project once in the terminal: `export PROJECT=your-gcp-project-id`. Every command below uses `$PROJECT`. New to the terms used here (Workflow, Cloud Run Job, backfill, T-1)? See [index.md](index.md) for a glossary.

> **Schedule note:** Pipeline runs automatically twice daily via Cloud Scheduler (08:00 and 20:00 WIB). This schedule is a default assumption from the TSD - the client has not confirmed a final schedule. To update: `gcloud scheduler jobs update http pipeline-trigger-morning --schedule="0 H * * *" --location=asia-southeast2 --project=$PROJECT` (and same for `pipeline-trigger-afternoon`).

## 1. Triggering a manual pipeline run

> **Workflow behavior:** Workflow triggers extract-appsflyer, extract-moengage, and extract-play-console **in parallel**, polls each every 15s until SUCCEEDED (all three must succeed), then triggers dbt-transform, polls until SUCCEEDED, then returns. Total duration ~6-7 minutes for appsflyer+moengage (play-console adds time on first load; subsequent runs ~2-3 min). If any extract fails, Workflow fails immediately  -  dbt does NOT run.

**Run pipeline (T-2 auto-computed — default window is T-3 to T-2):**
```bash
gcloud workflows run pipeline \
  --location=asia-southeast2 \
  --project=$PROJECT
```

> **Why T-2 not T-1?** Play Console vitals API has a 2-day data lag. Requesting T-1 returns HTTP 400 `end_date exceeds freshness boundary`. T-2 is the most recent date always available. The pipeline fetches one day of data per run (T-3 as date_from, T-2 as date_to).

**Run for specific date range (backfill):**
```bash
gcloud workflows run pipeline \
  --data='{"date_from":"2026-06-01","date_to":"2026-06-10"}' \
  --location=asia-southeast2 \
  --project=$PROJECT
```

---

## 2. Verifying pipeline success

**Step 1  -  Check Workflow execution result:**

Successful run output:
```
state: SUCCEEDED
result: '"Pipeline complete for 2026-06-19 to 2026-06-19"'
duration: ~7 minutes (verified; varies with data volume)
```

Failed run output:
```
state: FAILED
error:
  context: "extract-appsflyer completed but not all tasks succeeded"
```

**Step 2a  -  Check AppsFlyer extract logs:**
```bash
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="extract-appsflyer"' \
  --project=$PROJECT \
  --limit=50 \
  --order=desc \
  --format="table(timestamp,textPayload)"
```

Key lines to look for:
- `Extract complete: 8/8 succeeded` → success
- `RuntimeError: Extract failed for N pull(s)` → failure, check which endpoint/platform

**Step 2b  -  Check MoEngage extract logs:**
```bash
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="extract-moengage"' \
  --project=$PROJECT \
  --limit=50 \
  --order=desc \
  --format="table(timestamp,textPayload)"
```

Key lines to look for:
- `Extract complete` (exit 0) → success
- Any `ERROR` or non-zero exit → failure; check API connectivity or secret rotation

**Step 2c  -  Check Play Console extract logs:**
```bash
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="extract-play-console"' \
  --project=$PROJECT \
  --limit=50 \
  --order=desc \
  --format="table(timestamp,textPayload)"
```

Key lines to look for:
- `Extract complete: 7 pulls` (6 metric sets + reviews, exit 0) → success
- `Extract failed for: [...]` → one or more metric sets failed; check error details above

**Step 2d  -  Check App Store extract logs (once GCP infra provisioned):**
```bash
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="extract-app-store"' \
  --project=$PROJECT \
  --limit=50 \
  --order=desc \
  --format="table(timestamp,textPayload)"
```

Key lines to look for:
- `Extract complete: N total rows` → success
- `reviews: N rows` + per-report log lines (one per Analytics report)
- `Extract failed for: [...]` → collect-errors pattern; one or more reports failed, others still loaded

**Step 3  -  Check dbt logs (look for PASS=140 ERROR=0):**
```bash
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="dbt-transform"' \
  --project=$PROJECT \
  --limit=50 \
  --order=desc \
  --format="table(timestamp,textPayload)"
```

Key lines to look for:
- `Done. PASS=140 WARN=0 ERROR=0` → success (3 sources; PASS=N will increase once App Store source GCP is provisioned)
- `Done. PASS=XX ERROR=N` → test failures, check which model

**Step 4  -  Check execution list (optional):**
```bash
gcloud run jobs executions list \
  --job=extract-appsflyer \
  --region=asia-southeast2 \
  --project=$PROJECT \
  --limit=3
```

`✔` = succeeded, `X` = failed, `…` = running.

---

## 3. Running a single job manually

**Extract AppsFlyer only (bypass Workflow):**
```bash
gcloud run jobs execute extract-appsflyer \
  --region=asia-southeast2 \
  --project=$PROJECT \
  --update-env-vars="DATE_FROM=2026-06-19,DATE_TO=2026-06-19"
```

**Extract MoEngage only (bypass Workflow):**
```bash
gcloud run jobs execute extract-moengage \
  --region=asia-southeast2 \
  --project=$PROJECT \
  --update-env-vars="DATE_FROM=2026-06-19,DATE_TO=2026-06-19"
```

**Extract Play Console only (bypass Workflow):**
```bash
gcloud run jobs execute extract-play-console \
  --region=asia-southeast2 \
  --project=$PROJECT \
  --update-env-vars="DATE_FROM=2026-06-19,DATE_TO=2026-06-19"
```

> Note: Play Console reviews are not date-scoped (the API always returns the current state of all reviews). DATE_FROM/DATE_TO affect only the metric set queries (crash rate, ANR rate, etc).

**Extract App Store only (bypass Workflow):**
```bash
gcloud run jobs execute extract-app-store \
  --region=asia-southeast2 \
  --project=$PROJECT \
  --update-env-vars="DATE_FROM=2026-06-19,DATE_TO=2026-06-19" \
  --wait
```

> Note: App Store analytics downloads ALL available instances each run (stateless). DATE_FROM/DATE_TO only set metadata (`_extract_from`/`_extract_to`) on raw rows; Apple controls which dates are available. Reviews use DATE_FROM as incremental cutoff.

**dbt only (bypass Workflow):**
```bash
gcloud run jobs execute dbt-transform \
  --region=asia-southeast2 \
  --project=$PROJECT
```

---

## 4. Backfilling historical data

Raw is append-only. Staging deduplicates by latest `_ingested_at` per natural key, so re-runs are safe.

**Option A  -  Backfill via Workflow (recommended  -  runs extract + dbt in sequence):**
```bash
gcloud workflows run pipeline \
  --data='{"date_from":"2026-05-01","date_to":"2026-05-31"}' \
  --location=asia-southeast2 \
  --project=$PROJECT
```

**Option B  -  Backfill extract only (manual, bypass Workflow):**
```bash
gcloud run jobs execute extract-appsflyer \
  --region=asia-southeast2 \
  --project=$PROJECT \
  --update-env-vars="DATE_FROM=2026-05-01,DATE_TO=2026-05-31"
```

After Option B extract completes, run dbt manually:
```bash
gcloud run jobs execute dbt-transform \
  --region=asia-southeast2 \
  --project=$PROJECT
```

---

## 5. Rotating the AppsFlyer API token

```bash
echo -n "NEW_TOKEN_VALUE" | gcloud secrets versions add appsflyer-api-token \
  --data-file=- \
  --project=$PROJECT

gcloud secrets versions list appsflyer-api-token --project=$PROJECT

gcloud secrets versions disable VERSION_NUMBER \
  --secret=appsflyer-api-token \
  --project=$PROJECT
```

---

## 6. Rotating the MoEngage API credentials

```bash
echo -n "NEW_WORKSPACE_ID:NEW_API_KEY" | gcloud secrets versions add moengage-api-creds \
  --data-file=- \
  --project=$PROJECT

gcloud secrets versions list moengage-api-creds --project=$PROJECT

gcloud secrets versions disable VERSION_NUMBER \
  --secret=moengage-api-creds \
  --project=$PROJECT
```

> Secret format: `WORKSPACE_ID:API_KEY` colon-separated. Get values from MoEngage dashboard > Settings > APIs.

---

## 7. Rotating the Play Console service account key

The Play Console secret (`play-console-sa-key`) stores a SA key from the client's production GCP project (`pgd-prd-digital-rating-tring`), not from `hypefast-data-staging`. To rotate:

1. Ask the client to generate a new key from their GCP IAM: SA `dashboard-monitoring-aiinsight@pgd-prd-digital-rating-tring.iam.gserviceaccount.com` > Keys > Add Key > JSON
2. Client sends the new key file securely (never via email or Slack - use a secret sharing tool)
3. Add new version to Secret Manager:
```bash
cat new-sa-key.json | gcloud secrets versions add play-console-sa-key --data-file=- --project=$PROJECT
rm new-sa-key.json
```
4. Disable the old version:
```bash
gcloud secrets versions list play-console-sa-key --project=$PROJECT
gcloud secrets versions disable OLD_VERSION_NUMBER --secret=play-console-sa-key --project=$PROJECT
```
5. Ask the client to delete the old key from their GCP IAM to fully revoke it.

> The Cloud Run Job picks up the new secret version on the next execution. No job restart needed.

---

## 8. Updating the pipeline schedule

The default schedule is 08:00 and 20:00 WIB (01:00 and 13:00 UTC). To change:

```bash
# Morning trigger (change cron as needed)
gcloud scheduler jobs update http pipeline-trigger-morning \
  --schedule="0 1 * * *" \
  --time-zone="Asia/Jakarta" \
  --location=asia-southeast2 \
  --project=$PROJECT

# Afternoon trigger
gcloud scheduler jobs update http pipeline-trigger-afternoon \
  --schedule="0 13 * * *" \
  --time-zone="Asia/Jakarta" \
  --location=asia-southeast2 \
  --project=$PROJECT
```

Cron format: `minute hour day month weekday`. `0 1 * * *` = every day at 01:00 UTC = 08:00 WIB. Use [crontab.guru](https://crontab.guru) to verify your cron expression before applying.

To verify current schedule:
```bash
gcloud scheduler jobs list --location=asia-southeast2 --project=$PROJECT
```

---

## 9. Known issue: AppsFlyer in_app_events rate limit

AppsFlyer limits: `in_app_events` 12 calls/day/app, `installs` 24/day/app. When hit:

- Error: `400 Bad Request`  -  "You've reached your maximum number of in-app event reports"
- Workflow state: `FAILED`  -  "extract-appsflyer completed but not all tasks succeeded"
- Resets at UTC 00:00 (07:00 WIB)
- Production schedule (2x/day) uses 4 calls/day  -  safely under 12 limit
- If hit in prod: check for runaway executions or excessive manual runs
- To increase limit: client contacts AppsFlyer CSM (hello@appsflyer.com)
- Reference: https://support.appsflyer.com/hc/en-us/articles/207034366

---

## 10. Known behavior: Play Console Reporting API uses exclusive endTime

The Play Developer Reporting API treats `endTime` as exclusive (not inclusive). The extract code automatically adds 1 day to your `--to` date before sending the request, so you never need to adjust your date arguments.

If you see this error when running Play Console extract:

```
"The 'start_time' must be earlier than the 'end_time'"
```

It means `startTime` and `endTime` sent to the API are equal -- this should not happen with the current code. Check that you are running the latest version of `extract.py` (the fix was added in commit `4b56365`).

---

## 11. Schema changes from upstream APIs

**New columns added by the API provider (Apple, AppsFlyer, MoEngage, Google):**

The ingestion layer (`bq_loader.py`) automatically filters out any columns from the API response that are not in the existing BQ table schema. New fields are silently dropped at ingest time — **no pipeline failure, no manual schema update needed just to keep the pipeline running**.

A warning is logged: `dropping unknown columns not in BQ schema: {'new_col'}`. Check Cloud Logging periodically to know what Apple/Google added:

```bash
gcloud logging read 'resource.type="cloud_run_job" AND textPayload=~"dropping unknown columns"' \
  --project=$PROJECT \
  --limit=20 \
  --format="value(timestamp,resource.labels.job_name,textPayload)" \
  --freshness=7d
```

Output example:
```
2026-07-01T08:34:xx  extract-app-store  dropping unknown columns not in BQ schema: {'new_col_from_apple'}
```

The job name tells you which source added the new field.

To **capture** a new column in the pipeline (i.e. make it available in dbt):
1. Export current schema: `bq show --schema --format=prettyjson PROJECT:DATASET.TABLE > /tmp/schema.json`
2. Add the new field to the JSON (type `STRING` for raw)
3. Update BQ table: `bq update PROJECT:DATASET.TABLE /tmp/schema.json`
4. Add the column to the relevant staging model SQL
5. Rebuild + redeploy: `make cloudbuild-deploy-prod PROJECT=$PROJECT`
6. Re-run pipeline

**Columns removed or renamed by the API provider:**

This will cause the staging model to fail with `Unrecognized name: <col>`. Fix: update the staging SQL to remove or rename the column reference, then rebuild dbt.

**App Store TSV column name normalization:**

Apple TSV headers are normalized via `_snake()` in `endpoints.py`: spaces → `_`, dashes → `_`. Example: `Pre-Order` → `pre_order`. Raw BQ data ingested before 2026-06-28 used the old format `pre-order` (dash); `stg_appstore_app_downloads` handles both via `coalesce(pre_order, \`pre-order\`)`.

---

## 12. Checking for failures and adding alerting

By default there is no automated alert (not provisioned in the initial
handover). Failures surface as a `FAILED` Workflow execution. Check manually as
below, or set up email alerting (next sub-section) so failures notify you
automatically.

Check periodically, or after a scheduled run:

1. List executions: `gcloud workflows executions list pipeline --location=asia-southeast2 --project=$PROJECT --limit=5`
2. A `FAILED` state names which step failed in its error message  -  describe it: `gcloud workflows executions describe EXECUTION_ID --workflow=pipeline --location=asia-southeast2 --project=$PROJECT`
3. Check Cloud Logging for that job (sections 2-3 above)

### Adding email alerting (recommended for production)

Alerting is not provisioned in the initial handover, so a failed run is only
visible if someone checks manually. For production you usually want an email
when the pipeline fails. Set it up once per GCP project with two commands.

The alert fires on the Cloud Monitoring metric
`workflows.googleapis.com/finished_execution_count` filtered to
`status="FAILED"`, so it covers any failure in any branch (the workflow ends in
`FAILED` whenever an extract or the dbt step fails).

```bash
# 1. Create an email notification channel. Use a team distribution list, not a
#    personal inbox, so alerts survive staff changes.
gcloud beta monitoring channels create \
  --display-name="Pipeline Alerts" \
  --type=email \
  --channel-labels=email_address=YOUR_TEAM_EMAIL@example.com \
  --project=$PROJECT

# Copy the channel name from the output. It looks like:
#   projects/$PROJECT/notificationChannels/1234567890123456789
```

```bash
# 2. Create the alert policy, pointing at the channel name from step 1.
CHANNEL="projects/$PROJECT/notificationChannels/PASTE_CHANNEL_ID_HERE"

gcloud alpha monitoring policies create \
  --notification-channels="$CHANNEL" \
  --display-name="Pipeline run FAILED" \
  --condition-display-name="Workflow pipeline finished with FAILED" \
  --condition-filter='metric.type="workflows.googleapis.com/finished_execution_count" AND resource.type="workflows.googleapis.com/Workflow" AND resource.label.workflow_id="pipeline" AND metric.label.status="FAILED"' \
  --condition-threshold-value=0 \
  --condition-threshold-comparison=COMPARISON_GT \
  --condition-threshold-duration=0s \
  --condition-threshold-aggregation='{"alignmentPeriod":"300s","perSeriesAligner":"ALIGN_COUNT"}' \
  --combiner=OR \
  --project=$PROJECT
```

After this, any `FAILED` run sends an email within a few minutes. To verify, let
a run fail on purpose (for example point an extract at an invalid date) or wait
for the next real failure.

> For Slack or PagerDuty instead of email: create the notification channel with
> `--type=slack` or `--type=pagerduty` (each needs its own setup in the GCP
> Console first to authorize the integration), then reuse the same alert policy
> command with that channel name. You can attach more than one channel by
> repeating `--notification-channels`.

Common causes:
- **HTTP 401 (AppsFlyer)**: Token expired → rotate token (Section 5)
- **HTTP 401 (MoEngage)**: Credentials invalid → rotate secret (Section 6)
- **HTTP 400 rate limit**: Daily quota exhausted → wait for UTC 00:00 reset
- **Empty response**: No data for that date window  -  normal for new apps or holidays
- **dbt ERROR=N**: Test failures → check which model, run `dbt build --select failing_model` locally

---

## 13. Adding a new data source

**MoEngage** - fully implemented and E2E verified (2026-06-22: 599 campaigns, 4712 stats rows, exit(0), full pipeline SUCCEEDED). GCP infra provisioned (SA, secret, BQ datasets, Cloud Run Job `extract-moengage`). dbt models built (`stg_moengage_campaigns`, `stg_moengage_campaign_stats`, `mart_moengage_push`, `mart_moengage_campaign_analytics`). pipeline.yaml runs all three extracts (AppsFlyer + MoEngage + Play Console) in parallel; full-pipeline dbt run is PASS=140 WARN=0 ERROR=0.

**Play Console** - FULLY DONE (2026-06-22). Ingestion code (16 tests PASS) + GCP infra (SA, secret, BQ datasets, Cloud Run Job) + dbt models (7 staging + 2 mart, PASS=140 WARN=0 ERROR=0 E2E verified) + pipeline.yaml (3 parallel branches, Workflow rev 000012-e43). Uses SA key from client prod project `pgd-prd-digital-rating-tring` stored in Secret Manager.

> **Adding an endpoint to a source that already exists** (one more AppsFlyer report, one more Play Console metric set, one more MoEngage call) is a smaller job - you do not create a new SA, secret, job, or dataset. See `docs/adding-endpoints.md` for that. The steps below are for a brand new source (a new vendor).

General steps for any new source:

1. Add package under `ingestion/src/tring_ingest/sources/<source_name>/` with `client.py`, `endpoints.py`, `extract.py` following the AppsFlyer or MoEngage pattern
2. Add `--source <source_name>` handler to `cli.py`
3. Add config env vars to `common/config.py`
4. Create the Secret Manager secret, SA, IAM, and BQ datasets (see `docs/gcp-setup.md` section on adding sources)
5. Create new Cloud Run Job pointing to the ingestion image with `--source <source_name>`
6. Add the new extract job to `pipeline.yaml` as a parallel branch (min 2 branches required for parallel mode)
7. Add dbt models under `transform/models/staging/<source>/` and `transform/models/marts/<source>/`

**Infra commands for MoEngage (run once per GCP project):**

```bash
# SA
gcloud iam service-accounts create sa-extract-moengage \
  --display-name="MoEngage extractor runtime" --project=$PROJECT

# IAM
gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:sa-extract-moengage@${PROJECT}.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor"
gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:sa-extract-moengage@${PROJECT}.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"

# Secret (add value out of band - never commit the value)
gcloud secrets create moengage-api-creds --replication-policy="automatic" --project=$PROJECT
# Value format: WORKSPACE_ID:API_KEY  (colon-separated, no spaces)
echo -n "YOUR_WORKSPACE_ID:YOUR_API_KEY" | gcloud secrets versions add moengage-api-creds \
  --data-file=- --project=$PROJECT

gcloud secrets add-iam-policy-binding moengage-api-creds \
  --member="serviceAccount:sa-extract-moengage@${PROJECT}.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" --project=$PROJECT

# BQ datasets
bq --project_id=$PROJECT mk --location=asia-southeast2 moengage_raw
bq --project_id=$PROJECT mk --location=asia-southeast2 moengage_staging
bq --project_id=$PROJECT mk --location=asia-southeast2 moengage_mart

# Cloud Run Job (same ingestion image, different --source)
REGISTRY=asia-southeast2-docker.pkg.dev
gcloud run jobs create extract-moengage \
  --image=${REGISTRY}/${PROJECT}/tring-service/ingestion:latest \
  --region=asia-southeast2 \
  --service-account=sa-extract-moengage@${PROJECT}.iam.gserviceaccount.com \
  --set-env-vars="GCP_PROJECT=${PROJECT},BQ_DATASET_RAW_MOENGAGE=moengage_raw,REGION=asia-southeast2" \
  --set-secrets="MOENGAGE_API_CREDS=moengage-api-creds:latest" \
  --command=python \
  --args="-m,tring_ingest,--source,moengage" \
  --memory=2Gi --cpu=1 \
  --max-retries=0 \
  --project=$PROJECT
```

---

## 14. Deploying a change

> **Important:** All code (ingestion Python and dbt SQL models) is baked into Docker images at build time. Running `gcloud run jobs execute` without rebuilding the image will use stale code from the previous build. Always rebuild first when code changes.
>
> - Changed `transform/` SQL? Rebuild both images (build-push.yaml builds ingestion + dbt together), update `dbt-transform`, then execute.
> - Changed `ingestion/` Python? Rebuild, update all `extract-*` jobs, then execute.
> - Changed both? Rebuild once, update all 5 jobs.

```bash
# Build + push new image
gcloud builds submit . \
  --config=cloudbuild/build-push.yaml \
  --substitutions="_PROJECT=$PROJECT" \
  --project=$PROJECT

# Update Cloud Run Jobs to new image
gcloud run jobs update extract-appsflyer \
  --image=asia-southeast2-docker.pkg.dev/$PROJECT/tring-service/ingestion:latest \
  --region=asia-southeast2 \
  --project=$PROJECT

gcloud run jobs update extract-moengage \
  --image=asia-southeast2-docker.pkg.dev/$PROJECT/tring-service/ingestion:latest \
  --region=asia-southeast2 \
  --project=$PROJECT

gcloud run jobs update extract-play-console \
  --image=asia-southeast2-docker.pkg.dev/$PROJECT/tring-service/ingestion:latest \
  --region=asia-southeast2 \
  --project=$PROJECT

gcloud run jobs update dbt-transform \
  --image=asia-southeast2-docker.pkg.dev/$PROJECT/tring-service/dbt:latest \
  --region=asia-southeast2 \
  --project=$PROJECT
```

---

## 15. Checking dbt model freshness

```bash
cd transform
dbt source freshness --profiles-dir . --target dev
```

---

## 16. Query cost optimization

BigQuery charges by the amount of data scanned per query (on-demand pricing: ~$5 per TB). All mart tables are partitioned and clustered to reduce scan size. This section explains how to use them correctly.

### Partition and cluster config per mart table

| Table | Dataset | Partition column | Cluster columns |
|---|---|---|---|
| `mart_appsflyer_install_attribution` | `appsflyer_mart` | `install_date` (DATE) | `media_source`, `campaign`, `platform` |
| `mart_appsflyer_campaign_performance` | `appsflyer_mart` | `date` (DATE) | `media_source`, `campaign`, `platform` |
| `mart_appsflyer_user_quality` | `appsflyer_mart` | `date` (DATE) | `media_source`, `campaign`, `platform` |
| `mart_appsflyer_retention` | `appsflyer_mart` | `cohort_date` (DATE) | `media_source`, `campaign`, `platform` |
| `mart_appsflyer_fraud` | `appsflyer_mart` | `date` (DATE) | `media_source`, `campaign`, `platform` |
| `mart_moengage_push` | `moengage_mart` | `stats_date_from` (DATE) | `platform`, `channel` |
| `mart_moengage_campaign_analytics` | `moengage_mart` | `stats_date_from` (DATE) | `platform`, `channel` |
| `mart_play_console_app_health` | `play_mart` | `date` (DATE) | `version_code` |
| `mart_play_console_reviews` | `play_mart` | `review_date` (DATE) | `star_rating` |

**Partition** = BigQuery splits the table into separate storage chunks by date. A query with `WHERE date = '2026-06-01'` only scans that one chunk, not the whole table.

**Cluster** = within each partition chunk, rows are physically sorted by the cluster columns. A query with `WHERE media_source = 'Facebook Ads'` scans less data because matching rows are stored together.

### How to write cost-efficient queries

**Always filter on the partition column first:**

```sql
-- Good: filters partition column, scans only June data
SELECT *
FROM `your-project.appsflyer_mart.mart_appsflyer_campaign_performance`
WHERE date BETWEEN '2026-06-01' AND '2026-06-30'
  AND media_source = 'Facebook Ads';

-- Bad: no date filter, scans the entire table
SELECT *
FROM `your-project.appsflyer_mart.mart_appsflyer_campaign_performance`
WHERE media_source = 'Facebook Ads';
```

**Stack cluster filters after the partition filter:**

```sql
-- Best: partition filter + cluster filter = minimum scan
SELECT date, campaign, installs, cost
FROM `your-project.appsflyer_mart.mart_appsflyer_campaign_performance`
WHERE date BETWEEN '2026-06-01' AND '2026-06-30'
  AND media_source = 'Facebook Ads'
  AND platform = 'android';
```

**Avoid `SELECT *` on large tables:**

```sql
-- Good: select only the columns you need
SELECT date, campaign, installs
FROM `your-project.appsflyer_mart.mart_appsflyer_campaign_performance`
WHERE date = '2026-06-23';

-- Expensive: pulls all columns including ones you do not use
SELECT *
FROM `your-project.appsflyer_mart.mart_appsflyer_campaign_performance`
WHERE date = '2026-06-23';
```

**Check bytes scanned before running a query:**

In BigQuery Console, the estimated bytes scanned appears in the top-right corner of the editor after you write a query (before running it). Aim for MB range, not GB.

```sql
-- You can also run a dry run via CLI to check bytes without cost
bq query --dry_run --use_legacy_sql=false --project_id=$PROJECT \
  'SELECT date, campaign, installs
   FROM `your-project.appsflyer_mart.mart_appsflyer_campaign_performance`
   WHERE date = "2026-06-23"'
```

The output shows `totalBytesProcessed` - this is the scan size before any cost is charged.

### Raw and staging tables

Raw tables (`appsflyer_raw`, `moengage_raw`, `play_raw`) are append-only and not partitioned. **Avoid querying raw tables directly** for analysis - use the mart tables instead. Raw tables grow unbounded and scanning them is expensive.

Staging tables (`appsflyer_staging`, `moengage_staging`, etc.) are views or intermediate tables used only by dbt. Query mart tables for all analysis.

---

## 17. App Store source

> **Status (2026-06-28):** Ingestion + transform code DONE. GCP infra NOT yet provisioned (Firza to provision). Analytics instances confirmed READY.

**Provision GCP (Firza to run):** see `docs/gcp-setup.md` sections 2 (sa-extract-app-store), 3 (IAM), 4 (App Store secrets), 6 (appstore datasets), 8 (create job).

Shortcut via Makefile:
```bash
make create-app-store PROJECT=your-gcp-project-id
```

**Rotating App Store secrets:**
```bash
# Key ID + Issuer ID
echo -n "NEW_KEY_ID:NEW_ISSUER_ID" | gcloud secrets versions add appstore-connect-key --data-file=- --project=$PROJECT

# .p8 file content
cat new.p8 | gcloud secrets versions add appstore-connect-key-p8 --data-file=- --project=$PROJECT
rm new.p8

gcloud secrets versions list appstore-connect-key --project=$PROJECT
gcloud secrets versions disable OLD_VERSION --secret=appstore-connect-key --project=$PROJECT
gcloud secrets versions list appstore-connect-key-p8 --project=$PROJECT
gcloud secrets versions disable OLD_VERSION --secret=appstore-connect-key-p8 --project=$PROJECT
```

> Secrets are read at runtime - no job restart needed after rotation.

**Reviews backfill (all-time, 11,488+ reviews since Mar 2018):**
```bash
gcloud run jobs execute extract-app-store \
  --region=asia-southeast2 \
  --project=$PROJECT \
  --update-env-vars="DATE_FROM=2018-01-01,DATE_TO=2026-06-28" \
  --wait
```

**Analytics historical backfill (ONE_TIME_SNAPSHOT - deferred until July 2026):**
- Quota: 1 snapshot per month per app. June 2026 quota already used.
- Run in July 2026:
```bash
cd tring-data-pipeline
uv run --with PyJWT --with cryptography --with requests python3 ../test-appstore/test_appstore_endpoints.py --snapshot
```
Then wait 24-48h for Apple to generate instances, then run extract-app-store normally.

**App Store API details (do NOT hardcode in code):**
- Key ID and Issuer ID in `.env` (gitignored, loaded from Secret Manager in production)
- .p8 file at repo root (gitignored, loaded from Secret Manager in production)
- Analytics ONGOING request ID: `77203237-b1c3-40ed-bccf-ce4345c7d5ab` (override via `APPSTORE_ANALYTICS_REQUEST_ID` env var if request is recreated)
