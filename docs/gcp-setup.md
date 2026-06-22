# GCP Setup Guide

One-time provisioning steps for each GCP project (dev or prod).

> **Before you start - your GCP account needs these roles on the project:**
>
> | Role | Why you need it |
> |---|---|
> | `roles/iam.serviceAccountAdmin` | Create service accounts (Section 2) |
> | `roles/secretmanager.admin` | Create secrets and bind IAM on them (Sections 3-4) |
> | `roles/artifactregistry.admin` | Create the Docker image repository (Section 5) |
> | `roles/bigquery.admin` | Create datasets (Section 6) |
> | `roles/run.admin` | Create and update Cloud Run Jobs (Section 8) |
> | `roles/workflows.admin` | Deploy Cloud Workflows (Section 9) |
> | `roles/cloudscheduler.admin` | Create Cloud Scheduler jobs (Section 10) |
> | `roles/cloudbuild.builds.editor` | Submit Cloud Build jobs (Sections 7-8) |
>
> Check your current roles: GCP Console > IAM & Admin > IAM > filter by your email. If any role is missing, ask your GCP org admin to grant it before proceeding. Commands fail with `PERMISSION_DENIED` without the right roles.

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
gcloud iam service-accounts create sa-extract-moengage --display-name="MoEngage extractor runtime" --project=$PROJECT
gcloud iam service-accounts create sa-extract-play-console --display-name="Play Console extractor runtime" --project=$PROJECT
gcloud iam service-accounts create sa-dbt --display-name="dbt transform runtime" --project=$PROJECT
gcloud iam service-accounts create sa-workflows --display-name="Cloud Workflows orchestrator" --project=$PROJECT
gcloud iam service-accounts create sa-scheduler --display-name="Cloud Scheduler trigger" --project=$PROJECT
```

> **Play Console exception:** the `extract-play-console` job does NOT use a dedicated SA for Play Console API auth. It authenticates to the Play Console using a SA key from the client's production GCP project (`pgd-prd-digital-rating-tring`), stored as a JSON string in Secret Manager (`play-console-sa-key`). The Cloud Run Job itself still runs under a runtime SA (`sa-extract-play-console`) that has only BQ + Secret Manager access. See Section 4 (Play Console) for details.

> **Adding a new source (App Store Connect):** create a dedicated SA per source. Grant only the roles that source needs.

---

## 3. Grant IAM Roles

> **Order note:** the `gcloud secrets add-iam-policy-binding ...` lines below reference secrets (`appsflyer-api-token`, `moengage-api-creds`, `play-console-sa-key`) that are created in Section 4. If you run this section strictly before Section 4, those secret-binding lines fail with "secret not found." Two ways to handle it: either create the secrets first (run Section 4, then come back here), or run only the `projects add-iam-policy-binding` lines here now and run each `secrets add-iam-policy-binding` line right after you create that secret in Section 4. The `projects` (BigQuery) bindings can run in any order.

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

### sa-extract-moengage
Runs the MoEngage extract Cloud Run Job.

```bash
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:sa-extract-moengage@${PROJECT}.iam.gserviceaccount.com" --role="roles/bigquery.dataEditor"
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:sa-extract-moengage@${PROJECT}.iam.gserviceaccount.com" --role="roles/bigquery.jobUser"
gcloud secrets add-iam-policy-binding moengage-api-creds --member="serviceAccount:sa-extract-moengage@${PROJECT}.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor" --project=$PROJECT
```

### sa-extract-play-console (runtime SA for the Cloud Run Job)

This SA is the runtime identity of the Cloud Run Job — it writes to BigQuery and reads the Play Console SA key from Secret Manager. It does NOT authenticate to the Play Console API directly (that auth uses the SA key JSON stored in the secret).

> SA was already created in Section 2. Only the IAM bindings are added here.

```bash
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:sa-extract-play-console@${PROJECT}.iam.gserviceaccount.com" --role="roles/bigquery.dataEditor"
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:sa-extract-play-console@${PROJECT}.iam.gserviceaccount.com" --role="roles/bigquery.jobUser"
gcloud secrets add-iam-policy-binding play-console-sa-key --member="serviceAccount:sa-extract-play-console@${PROJECT}.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor" --project=$PROJECT
```

### sa-scheduler
Triggers Cloud Workflows from Cloud Scheduler.

```bash
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:sa-scheduler@${PROJECT}.iam.gserviceaccount.com" --role="roles/workflows.invoker"
```

---

## 4. Create Secret Manager Secrets

### AppsFlyer

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

### MoEngage

The MoEngage secret stores both credentials as a single colon-delimited string (`WORKSPACE_ID:API_KEY`). Get the values from the MoEngage dashboard > Settings > APIs.

```bash
gcloud secrets create moengage-api-creds --replication-policy="automatic" --project=$PROJECT

