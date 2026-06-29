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
> | `roles/monitoring.editor` | Create notification channels and alert policies (Section 11, optional) |
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
gcloud iam service-accounts create sa-extract-app-store --display-name="App Store extractor runtime" --project=$PROJECT
gcloud iam service-accounts create sa-dbt --display-name="dbt transform runtime" --project=$PROJECT
gcloud iam service-accounts create sa-workflows --display-name="Cloud Workflows orchestrator" --project=$PROJECT
gcloud iam service-accounts create sa-scheduler --display-name="Cloud Scheduler trigger" --project=$PROJECT
```

> **Play Console exception:** the `extract-play-console` job does NOT use a dedicated SA for Play Console API auth. It authenticates to the Play Console using a SA key from the client's production GCP project (`pgd-prd-digital-rating-tring`), stored as a JSON string in Secret Manager (`play-console-sa-key`). The Cloud Run Job itself still runs under a runtime SA (`sa-extract-play-console`) that has only BQ + Secret Manager access. See Section 4 (Play Console) for details.

> **Adding a new source (App Store Connect):** create a dedicated SA per source. Grant only the roles that source needs.

> **Why one SA per source (not one shared SA)?**
> Three reasons:
> 1. **Least privilege.** Each SA only has `secretAccessor` on its own secret. A shared SA would have access to all secrets - one compromised job exposes all API credentials.
> 2. **Blast radius.** A misconfigured or revoked shared SA kills the whole pipeline. Per-source SA means one source goes down, the rest keep running.
> 3. **Cloud Run is keyless.** Jobs run *as* their attached SA via Application Default Credentials - no JSON key file needed on disk. Switching to a shared SA key file (e.g. a downloaded `.json`) is a downgrade: key rotation is manual, the file can be copied or leaked, and it bypasses GCP's native identity model.
>
> Play Console is the one exception where a key file is unavoidable: the API belongs to a different GCP project (`pgd-prd-digital-rating-tring`), so there is no way to attach that project's SA as a Cloud Run identity. The key is stored in Secret Manager (not on disk or in code) to limit exposure.

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

This SA is the runtime identity of the Cloud Run Job - it writes to BigQuery and reads the Play Console SA key from Secret Manager. It does NOT authenticate to the Play Console API directly (that auth uses the SA key JSON stored in the secret).

> SA was already created in Section 2. Only the IAM bindings are added here.

```bash
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:sa-extract-play-console@${PROJECT}.iam.gserviceaccount.com" --role="roles/bigquery.dataEditor"
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:sa-extract-play-console@${PROJECT}.iam.gserviceaccount.com" --role="roles/bigquery.jobUser"
gcloud secrets add-iam-policy-binding play-console-sa-key --member="serviceAccount:sa-extract-play-console@${PROJECT}.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor" --project=$PROJECT
```

### sa-extract-app-store
Runs the App Store extract Cloud Run Job. Uses two secrets (key ID:issuer ID + .p8 content), accessed at runtime via Secret Manager client.

```bash
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:sa-extract-app-store@${PROJECT}.iam.gserviceaccount.com" --role="roles/bigquery.dataEditor"
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:sa-extract-app-store@${PROJECT}.iam.gserviceaccount.com" --role="roles/bigquery.jobUser"
gcloud secrets add-iam-policy-binding appstore-connect-key --member="serviceAccount:sa-extract-app-store@${PROJECT}.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor" --project=$PROJECT
gcloud secrets add-iam-policy-binding appstore-connect-key-p8 --member="serviceAccount:sa-extract-app-store@${PROJECT}.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor" --project=$PROJECT
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

