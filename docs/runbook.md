# Runbook: Dashboard Monitoring & AI Insight — Data Pipeline

## 1. Triggering a manual pipeline run

```bash
gcloud workflows run pipeline \
  --location=asia-southeast2 \
  --project=$PROJECT
```

Watch execution:
```bash
gcloud workflows executions list pipeline \
  --location=asia-southeast2 \
  --project=$PROJECT \
  --limit=5
```

## 2. Running a single extractor manually

```bash
gcloud run jobs execute extract-appsflyer \
  --region=asia-southeast2 \
  --project=$PROJECT \
  --update-env-vars="FROM_DATE=2026-06-13,TO_DATE=2026-06-14"
```

Check logs:
```bash
gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="extract-appsflyer"' \
  --project=$PROJECT \
  --limit=50 \
  --format=json
```

## 3. Backfilling historical data

Run the extractor job with a wider date window. Raw is append-only; staging deduplicates by latest `_ingested_at` per natural key, so re-runs are safe.

```bash
# Example: backfill last 30 days
gcloud run jobs execute extract-appsflyer \
  --region=asia-southeast2 \
  --project=$PROJECT \
  --update-env-vars="FROM_DATE=2026-05-01,TO_DATE=2026-05-31"
```

After extract completes, re-run dbt to rebuild staging and mart:
```bash
gcloud run jobs execute dbt-transform \
  --region=asia-southeast2 \
  --project=$PROJECT
```

## 4. Rotating the AppsFlyer API token

```bash
# Add a new version (old version stays until you destroy it)
echo -n "NEW_TOKEN_VALUE" | gcloud secrets versions add appsflyer-api-token \
  --data-file=- \
  --project=$PROJECT

# Verify new version is active
gcloud secrets versions list appsflyer-api-token --project=$PROJECT

# Disable old version after confirming new one works
gcloud secrets versions disable VERSION_NUMBER \
  --secret=appsflyer-api-token \
  --project=$PROJECT
```

## 5. Reading alerts

When an alert fires:

1. Check Cloud Workflows execution: `gcloud workflows executions list pipeline ...`
2. Find the failed step and check Cloud Logging for that job.
3. Common causes:
   - **HTTP 401**: AppsFlyer token expired. Rotate token (Section 4).
   - **HTTP 429**: Rate limit. Extractor has 3-attempt retry. If still failing, check AppsFlyer plan limits.
   - **Empty response**: No data for that date window. Normal for new apps or holidays.
   - **dbt test failure**: Check `dbt test` output in Cloud Logging. Run `dbt build --select failing_model` locally against dev.

## 6. Adding a new source (MoEngage, Play Console, App Store Connect)

1. Add a new package under `ingestion/src/tring_ingest/sources/<source_name>/`.
2. Implement `client.py`, `endpoints.py`, `extract.py` following the AppsFlyer pattern.
3. Add `--source <source_name>` to `cli.py`.
4. Add new BigQuery datasets in `infra/modules/bigquery/main.tf`.
5. Add new Cloud Run Job in `infra/modules/cloud_run_jobs/main.tf`.
6. Add new service account in `infra/modules/iam/main.tf`.
7. Add new secret in `infra/modules/secrets/main.tf`.
8. Add the new extract job to the parallel branch in `orchestration/workflows/pipeline.yaml`.
9. Add dbt models under `transform/models/staging/<source>/` and `transform/models/marts/<source>/`.

## 7. Checking dbt model freshness

```bash
cd transform
dbt source freshness --profiles-dir . --target dev
```

## 8. Deploying a change

```bash
# Dev — push to GitHub, Cloud Build triggers automatically
git push origin main

# Prod — push to client GitLab (VPN required)
# Cloud Build on client GCP picks up the push and deploys
git push client-gitlab main
```

## 9. Terraform state

State is local by default. For team use, configure GCS backend in `infra/envs/dev/main.tf`:
```hcl
backend "gcs" {
  bucket = "tf-state-dev"
  prefix = "terraform/state"
}
```
Create the bucket manually first (it cannot be managed by the Terraform it stores state for).