# Value format: WORKSPACE_ID:API_KEY  (colon-separated, no spaces)
# Never commit the actual values - add them directly in the terminal
echo -n "YOUR_WORKSPACE_ID:YOUR_API_KEY" | gcloud secrets versions add moengage-api-creds --data-file=- --project=$PROJECT
```

To rotate:
```bash
echo -n "NEW_WORKSPACE_ID:NEW_API_KEY" | gcloud secrets versions add moengage-api-creds --data-file=- --project=$PROJECT
```

### Play Console

The Play Console secret stores a service account key JSON. This is the one case where the key comes from a **different** GCP project than the one you are provisioning. There are two projects:

- **Your pipeline project** (`$PROJECT`) - where this secret lives.
- **The Play Console source project** (`pgd-prd-digital-rating-tring`) - which owns the SA `dashboard-monitoring-aiinsight@pgd-prd-digital-rating-tring.iam.gserviceaccount.com`. That SA already has Play Developer Reporting API and Android Publisher API access granted via Google Play Console. You do not create a new SA and you do not touch the Play Console UI.

**Step 1 - get the SA key JSON file.** You need a JSON key for `dashboard-monitoring-aiinsight` in `pgd-prd-digital-rating-tring`:

- If you have IAM access to that project: GCP Console > IAM & Admin > Service Accounts > pick `dashboard-monitoring-aiinsight` > Keys > Add Key > Create new key > JSON. Download it to the repo root.
- If you do not have access to that project (likely, it is a separate production project owned by another team): ask whoever owns `pgd-prd-digital-rating-tring` to generate the JSON key and send it to you over a secure channel (a secret-sharing tool, never email or chat).

Save the downloaded file at the repo root. The `.gitignore` blocks `*.json`, so it cannot be committed by accident. Do not put it anywhere else.

**Step 2 - load it into Secret Manager in your pipeline project:**

```bash
gcloud secrets create play-console-sa-key --replication-policy="automatic" --project=$PROJECT

# Replace play-console-sa-key.json with the actual filename you downloaded in Step 1.
cat play-console-sa-key.json | gcloud secrets versions add play-console-sa-key --data-file=- --project=$PROJECT

