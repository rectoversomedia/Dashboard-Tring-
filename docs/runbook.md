# Runbook: Dashboard Monitoring & AI Insight  -  Data Pipeline

> **Before you run any command here:** set your project once in the terminal: `export PROJECT=your-gcp-project-id`. Every command below uses `$PROJECT`. New to the terms used here (Workflow, Cloud Run Job, backfill, T-1)? See [index.md](index.md) for a glossary.

> **Schedule note:** Pipeline runs automatically twice daily via Cloud Scheduler (08:00 and 20:00 WIB). This schedule is a default assumption from the TSD - the client has not confirmed a final schedule. To update: `gcloud scheduler jobs update http pipeline-trigger-morning --schedule="0 H * * *" --location=asia-southeast2 --project=$PROJECT` (and same for `pipeline-trigger-afternoon`).

## 1. Triggering a manual pipeline run

> **Workflow behavior:** Workflow triggers extract-appsflyer and extract-moengage **in parallel**, polls each every 15s until SUCCEEDED (both must succeed), then triggers dbt-transform, polls until SUCCEEDED, then returns. Total duration ~6-7 minutes (verified 2026-06-21). If either extract fails (e.g. rate limit, API error), Workflow fails immediately  -  dbt does NOT run.

**Run pipeline (T-1 auto-computed):**
```bash
gcloud workflows run pipeline \
  --location=asia-southeast2 \
  --project=$PROJECT
```

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

**Step 3  -  Check dbt logs (look for PASS=93 ERROR=0):**
```bash
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="dbt-transform"' \
  --project=$PROJECT \
  --limit=50 \
  --order=desc \
  --format="table(timestamp,textPayload)"
```

Key lines to look for:
- `Done. PASS=93 WARN=0 ERROR=0` → success
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

The Play Console secret is a full SA key JSON (not a simple token). To rotate:

1. Go to GCP IAM > Service Accounts > `sa-extract-play-console` > Keys
2. Create a new key (JSON format) - download it
3. Add to Secret Manager:
```bash
cat new-sa-key.json | gcloud secrets versions add play-console-sa-key --data-file=- --project=$PROJECT
rm new-sa-key.json
```
4. Disable the old version:
```bash
gcloud secrets versions list play-console-sa-key --project=$PROJECT
gcloud secrets versions disable OLD_VERSION_NUMBER --secret=play-console-sa-key --project=$PROJECT
```
5. Delete the old key from GCP IAM to revoke it completely.

> If the SA key is compromised, disable the old Secret Manager version AND delete the key from GCP IAM immediately. The Cloud Run Job picks up the new version on the next execution (secrets are resolved at job start).

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

## 10. Checking for failures (no alerting provisioned)

There is no automated alert. Failures surface as a `FAILED` Workflow execution. Check periodically, or after a scheduled run:

1. List executions: `gcloud workflows executions list pipeline --location=asia-southeast2 --project=$PROJECT --limit=5`
2. A `FAILED` state names which step failed in its error message  -  describe it: `gcloud workflows executions describe EXECUTION_ID --workflow=pipeline --location=asia-southeast2 --project=$PROJECT`
3. Check Cloud Logging for that job (sections 2-3 above)

> **To add email/Slack alerting (optional):** create a Cloud Monitoring alert policy on metric `workflows.googleapis.com/finished_execution_count` filtered to `status="FAILED"`, attached to a notification channel (email/Slack/PagerDuty). This was left out of the initial handover scope.

Common causes:
- **HTTP 401 (AppsFlyer)**: Token expired → rotate token (Section 5)
- **HTTP 401 (MoEngage)**: Credentials invalid → rotate secret (Section 6)
- **HTTP 400 rate limit**: Daily quota exhausted → wait for UTC 00:00 reset
- **Empty response**: No data for that date window  -  normal for new apps or holidays
- **dbt ERROR=N**: Test failures → check which model, run `dbt build --select failing_model` locally

---

## 11. Adding a new source (App Store Connect)

**MoEngage** - fully implemented and E2E verified (2026-06-22: 599 campaigns, 4712 stats rows, exit(0), full pipeline SUCCEEDED). GCP infra provisioned (SA, secret, BQ datasets, Cloud Run Job `extract-moengage`). dbt models built (`stg_moengage_campaigns`, `stg_moengage_campaign_stats`, `mart_moengage_push`, `mart_moengage_campaign_analytics`). pipeline.yaml runs both extracts in parallel (PASS=93 WARN=0 ERROR=0).

**Play Console** - ingestion code implemented (2026-06-22: `client.py`, `endpoints.py`, `extract.py`, 16 tests PASS). Pulls 6 metric sets (crash rate, ANR rate, stuck wakelock, excessive wakeup, error count, slow start) + paginated reviews via Google Play Developer Reporting API and Android Publisher API. GCP infra NOT YET provisioned (SA, secret, BQ datasets, Cloud Run Job). dbt models NOT YET built. pipeline.yaml NOT YET updated to include play_console branch.

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

## 12. Deploying a change

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

## 13. Checking dbt model freshness

```bash
cd transform
dbt source freshness --profiles-dir . --target dev
```
