# GCP Setup Guide

One-time provisioning steps for each GCP project (dev or prod). Run as a user with sufficient IAM permissions (see Setup User Roles at the bottom).

Set project once:
```bash
export PROJECT=YOUR_GCP_PROJECT_ID   # dev or prod  -  never hardcode, always set explicitly
```

---

## 1. Enable APIs

```bash
gcloud services enable run.googleapis.com secretmanager.googleapis.com workflows.googleapis.com iam.googleapis.com storage.googleapis.com logging.googleapis.com monitoring.googleapis.com bigquery.googleapis.com artifactregistry.googleapis.com cloudscheduler.googleapis.com cloudbuild.googleapis.com --project=$PROJECT
```

---

## 2. Create Service Accounts

```bash
gcloud iam service-accounts create sa-extract-appsflyer --display-name="AppsFlyer extractor runtime" --project=$PROJECT
gcloud iam service-accounts create sa-dbt --display-name="dbt transform runtime" --project=$PROJECT
gcloud iam service-accounts create sa-workflows --display-name="Cloud Workflows orchestrator" --project=$PROJECT
gcloud iam service-accounts create sa-scheduler --display-name="Cloud Scheduler trigger" --project=$PROJECT
```

> **Adding a new source (MoEngage, Play Console, App Store Connect):** create a dedicated SA per source  -  `sa-extract-moengage`, `sa-extract-playstore`, etc. Grant only the roles that source needs. Never reuse an existing extractor SA for a different source.

---

## 3. Grant IAM Roles

### sa-extract-appsflyer
Runs the Cloud Run Job that pulls AppsFlyer API and loads into BigQuery raw.

```bash
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:sa-extract-appsflyer@${PROJECT}.iam.gserviceaccount.com" --role="roles/bigquery.dataEditor"
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:sa-extract-appsflyer@${PROJECT}.iam.gserviceaccount.com" --role="roles/bigquery.jobUser"
gcloud secrets add-iam-policy-binding appsflyer-api-token --member="serviceAccount:sa-extract-appsflyer@${PROJECT}.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor" --project=$PROJECT
```

### sa-dbt
Runs the dbt Cloud Run Job (reads staging, writes mart).

```bash
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:sa-dbt@${PROJECT}.iam.gserviceaccount.com" --role="roles/bigquery.dataEditor"
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:sa-dbt@${PROJECT}.iam.gserviceaccount.com" --role="roles/bigquery.jobUser"
```

### sa-workflows
Triggers Cloud Run Jobs from Cloud Workflows via v2 API.

```bash
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:sa-workflows@${PROJECT}.iam.gserviceaccount.com" --role="roles/run.invoker"
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:sa-workflows@${PROJECT}.iam.gserviceaccount.com" --role="roles/run.developer"
```

> `roles/run.invoker` alone is not enough for Cloud Run Jobs via v2 API. `roles/run.developer` grants `run.jobs.run` which is required to execute jobs via `https://run.googleapis.com/v2/.../jobs:run`.

### sa-scheduler
Triggers Cloud Workflows from Cloud Scheduler.

```bash
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:sa-scheduler@${PROJECT}.iam.gserviceaccount.com" --role="roles/workflows.invoker"
```

---

## 4. Create Secret Manager Secret

Create the container first (empty):
```bash
gcloud secrets create appsflyer-api-token --replication-policy="automatic" --project=$PROJECT
```

Then add the token value (never put token in code or git):
```bash
echo -n "YOUR_APPSFLYER_TOKEN" | gcloud secrets versions add appsflyer-api-token --data-file=- --project=$PROJECT
```

Token source: AppsFlyer dashboard > Configuration > API Token v3.

> **Handover note:** The token does not need to go through the developer. The client (or their GCP admin) can retrieve it directly from AppsFlyer and run the command above themselves. The developer never needs to see the production token.

To rotate:
```bash
echo -n "NEW_TOKEN" | gcloud secrets versions add appsflyer-api-token --data-file=- --project=$PROJECT
```

---

## 5. Create Artifact Registry Repository

```bash
gcloud artifacts repositories create tring-service --repository-format=docker --location=asia-southeast2 --project=$PROJECT
```

---

## 6. Create BigQuery Datasets

```bash
bq --project_id=$PROJECT mk --location=asia-southeast2 appsflyer_raw
bq --project_id=$PROJECT mk --location=asia-southeast2 appsflyer_staging
bq --project_id=$PROJECT mk --location=asia-southeast2 appsflyer_mart
```