# Delete the local key file once it is in Secret Manager.
rm play-console-sa-key.json
```

> **Important:** The SA key JSON grants access to the client's production Play Console data. Treat it like a password. The `.gitignore` at repo root blocks `*.json` so it cannot be committed accidentally. Never store the key file anywhere outside the repo root or Secret Manager.

To rotate (when the client generates a new key):
```bash
# Client generates new key from their GCP IAM, sends securely
cat new-sa-key.json | gcloud secrets versions add play-console-sa-key --data-file=- --project=$PROJECT
rm new-sa-key.json
gcloud secrets versions list play-console-sa-key --project=$PROJECT
gcloud secrets versions disable OLD_VERSION_NUMBER --secret=play-console-sa-key --project=$PROJECT
```

---

## 5. Create Artifact Registry Repository

```bash
gcloud artifacts repositories create tring-service --repository-format=docker --location=asia-southeast2 --project=$PROJECT
```

---

## 6. Create BigQuery Datasets

### AppsFlyer

```bash
bq --project_id=$PROJECT mk --location=asia-southeast2 appsflyer_raw
bq --project_id=$PROJECT mk --location=asia-southeast2 appsflyer_staging
bq --project_id=$PROJECT mk --location=asia-southeast2 appsflyer_mart
```

> Three datasets per source, one per layer: raw (ingestion landing, append-only), staging (dbt `stg_*` views, typed + deduplicated), mart (dbt `mart_*` tables, full-refresh, dashboard-ready). dbt resolves dataset names from base + per-folder `+schema` in `dbt_project.yml`.

### MoEngage

```bash
bq --project_id=$PROJECT mk --location=asia-southeast2 moengage_raw
bq --project_id=$PROJECT mk --location=asia-southeast2 moengage_staging
bq --project_id=$PROJECT mk --location=asia-southeast2 moengage_mart
```

### Play Console

```bash
bq --project_id=$PROJECT mk --location=asia-southeast2 play_raw
bq --project_id=$PROJECT mk --location=asia-southeast2 play_staging
bq --project_id=$PROJECT mk --location=asia-southeast2 play_mart
```

---

## 7. Build and Push Container Images

No Docker Desktop required. All builds run inside Cloud Build on GCP — nothing runs on your laptop.

There are two Cloud Build config files in `cloudbuild/`:
- `build-push.yaml` — used here (Section 7). Builds both Docker images and pushes them to Artifact Registry. Does NOT deploy or touch Cloud Run Jobs.
- `deploy-prod.yaml` — used by the automated CI/CD trigger (handover.md Steps 4-5). Builds images AND rolls them onto the existing Cloud Run Jobs. Used after the jobs are created.

You use `build-push.yaml` here because the Cloud Run Jobs do not exist yet — they are created in Section 8 using these images.

**One-time auth (allow gcloud to push to Artifact Registry):**
```bash
gcloud auth configure-docker asia-southeast2-docker.pkg.dev --project=$PROJECT
```

**Build both images and push:**
```bash
gcloud builds submit . \
  --config=cloudbuild/build-push.yaml \
  --substitutions="_PROJECT=${PROJECT}" \
  --project=$PROJECT
