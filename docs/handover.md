# Handover Guide — Client Production Setup

This guide is for the client's GCP/DevOps admin. It covers the one-time setup needed to run the pipeline autonomously in the client's GCP environment. After setup, all deployments are automatic via Cloud Build on every git push.

**No Docker Desktop required.** All container builds run inside Cloud Build (GCP-native).

---

## Overview

| What | Who does it | When |
|---|---|---|
| GCP provisioning (APIs, SA, IAM, secrets) | Client GCP admin | Once |
| Cloud Build trigger setup (GitLab → GCP) | Client GCP admin | Once |
| Push secrets (API tokens) | Client admin (not consultant) | Once, then on rotation |
| Git push to GitLab | Consultant / automated | Every code change |
| Build, push images, deploy Cloud Run Jobs | Cloud Build (automatic) | Every push to `main` |
| Pipeline run (extract + transform) | Cloud Scheduler (automatic) | Twice daily |

---

## Step 1: GCP Provisioning

Run all commands from `docs/gcp-setup.md` against the client's GCP project:

```bash
export PROJECT=YOUR_CLIENT_GCP_PROJECT_ID
```

Then run sections 1–6 of `docs/gcp-setup.md` in order:
1. Enable APIs
2. Create service accounts
3. Grant IAM roles
4. Create secrets (AppsFlyer token — see note below)
5. Create Artifact Registry repository
6. Create BigQuery datasets

> **Secret note:** The consultant never needs to see the production AppsFlyer token. The client's admin retrieves the token directly from the AppsFlyer dashboard (Configuration > API Token v3) and adds it to Secret Manager themselves.

---

## Step 2: Grant Cloud Build Service Account Permissions

Cloud Build runs as the default Cloud Build service account. Grant it deploy permissions:

```bash
PROJECT_NUMBER=$(gcloud projects describe $PROJECT --format="value(projectNumber)")
CB_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:${CB_SA}" --role="roles/run.developer"
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:${CB_SA}" --role="roles/artifactregistry.writer"
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:${CB_SA}" --role="roles/iam.serviceAccountUser"
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:${CB_SA}" --role="roles/bigquery.user"
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:${CB_SA}" --role="roles/bigquery.dataEditor"
```

---

## Step 3: Connect GitLab to Cloud Build

1. In GCP Console → **Cloud Build** → **Triggers** → **Connect Repository**
2. Choose **GitLab** as source provider
3. Authenticate with the client's GitLab account (VPN may be required)
4. Select the repository containing this pipeline code

> If the GitLab instance is self-hosted (on-premise/VPN), use **Cloud Build Private Pools** or set up a **GitLab webhook** pointing to a Cloud Build trigger URL instead of the native connector.

---

## Step 4: Create Cloud Build Trigger

Create a trigger for the `main` branch using the prod config:

```bash
gcloud builds triggers create gitlab \
  --name="deploy-prod-on-push" \
  --branch-pattern="^main$" \
  --build-config="cloudbuild/deploy-prod.yaml" \
  --substitutions="_PROJECT=${PROJECT}" \
  --project=$PROJECT
```

Or via GCP Console:
- **Event:** Push to branch `main`
- **Config:** `cloudbuild/deploy-prod.yaml`
- **Substitutions:** `_PROJECT` = `YOUR_CLIENT_GCP_PROJECT_ID`

---

## Step 5: First Deployment

Trigger the first build manually to verify everything works:

```bash
gcloud builds submit --config=cloudbuild/deploy-prod.yaml \
  --substitutions="_PROJECT=${PROJECT}" \
  --project=$PROJECT
```

This will:
1. Build ingestion image and push to Artifact Registry
2. Build dbt image and push to Artifact Registry
3. Apply Terraform (Cloud Run Jobs, Workflows, Scheduler)
4. Deploy updated images to Cloud Run Jobs

---

## Step 6: Verify Pipeline Runs

After deploy, trigger a manual pipeline run to confirm end-to-end:

```bash
gcloud workflows run pipeline \
  --location=asia-southeast2 \
  --project=$PROJECT
```

Watch status:
```bash
gcloud workflows executions list pipeline \
  --location=asia-southeast2 \
  --project=$PROJECT \
  --limit=5
```

Expected: all 4 extract jobs succeed, then dbt-transform succeeds.

---

## What's Automatic After Setup

| Event | What happens automatically |
|---|---|
| Push to `main` on GitLab | Cloud Build trigger fires → build images → deploy Cloud Run Jobs |
| Cloud Scheduler (twice daily) | Triggers Cloud Workflows → runs 4 extractors in parallel → runs dbt |
| Extractor failure | Cloud Workflows retries, then marks step failed → Cloud Monitoring alert fires |
| dbt test failure | Job exits non-zero → Workflows marks failed → alert fires |

---

## Ongoing Operations

See `docs/runbook.md` for:
- Manual pipeline trigger
- Backfilling historical data
- Rotating API tokens
- Reading alerts
- Adding a new source

---

## What the Consultant Hands Over

| Artifact | Location |
|---|---|
| All pipeline code | GitLab repo (this repo) |
| GCP provisioning guide | `docs/gcp-setup.md` |
| This handover guide | `docs/handover.md` |
| Operations runbook | `docs/runbook.md` |
| Infrastructure as code | `infra/` (Terraform) |
| CI/CD config | `cloudbuild/` |
| Architecture spec | `tsd_tring_architecture.md` |

After handover, the client's team can operate the pipeline independently using the runbook. No consultant access to prod GCP is required or expected.