> Three datasets, one per layer: `appsflyer_raw` (ingestion landing), `appsflyer_staging` (dbt staging views `stg_*`), `appsflyer_mart` (dbt mart tables `mart_*`). dbt resolves the staging/mart datasets from a base name plus a per-folder `+schema` (base `appsflyer`, `+schema: staging` or `mart` in `dbt_project.yml`). The raw dataset is also auto-created by the ingestion code on first run (safe to skip), but create all three explicitly for clarity.

---

## 7. Build and Push Container Images

No Docker Desktop required. All builds run via Cloud Build.

**One-time auth:**
```bash
gcloud auth configure-docker asia-southeast2-docker.pkg.dev --project=$PROJECT
```

**Build + push both images:**
```bash
gcloud builds submit . \
  --config=cloudbuild/build-push.yaml \
  --substitutions="_PROJECT=${PROJECT}" \
  --project=$PROJECT
```

This builds `ingestion` and `dbt` images and pushes them to:
```
asia-southeast2-docker.pkg.dev/${PROJECT}/tring-service/ingestion:latest
asia-southeast2-docker.pkg.dev/${PROJECT}/tring-service/dbt:latest
```

**Verify:**
```bash
gcloud artifacts docker images list asia-southeast2-docker.pkg.dev/${PROJECT}/tring-service --project=$PROJECT
```

---

## 8. Deploy Cloud Run Jobs

> **Note on date args:** dates are not set at job creation. Cloud Workflows injects them at runtime via `containerOverrides.env` (`DATE_FROM`/`DATE_TO`). For manual backfill, use `gcloud run jobs execute` with `--update-env-vars="DATE_FROM=...,DATE_TO=..."` (see runbook section 3).

```bash
REGISTRY=asia-southeast2-docker.pkg.dev

# extract-appsflyer
# --command and --args set the entrypoint; dates are injected by Workflow at runtime
gcloud run jobs create extract-appsflyer \
  --image=${REGISTRY}/${PROJECT}/tring-service/ingestion:latest \
  --region=asia-southeast2 \
  --service-account=sa-extract-appsflyer@${PROJECT}.iam.gserviceaccount.com \
  --set-env-vars="GCP_PROJECT=${PROJECT},BQ_DATASET_RAW=appsflyer_raw,REGION=asia-southeast2" \
  --set-secrets="APPSFLYER_API_TOKEN=appsflyer-api-token:latest" \
  --command=python \
  --args="-m,tring_ingest,--source,appsflyer" \
  --memory=4Gi \
  --cpu=2 \
  --project=$PROJECT

# dbt-transform
# ENTRYPOINT is hardcoded in Dockerfile: ["dbt", "build", "--profiles-dir", "/app", "--target", "prod"]
# Do NOT set --command or --args here  -  they override the Dockerfile ENTRYPOINT and break dbt
gcloud run jobs create dbt-transform \
  --image=${REGISTRY}/${PROJECT}/tring-service/dbt:latest \
  --region=asia-southeast2 \
  --service-account=sa-dbt@${PROJECT}.iam.gserviceaccount.com \
  --set-env-vars="GCP_PROJECT=${PROJECT}" \
  --project=$PROJECT
```

> **extract-appsflyer date args:** dates (`--from`/`--to`) are passed via env vars `DATE_FROM`/`DATE_TO` at runtime  -  either by Cloud Workflows (`containerOverrides.env`) or by `--update-env-vars` on manual execute. The job itself has no default dates.

**Test manual run extract (T-1):**
```bash
YESTERDAY=$(date -u -v-1d +%Y-%m-%d)
gcloud run jobs execute extract-appsflyer \
  --region=asia-southeast2 \
  --project=$PROJECT \
  --update-env-vars="DATE_FROM=${YESTERDAY},DATE_TO=${YESTERDAY}"
```

**Test manual run dbt:**
```bash
gcloud run jobs execute dbt-transform \
  --region=asia-southeast2 \
  --project=$PROJECT
```

**Check extract logs:**
```bash
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="extract-appsflyer"' \
  --project=$PROJECT \
  --limit=50 \
  --order=desc \
  --format="table(timestamp,textPayload)"
```

**Check dbt logs:**
```bash
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="dbt-transform"' \
  --project=$PROJECT \
  --limit=50 \
  --order=desc \
  --format="table(timestamp,textPayload)"
```

**Rebuild images and update jobs after code change:**
```bash
gcloud builds submit . \
  --config=cloudbuild/build-push.yaml \
  --substitutions="_PROJECT=${PROJECT}" \
  --project=$PROJECT

gcloud run jobs update extract-appsflyer \
  --image=${REGISTRY}/${PROJECT}/tring-service/ingestion:latest \
  --region=asia-southeast2 \
  --project=$PROJECT

gcloud run jobs update dbt-transform \
  --image=${REGISTRY}/${PROJECT}/tring-service/dbt:latest \
  --region=asia-southeast2 \
  --project=$PROJECT
```