```

This builds `ingestion/Dockerfile` (used by all 3 extract jobs) and `transform/Dockerfile` (used by dbt-transform), then pushes them to:
```
asia-southeast2-docker.pkg.dev/${PROJECT}/tring-service/ingestion:latest
asia-southeast2-docker.pkg.dev/${PROJECT}/tring-service/dbt:latest
```

The command uploads your local code to Cloud Build and streams build logs. It takes 3-5 minutes. A `SUCCESS` at the end means both images are ready in Artifact Registry.

**Verify images are there:**
```bash
gcloud artifacts docker images list asia-southeast2-docker.pkg.dev/${PROJECT}/tring-service --project=$PROJECT
```

You should see two image paths: one for `ingestion`, one for `dbt`.

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

# extract-moengage (same ingestion image, different --source arg)
gcloud run jobs create extract-moengage \
  --image=${REGISTRY}/${PROJECT}/tring-service/ingestion:latest \
  --region=asia-southeast2 \
  --service-account=sa-extract-moengage@${PROJECT}.iam.gserviceaccount.com \
  --set-env-vars="GCP_PROJECT=${PROJECT},BQ_DATASET_RAW_MOENGAGE=moengage_raw,REGION=asia-southeast2" \
  --set-secrets="MOENGAGE_API_CREDS=moengage-api-creds:latest" \
  --command=python \
  --args="-m,tring_ingest,--source,moengage" \
  --memory=2Gi \
  --cpu=1 \
  --max-retries=0 \
  --project=$PROJECT

# extract-play-console (same ingestion image, --source play_console)
# PLAY_CONSOLE_SECRET_NAME tells config.py which Secret Manager secret to fetch the SA key JSON from.
# The code (config.py) reads this env var as the *name* of the secret, then calls Secret Manager API
# to fetch the actual key content at runtime. Default is "play-console-sa-key" (matches secret created in Section 4).
gcloud run jobs create extract-play-console \
  --image=${REGISTRY}/${PROJECT}/tring-service/ingestion:latest \
  --region=asia-southeast2 \
  --service-account=sa-extract-play-console@${PROJECT}.iam.gserviceaccount.com \
  --set-env-vars="GCP_PROJECT=${PROJECT},BQ_DATASET_RAW_PLAY_CONSOLE=play_raw,REGION=asia-southeast2,PLAY_CONSOLE_SECRET_NAME=play-console-sa-key" \
  --command=python \
  --args="-m,tring_ingest,--source,play_console" \
  --memory=2Gi \
  --cpu=1 \
  --max-retries=0 \
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

> **How dbt authenticates to BigQuery (no key file):** `transform/profiles.yml` uses `method: oauth`. Inside the Cloud Run Job this means dbt uses Application Default Credentials, which resolve to the job's runtime service account `sa-dbt`. That is why `sa-dbt` needs `bigquery.dataEditor` + `bigquery.jobUser` (granted in section 3) and nothing else. There is no interactive login and no key file inside the container, this is expected. Running dbt locally uses your own `gcloud auth application-default login` credentials instead.

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

gcloud run jobs update extract-moengage \
  --image=${REGISTRY}/${PROJECT}/tring-service/ingestion:latest \
  --region=asia-southeast2 \
  --project=$PROJECT

gcloud run jobs update extract-play-console \
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

The `infra/` directory contains Terraform modules that codify the AppsFlyer infrastructure as infrastructure-as-code. Terraform is **optional**  -  the `gcloud` commands above are the authoritative deploy method and are the only fully maintained path.

> **Terraform is AppsFlyer-only and lags the gcloud path.** The `infra/` modules do NOT yet provision the MoEngage resources (sa-extract-moengage, the moengage-api-creds secret, the extract-moengage Cloud Run Job, and its IAM). If you adopt Terraform, you must add those yourself or provision MoEngage via the gcloud commands in Sections 2-8 above. The gcloud commands in this guide are complete for both sources; the Terraform modules are not.

**When to use Terraform:**
- Client wants full IaC reproducibility for their prod environment
- Multiple environments need to stay in sync
- Team wants drift detection via `terraform plan`

**When to skip Terraform (current approach):**
- Prod runs on client GitLab + VPN  -  Terraform state backend (GCS) adds complexity in a VPN-gated environment
- `gcloud` commands in this guide are sufficient, explicit, and auditable
- Terraform is available in `infra/` as a reference and can be adopted later without changing anything else

If the client wants to adopt Terraform later: copy `infra/envs/prod/terraform.tfvars.example` to `terraform.tfvars`, fill in values, run `terraform init && terraform apply`. The AppsFlyer modules are written; MoEngage resources still need to be added to the modules (or provisioned via gcloud) as noted above.

---

## IAM Summary

| Service Account | Role | Scope |
|---|---|---|
| sa-extract-appsflyer | bigquery.dataEditor | project |
| sa-extract-appsflyer | bigquery.jobUser | project |
| sa-extract-appsflyer | secretmanager.secretAccessor | secret: appsflyer-api-token only |
| sa-extract-moengage | bigquery.dataEditor | project |
| sa-extract-moengage | bigquery.jobUser | project |
| sa-extract-moengage | secretmanager.secretAccessor | secret: moengage-api-creds only |
| sa-extract-play-console | bigquery.dataEditor | project |
| sa-extract-play-console | bigquery.jobUser | project |
| sa-extract-play-console | secretmanager.secretAccessor | secret: play-console-sa-key only |
| sa-dbt | bigquery.dataEditor | project |
| sa-dbt | bigquery.jobUser | project |
| sa-workflows | run.invoker | project |
| sa-workflows | run.developer | project |
| sa-scheduler | workflows.invoker | project |

## Setup User Roles

See the role table at the top of this file (Before you start section). Check your roles in GCP Console > IAM & Admin > IAM before running any section.
