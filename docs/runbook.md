# Runbook: Dashboard Monitoring & AI Insight  -  Data Pipeline

## 1. Triggering a manual pipeline run

> **Workflow behavior:** Workflow triggers extract-appsflyer, polls every 15s until SUCCEEDED, then triggers dbt-transform, polls until SUCCEEDED, then returns. Total duration ~2-5 minutes. If extract fails (e.g. rate limit, API error), Workflow fails immediately  -  dbt does NOT run.

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
duration: ~90-300s
```

Failed run output:
```
state: FAILED
error:
  context: "extract-appsflyer completed but not all tasks succeeded"
```

**Step 2  -  Check extract logs (look for "8 extracts succeeded" or errors):**
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

**Step 3  -  Check dbt logs (look for PASS=63 ERROR=0):**
```bash
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="dbt-transform"' \
  --project=$PROJECT \
  --limit=50 \
  --order=desc \
  --format="table(timestamp,textPayload)"
```

Key lines to look for:
- `Done. PASS=63 WARN=0 ERROR=0` → success
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

**Extract only (bypass Workflow):**
```bash
gcloud run jobs execute extract-appsflyer \
  --region=asia-southeast2 \
  --project=$PROJECT \
  --update-env-vars="DATE_FROM=2026-06-19,DATE_TO=2026-06-19"
```

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

## 6. Known issue: in_app_events rate limit

AppsFlyer limits: `in_app_events` 12 calls/day/app, `installs` 24/day/app. When hit:

- Error: `400 Bad Request`  -  "You've reached your maximum number of in-app event reports"
- Workflow state: `FAILED`  -  "extract-appsflyer completed but not all tasks succeeded"
- Resets at UTC 00:00 (07:00 WIB)
- Production schedule (2x/day) uses 4 calls/day  -  safely under 12 limit
- If hit in prod: check for runaway executions or excessive manual runs
- To increase limit: client contacts AppsFlyer CSM (hello@appsflyer.com)
- Reference: https://support.appsflyer.com/hc/en-us/articles/207034366

---

## 7. Checking for failures (no alerting provisioned)

There is no automated alert. Failures surface as a `FAILED` Workflow execution. Check periodically, or after a scheduled run:

1. List executions: `gcloud workflows executions list pipeline --location=asia-southeast2 --project=$PROJECT --limit=5`
2. A `FAILED` state names which step failed in its error message  -  describe it: `gcloud workflows executions describe EXECUTION_ID --workflow=pipeline --location=asia-southeast2 --project=$PROJECT`
3. Check Cloud Logging for that job (sections 2-3 above)

> **To add email/Slack alerting (optional):** create a Cloud Monitoring alert policy on metric `workflows.googleapis.com/finished_execution_count` filtered to `status="FAILED"`, attached to a notification channel (email/Slack/PagerDuty). This was left out of the initial handover scope.

Common causes:
- **HTTP 401**: AppsFlyer token expired → rotate token (Section 5)
- **HTTP 400 rate limit**: Daily quota exhausted → wait for UTC 00:00 reset
- **Empty response**: No data for that date window  -  normal for new apps or holidays
- **dbt ERROR=N**: Test failures → check which model, run `dbt build --select failing_model` locally

---

## 8. Adding a new source (MoEngage, Play Console, App Store Connect)

1. Add package under `ingestion/src/tring_ingest/sources/<source_name>/`
2. Implement `client.py`, `endpoints.py`, `extract.py` following AppsFlyer pattern
3. Add `--source <source_name>` to `cli.py`
4. Create new Cloud Run Job + SA + IAM (see `docs/gcp-setup.md`)
5. Add new extract job to `pipeline.yaml` as parallel branch (min 2 branches required)
6. Add dbt models under `transform/models/staging/<source>/` and `transform/models/marts/<source>/`

---

## 9. Deploying a change

```bash
# Build + push new image
gcloud builds submit . \
  --config=cloudbuild/build-push.yaml \
  --substitutions="_PROJECT=$PROJECT" \
  --project=$PROJECT

# Update Cloud Run Job to new image
gcloud run jobs update extract-appsflyer \
  --image=asia-southeast2-docker.pkg.dev/$PROJECT/tring-service/ingestion:latest \
  --region=asia-southeast2 \
  --project=$PROJECT

gcloud run jobs update dbt-transform \
  --image=asia-southeast2-docker.pkg.dev/$PROJECT/tring-service/dbt:latest \
  --region=asia-southeast2 \
  --project=$PROJECT
```

---

## 10. Checking dbt model freshness

```bash
cd transform
dbt source freshness --profiles-dir . --target dev
```