---

## 9. Deploy Cloud Workflows

> **Troubleshooting:** If you get `FAILED_PRECONDITION: Workflows service agent does not exist`, run:
> ```bash
> gcloud services enable workflows.googleapis.com --project=$PROJECT
> PROJECT_NUMBER=$(gcloud projects describe $PROJECT --format='value(projectNumber)')
> gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-workflows.iam.gserviceaccount.com" --role="roles/workflows.serviceAgent"
> ```

> **Note on parallel branches:** `pipeline.yaml` currently runs AppsFlyer as a sequential step (not `parallel`) because Cloud Workflows requires minimum 2 branches for parallel execution. When MoEngage/Play Console sources are added, convert back to `parallel` with 2+ branches.

```bash
gcloud workflows deploy pipeline \
  --location=asia-southeast2 \
  --source=orchestration/workflows/pipeline.yaml \
  --service-account=sa-workflows@${PROJECT}.iam.gserviceaccount.com \
  --project=$PROJECT
```

Verify deploy succeeded (`state: ACTIVE`):
```bash
gcloud workflows describe pipeline \
  --location=asia-southeast2 \
  --project=$PROJECT
```

---

## 10. Create Cloud Scheduler Jobs

```bash
# 08:00 WIB (01:00 UTC)
gcloud scheduler jobs create http pipeline-trigger-morning \
  --location=asia-southeast2 \
  --schedule="0 1 * * *" \
  --time-zone="Asia/Jakarta" \
  --uri="https://workflowexecutions.googleapis.com/v1/projects/${PROJECT}/locations/asia-southeast2/workflows/pipeline/executions" \
  --message-body="{}" \
  --oauth-service-account-email=sa-scheduler@${PROJECT}.iam.gserviceaccount.com \
  --project=$PROJECT

# 20:00 WIB (13:00 UTC)
gcloud scheduler jobs create http pipeline-trigger-afternoon \
  --location=asia-southeast2 \
  --schedule="0 13 * * *" \
  --time-zone="Asia/Jakarta" \
  --uri="https://workflowexecutions.googleapis.com/v1/projects/${PROJECT}/locations/asia-southeast2/workflows/pipeline/executions" \
  --message-body="{}" \
  --oauth-service-account-email=sa-scheduler@${PROJECT}.iam.gserviceaccount.com \
  --project=$PROJECT
```

---

## Note on Terraform

The `infra/` directory contains Terraform modules that codify all of the above as infrastructure-as-code. Terraform is **optional**  -  the `gcloud` commands above are the authoritative deploy method and produce identical results.

**When to use Terraform:**
- Client wants full IaC reproducibility for their prod environment
- Multiple environments need to stay in sync
- Team wants drift detection via `terraform plan`

**When to skip Terraform (current approach):**
- Prod runs on client GitLab + VPN  -  Terraform state backend (GCS) adds complexity in a VPN-gated environment
- `gcloud` commands in this guide are sufficient, explicit, and auditable
- Terraform is available in `infra/` as a reference and can be adopted later without changing anything else

If the client wants to adopt Terraform later: copy `infra/envs/prod/terraform.tfvars.example` to `terraform.tfvars`, fill in values, run `terraform init && terraform apply`. All modules are already written.

---

## IAM Summary

| Service Account | Role | Scope |
|---|---|---|
| sa-extract-appsflyer | bigquery.dataEditor | project |
| sa-extract-appsflyer | bigquery.jobUser | project |
| sa-extract-appsflyer | secretmanager.secretAccessor | secret: appsflyer-api-token only |
| sa-dbt | bigquery.dataEditor | project |
| sa-dbt | bigquery.jobUser | project |
| sa-workflows | run.invoker | project |
| sa-workflows | run.developer | project |
| sa-scheduler | workflows.invoker | project |

## Setup User Roles

Human account running the above commands needs:

| Role | Why |
|---|---|
| roles/iam.serviceAccountAdmin | Create service accounts |
| roles/secretmanager.admin | Create and bind secrets |
| roles/artifactregistry.admin | Create Docker repo |
| roles/bigquery.admin | Create datasets |
| roles/run.admin | Deploy Cloud Run Jobs |
| roles/workflows.admin | Deploy Cloud Workflows |
| roles/cloudscheduler.admin | Deploy Cloud Scheduler jobs |
