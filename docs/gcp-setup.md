# GCP Setup Guide

One-time provisioning steps for each GCP project (dev or prod). Run as a user with sufficient IAM permissions (see Setup User Roles at the bottom).

Set project once:
```bash
export PROJECT=hypefast-data-staging   # or dashboard-tring-prod
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

> **Adding a new source (MoEngage, Play Console, App Store Connect):** create a dedicated SA per source — `sa-extract-moengage`, `sa-extract-playstore`, etc. Grant only the roles that source needs. Never reuse an existing extractor SA for a different source.

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
Triggers Cloud Run Jobs from Cloud Workflows.

```bash
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:sa-workflows@${PROJECT}.iam.gserviceaccount.com" --role="roles/run.invoker"
```

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

Datasets are also auto-created by the ingestion code on first run (safe to skip).

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