> **Play Console access is tied to a specific SA email.** The SA `dashboard-monitoring-aiinsight@pgd-prd-digital-rating-tring.iam.gserviceaccount.com` has already been invited to Google Play Console for the app **Tring! by Pegadaian** (`com.pegadaiandigital`). If you ever need to use a different SA, you must invite it to Play Console first - generating a key and loading it into Secret Manager is not enough on its own.
>
> **To invite a new SA to Play Console:**
> 1. Go to [play.google.com/console](https://play.google.com/console) and open the Tring! by Pegadaian app.
> 2. Left menu → **Users and permissions**.
> 3. Click **Invite new users**.
> 4. Enter the new SA email address.
> 5. Under **App permissions**, select `com.pegadaiandigital` and grant at minimum: **View app information and download bulk reports (read-only)**.
> 6. Click **Send invitation** → **Apply**.
> 7. Wait a few minutes for the permission to propagate before proceeding.

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

### App Store Connect

Two secrets required. The key ID and issuer ID are in `.env`; the .p8 file is at repo root (gitignored, never commit).

```bash
gcloud secrets create appstore-connect-key --replication-policy="automatic" --project=$PROJECT

# Value format: KEY_ID:ISSUER_ID  (colon-separated, no spaces)
# Get values from .env (APPSTORE_KEY_ID and APPSTORE_ISSUER_ID)
echo -n "YOUR_KEY_ID:YOUR_ISSUER_ID" | gcloud secrets versions add appstore-connect-key --data-file=- --project=$PROJECT

gcloud secrets create appstore-connect-key-p8 --replication-policy="automatic" --project=$PROJECT

# Value: full content of AuthKey_XXXXXXXX.p8 (the .p8 file, NOT the path)
cat AuthKey_3JJKJT5QCK.p8 | gcloud secrets versions add appstore-connect-key-p8 --data-file=- --project=$PROJECT
```

> **Security note:** the .p8 file grants signing authority for App Store Connect API. Store only in Secret Manager. Delete local copy once loaded: `rm AuthKey_3JJKJT5QCK.p8`. The `.gitignore` blocks `*.p8` so it cannot be committed accidentally.

To rotate (new key generated in App Store Connect):
```bash
echo -n "NEW_KEY_ID:NEW_ISSUER_ID" | gcloud secrets versions add appstore-connect-key --data-file=- --project=$PROJECT
cat new.p8 | gcloud secrets versions add appstore-connect-key-p8 --data-file=- --project=$PROJECT
rm new.p8
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

### App Store

```bash
bq --project_id=$PROJECT mk --location=asia-southeast2 appstore_raw
bq --project_id=$PROJECT mk --location=asia-southeast2 appstore_staging
bq --project_id=$PROJECT mk --location=asia-southeast2 appstore_mart
```

### Dashboard (pre-aggregated layer for Looker Studio)

```bash
bq --project_id=$PROJECT mk --location=asia-southeast2 dashboard
```

Also grant `sa-dbt` write access to the new dataset:

```bash
bq show --format=prettyjson --project_id=$PROJECT dashboard > /tmp/dashboard_acl.json
# add this entry to the "access" array in /tmp/dashboard_acl.json:
# {"role": "WRITER", "userByEmail": "sa-dbt@$PROJECT.iam.gserviceaccount.com"}
bq update --project_id=$PROJECT --source /tmp/dashboard_acl.json dashboard
```

Or use the simpler IAM binding (if sa-dbt already has project-level bigquery.dataEditor):

```bash
# no extra step needed if sa-dbt has roles/bigquery.dataEditor at project level
# verify: gcloud projects get-iam-policy $PROJECT --flatten="bindings[].members" \
#   --filter="bindings.members:sa-dbt@$PROJECT.iam.gserviceaccount.com"
```

---

## 7. Build and Push Container Image

No Docker Desktop required. All builds run inside Cloud Build on GCP - nothing runs on your laptop.

There are two Cloud Build config files in `cloudbuild/`:
- `build-push.yaml` - used here (Section 7). Builds the single pipeline image and pushes it to Artifact Registry. Does NOT deploy or touch Cloud Run Jobs.
- `deploy-prod.yaml` - used by the automated CI/CD trigger (handover.md Steps 4-5). Builds the image AND rolls it onto all existing Cloud Run Jobs. Used after the jobs are created. When running manually (no git trigger), `COMMIT_SHA` is empty so pass it explicitly: `--substitutions="_PROJECT=${PROJECT},COMMIT_SHA=latest"`.

You use `build-push.yaml` here because the Cloud Run Jobs do not exist yet - they are created in Section 8 using this image.

**One-time auth (allow gcloud to push to Artifact Registry):**
```bash
gcloud auth configure-docker asia-southeast2-docker.pkg.dev --project=$PROJECT
```

**Build image and push:**
```bash
gcloud builds submit . \
  --config=cloudbuild/build-push.yaml \
  --substitutions="_PROJECT=${PROJECT}" \
  --project=$PROJECT
```

This builds the root `Dockerfile` (contains both ingestion Python package and dbt) and pushes to:
```
asia-southeast2-docker.pkg.dev/${PROJECT}/tring-service/pipeline:latest
```

The image has no ENTRYPOINT. Each Cloud Run Job must set `--command` and `--args` explicitly (done in Section 8).

The command uploads your local code to Cloud Build and streams build logs. It takes 5-8 minutes. A `SUCCESS` at the end means the image is ready in Artifact Registry.

**Verify image is there:**
```bash
gcloud artifacts docker images list asia-southeast2-docker.pkg.dev/${PROJECT}/tring-service --project=$PROJECT
```

You should see one image path: `pipeline`.

---

## 8. Deploy Cloud Run Jobs

> **Note on date args:** dates are not set at job creation. Cloud Workflows injects them at runtime via `containerOverrides.env` (`DATE_FROM`/`DATE_TO`). For manual backfill, use `gcloud run jobs execute` with `--update-env-vars="DATE_FROM=...,DATE_TO=..."` (see runbook section 3).

> **IMPORTANT - no ENTRYPOINT in image:** The `pipeline` image has no ENTRYPOINT. Every job MUST set `--command` and `--args`. A job created without them will not know what to run and will fail at runtime, not at deploy time.

> **dbt profiles dir:** The `dbt-transform` job uses `DBT_PROFILES_DIR=/app/transform` env var instead of passing `--profiles-dir` in args. This is required because gcloud parses multiple `--*dir` flags inside `--args` incorrectly. Do not change this.

```bash
REGISTRY=asia-southeast2-docker.pkg.dev

# All 5 jobs use the same pipeline image. Each sets --command and --args for its workload.

# extract-appsflyer
gcloud run jobs create extract-appsflyer \
  --image=${REGISTRY}/${PROJECT}/tring-service/pipeline:latest \
  --region=asia-southeast2 \
  --service-account=sa-extract-appsflyer@${PROJECT}.iam.gserviceaccount.com \
  --set-env-vars="GCP_PROJECT=${PROJECT},BQ_DATASET_RAW=appsflyer_raw,REGION=asia-southeast2" \
  --set-secrets="APPSFLYER_API_TOKEN=appsflyer-api-token:latest" \
  --command=python \
  --args="-m,tring_ingest,--source,appsflyer" \
  --memory=4Gi \
  --cpu=2 \
  --project=$PROJECT

# extract-moengage
gcloud run jobs create extract-moengage \
  --image=${REGISTRY}/${PROJECT}/tring-service/pipeline:latest \
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

# extract-play-console
# PLAY_CONSOLE_SECRET_NAME tells config.py which Secret Manager secret to fetch the SA key JSON from.
gcloud run jobs create extract-play-console \
  --image=${REGISTRY}/${PROJECT}/tring-service/pipeline:latest \
  --region=asia-southeast2 \
  --service-account=sa-extract-play-console@${PROJECT}.iam.gserviceaccount.com \
  --set-env-vars="GCP_PROJECT=${PROJECT},BQ_DATASET_RAW_PLAY_CONSOLE=play_raw,REGION=asia-southeast2,PLAY_CONSOLE_SECRET_NAME=play-console-sa-key" \
  --command=python \
  --args="-m,tring_ingest,--source,play_console" \
  --memory=2Gi \
  --cpu=1 \
  --max-retries=0 \
  --project=$PROJECT

# extract-app-store
gcloud run jobs create extract-app-store \
  --image=${REGISTRY}/${PROJECT}/tring-service/pipeline:latest \
  --region=asia-southeast2 \
  --service-account=sa-extract-app-store@${PROJECT}.iam.gserviceaccount.com \
  --set-env-vars="GCP_PROJECT=${PROJECT},BQ_DATASET_RAW_APPSTORE=appstore_raw,REGION=asia-southeast2,APPSTORE_SECRET_NAME=appstore-connect-key,APPSTORE_APP_ID=1350501409" \
  --command=python \
  --args="-m,tring_ingest,--source,app_store" \
  --memory=2Gi \
  --cpu=1 \
  --max-retries=0 \
  --project=$PROJECT

# dbt-transform
# DBT_PROFILES_DIR env var tells dbt where profiles.yml is (avoids --profiles-dir in args).
gcloud run jobs create dbt-transform \
  --image=${REGISTRY}/${PROJECT}/tring-service/pipeline:latest \
  --region=asia-southeast2 \
  --service-account=sa-dbt@${PROJECT}.iam.gserviceaccount.com \
  --set-env-vars="GCP_PROJECT=${PROJECT},DBT_PROFILES_DIR=/app/transform" \
  --command=dbt \
  --args="build,--project-dir,/app/transform,--target,prod,--target-path,/tmp/dbt-target" \
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

**Rebuild image and update all jobs after code change:**
```bash
gcloud builds submit . \
  --config=cloudbuild/build-push.yaml \
  --substitutions="_PROJECT=${PROJECT}" \
  --project=$PROJECT

gcloud run jobs update extract-appsflyer \
  --image=${REGISTRY}/${PROJECT}/tring-service/pipeline:latest \
  --command=python \
  --args="-m,tring_ingest,--source,appsflyer" \
  --region=asia-southeast2 \
  --project=$PROJECT

gcloud run jobs update extract-moengage \
  --image=${REGISTRY}/${PROJECT}/tring-service/pipeline:latest \
  --command=python \
  --args="-m,tring_ingest,--source,moengage" \
  --region=asia-southeast2 \
  --project=$PROJECT

gcloud run jobs update extract-play-console \
  --image=${REGISTRY}/${PROJECT}/tring-service/pipeline:latest \
  --command=python \
  --args="-m,tring_ingest,--source,play_console" \
  --region=asia-southeast2 \
  --project=$PROJECT

gcloud run jobs update extract-app-store \
  --image=${REGISTRY}/${PROJECT}/tring-service/pipeline:latest \
  --command=python \
  --args="-m,tring_ingest,--source,app_store" \
  --region=asia-southeast2 \
  --project=$PROJECT

gcloud run jobs update dbt-transform \
  --image=${REGISTRY}/${PROJECT}/tring-service/pipeline:latest \
  --command=dbt \
  --args="build,--project-dir,/app/transform,--target,prod,--target-path,/tmp/dbt-target" \
  --update-env-vars=DBT_PROFILES_DIR=/app/transform \
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

Run once daily at 09:00 WIB (02:00 UTC). This timing ensures Play Console vitals data (3-day lag) is settled and AppsFlyer rate limit has reset (resets 00:00 UTC = 07:00 WIB).

```bash
gcloud scheduler jobs create http pipeline-trigger-daily \
  --location=asia-southeast2 \
  --schedule="0 2 * * *" \
  --time-zone="UTC" \
  --uri="https://workflowexecutions.googleapis.com/v1/projects/${PROJECT}/locations/asia-southeast2/workflows/pipeline/executions" \
  --message-body="{}" \
  --oauth-service-account-email=sa-scheduler@${PROJECT}.iam.gserviceaccount.com \
  --headers="Content-Type=application/json" \
  --project=$PROJECT
```

---

## 11. Run the Pipeline Once to Verify

Run the pipeline manually to confirm the full setup works end-to-end.

**Default run (pulls yesterday's data):**
```bash
gcloud workflows run pipeline --location=asia-southeast2 --project=$PROJECT
```

**Recommended for first run - use an explicit date range to verify with known data:**
```bash
gcloud workflows run pipeline \
  --data='{"date_from":"2026-06-01","date_to":"2026-06-15"}' \
  --location=asia-southeast2 --project=$PROJECT
```

A full run takes 6–10 minutes. Check the result:
```bash
gcloud workflows executions list pipeline --location=asia-southeast2 --project=$PROJECT --limit=5
```

`state: SUCCEEDED` means everything worked. `state: FAILED` - check logs:
```bash
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="extract-appsflyer"' \
  --project=$PROJECT --limit=30 --order=desc --format="table(timestamp,textPayload)"
```

Replace `extract-appsflyer` with `extract-moengage`, `extract-play-console`, or `dbt-transform` to check the other jobs.

---

## 12. Failure Alerting (recommended, not provisioned by default)

The pipeline does not notify anyone when a run fails out of the box. A `FAILED`
run is only visible if someone checks `gcloud workflows executions list` or the
Console. For production you almost always want an email on failure so a broken
pipeline does not go unnoticed for days.

This is optional and left out of the base provisioning on purpose (the initial
handover scope had no alerting). Set it up once per project when the client is
ready. Two commands, full walkthrough including Slack/PagerDuty variants, are in
`docs/runbook.md` section 10 ("Adding email alerting").

Quick version:

```bash
# 1. notification channel (use a team distribution list, not a personal inbox)
gcloud beta monitoring channels create \
  --display-name="Pipeline Alerts" \
  --type=email \
  --channel-labels=email_address=YOUR_TEAM_EMAIL@example.com \
  --project=$PROJECT

# 2. alert policy on FAILED workflow runs (paste the channel name from step 1)
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
| sa-extract-app-store | bigquery.dataEditor | project |
| sa-extract-app-store | bigquery.jobUser | project |
| sa-extract-app-store | secretmanager.secretAccessor | secret: appstore-connect-key only |
| sa-extract-app-store | secretmanager.secretAccessor | secret: appstore-connect-key-p8 only |
| sa-dbt | bigquery.dataEditor | project |
| sa-dbt | bigquery.jobUser | project |
| sa-workflows | run.invoker | project |
| sa-workflows | run.developer | project |
| sa-scheduler | workflows.invoker | project |

## Setup User Roles

See the role table at the top of this file (Before you start section). Check your roles in GCP Console > IAM & Admin > IAM before running any section.
