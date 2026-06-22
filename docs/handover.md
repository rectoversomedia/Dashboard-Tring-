# Handover Guide  -  Client Production Setup

This guide is for the client's GCP/DevOps admin. It covers the one-time setup needed to run the pipeline autonomously in the client's GCP environment. After setup, all deployments are automatic via Cloud Build on every git push.

**No Docker Desktop required.** All container builds run inside Cloud Build (GCP-native).

---

## Overview

| What | Who does it | When |
|---|---|---|
| GCP provisioning (APIs, SA, IAM, secrets) | Client GCP admin | Once |
| Cloud Build trigger setup (GitLab → GCP) | Client GCP admin | Once |
| Push secrets (API tokens) | Client admin (not consultant) | Once, then on rotation |
| Failure alerting (email on FAILED run) | Client GCP admin | Once, optional but recommended (Step 7) |
| Git push to GitLab | Consultant / automated | Every code change |
| Build, push images, deploy Cloud Run Jobs | Cloud Build (automatic) | Every push to `main` |
| Pipeline run (extract + transform) | Cloud Scheduler (automatic) | Twice daily |

---

## Step 1: GCP Provisioning

Run all commands from `docs/gcp-setup.md` against the client's GCP project:

```bash
export PROJECT=YOUR_CLIENT_GCP_PROJECT_ID
```

Then run sections 1–10 of `docs/gcp-setup.md` in order:
1. Enable APIs
2. Create service accounts (sa-extract-appsflyer, sa-extract-moengage, sa-extract-play-console, sa-dbt, sa-workflows, sa-scheduler)
3. Grant IAM roles
4. Create secrets (AppsFlyer token + MoEngage credentials + Play Console SA key  -  see note below)
5. Create Artifact Registry repository
6. Create BigQuery datasets (9 total: appsflyer, moengage, and play_console, each raw/staging/mart)
7. Build and push container images
8. Create Cloud Run Jobs (extract-appsflyer, extract-moengage, extract-play-console, dbt-transform)
9. Deploy Cloud Workflows (pipeline)
10. Create Cloud Scheduler jobs (twice-daily trigger)

> Steps 7-10 create the runtime resources (jobs, workflow, scheduler) once. After this, Cloud Build (Steps 2-5 below) only rolls new images onto the existing jobs on each git push  -  it does not re-create them.

> **Secret note:** The consultant never needs to see the production secrets. The client's admin retrieves them directly from each vendor and adds them to Secret Manager themselves:
> - **AppsFlyer:** token from the AppsFlyer dashboard (Configuration > API Token v3) into secret `appsflyer-api-token`.
> - **MoEngage:** workspace ID + API key from the MoEngage dashboard (Settings > APIs) into secret `moengage-api-creds`, formatted as `WORKSPACE_ID:API_KEY` (colon-delimited, no spaces).
> - **Play Console:** SA key JSON from the client's production GCP project (`pgd-prd-digital-rating-tring`), SA `dashboard-monitoring-aiinsight`. This SA already has Play Console access - no Play Console UI setup needed. Store in secret `play-console-sa-key`. Delete the local key file after adding to Secret Manager.

---

## Step 2: Grant Cloud Build Service Account Permissions

Cloud Build runs automatically using a service account that GCP creates for you. You need to give it permission to deploy to Cloud Run and push images.

**First, find your Cloud Build service account email:**

```bash
PROJECT_NUMBER=$(gcloud projects describe $PROJECT --format="value(projectNumber)")
CB_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

# Print it to confirm before running the next block
echo $CB_SA
```

You should see something like: `123456789@cloudbuild.gserviceaccount.com`

**Grant deploy permissions:**

```bash
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:${CB_SA}" --role="roles/run.developer"
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:${CB_SA}" --role="roles/artifactregistry.writer"
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:${CB_SA}" --role="roles/iam.serviceAccountUser"
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:${CB_SA}" --role="roles/bigquery.user"
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:${CB_SA}" --role="roles/bigquery.dataEditor"
```

Each command should print `Updated IAM policy for project [...]`. If you see an error about permissions, make sure your account has `roles/resourcemanager.projectIamAdmin` on the project.

---

## Step 3: Connect GitLab to Cloud Build

This step links your GitLab repository to GCP so that Cloud Build can read the code and trigger builds automatically.

> **VPN note:** If your GitLab is on a company network (self-hosted / on-premise), you need to be connected to the VPN before doing this step. Cloud Build needs to reach GitLab from the internet.

**Option A: GCP Console (recommended for first time)**

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and make sure the correct project is selected (top bar, next to "Google Cloud" logo).
2. In the left sidebar, search for **Cloud Build** and click it.
3. Click **Triggers** in the left menu.
4. Click **Connect Repository** (blue button, top right).
5. Under "Select source", choose **GitLab**.
6. Click **Continue**.
7. If prompted, authenticate with your GitLab account (username + password, or SSO if your company uses it).
8. Select the repository that contains this pipeline code.
9. Check the box to confirm you understand Cloud Build will read the repo.
10. Click **Connect**.

You should see the repo listed under "Connected repositories". If connection fails, check:
- VPN is active (if GitLab is self-hosted)
- Your GitLab account has at least Reporter access to the repo

**Option B: gcloud CLI**

If your GitLab is public or already authenticated:

```bash
# Replace GITLAB_HOST with your GitLab domain, e.g. gitlab.com or gitlab.yourcompany.com
gcloud builds connections create gitlab tring-gitlab-connection \
  --host-uri="https://GITLAB_HOST" \
  --project=$PROJECT \
  --region=asia-southeast2
```

Then link the specific repo:

```bash
# Replace GITLAB_HOST and GITLAB_REPO_PATH (e.g. myorg/tring-data-pipeline)
gcloud builds repositories create tring-pipeline-repo \
  --connection=tring-gitlab-connection \
  --remote-uri="https://GITLAB_HOST/GITLAB_REPO_PATH.git" \
  --project=$PROJECT \
  --region=asia-southeast2
```

---

## Step 4: Create Cloud Build Trigger

The trigger tells Cloud Build: "every time someone pushes code to the `main` branch, run the deploy script automatically."

> **One GCP project (prod only)?** Create only the trigger below (`deploy-prod-on-push`). The repo also contains `cloudbuild/deploy-dev.yaml` for teams with a separate dev project - you can ignore it. One project = one trigger = one `main` branch = done.

> **Two GCP projects (dev + prod)?** Create two triggers: one pointing `cloudbuild/deploy-dev.yaml` on a `dev` branch (with `_PROJECT` = your dev project ID), and one pointing `cloudbuild/deploy-prod.yaml` on `main` (with `_PROJECT` = your prod project ID). Each project needs its own GCP provisioning (Step 1) and its own service accounts.

**Via GCP Console (recommended):**

1. In Cloud Build, click **Triggers** in the left menu.
2. Click **Create Trigger**.
3. Fill in:
   - **Name:** `deploy-prod-on-push`
   - **Region:** `asia-southeast2`
   - **Event:** Push to a branch
   - **Source (1st gen):** Select the repository you connected in Step 3
   - **Branch:** `^main$` (exactly this, including the `^` and `$`)
   - **Configuration:** Cloud Build configuration file (yaml or json)
   - **Cloud Build configuration file location:** `cloudbuild/deploy-prod.yaml`
4. Scroll down to **Substitution variables**. Click **Add variable** and add:
   - Variable: `_PROJECT`
   - Value: your GCP project ID (same as `$PROJECT`)
5. Click **Save**.

**Via gcloud CLI (alternative):**

```bash
gcloud builds triggers create gitlab \
  --name="deploy-prod-on-push" \
  --region=asia-southeast2 \
  --repository="projects/${PROJECT}/locations/asia-southeast2/connections/tring-gitlab-connection/repositories/tring-pipeline-repo" \
  --branch-pattern="^main$" \
  --build-config="cloudbuild/deploy-prod.yaml" \
  --substitutions="_PROJECT=${PROJECT}" \
  --project=$PROJECT
```

> Replace `tring-gitlab-connection` and `tring-pipeline-repo` with the names you used in Step 3 if different.

**Verify the trigger was created:**

```bash
gcloud builds triggers list --project=$PROJECT --region=asia-southeast2
```

You should see `deploy-prod-on-push` in the list with `STATUS: ENABLED`.

---

## Step 5: First Deployment

Run the first build manually to confirm everything works before relying on automatic triggers.

```bash
gcloud builds submit . \
  --config=cloudbuild/deploy-prod.yaml \
  --substitutions="_PROJECT=${PROJECT}" \
  --project=$PROJECT
```

This command uploads the code to Cloud Build and runs the deploy script. It will:
1. Build the ingestion container image and push it to Artifact Registry
2. Build the dbt container image and push it to Artifact Registry
3. Update the existing Cloud Run Jobs (`extract-appsflyer`, `extract-moengage`, `extract-play-console`, and `dbt-transform`) to use the new images

> **Prerequisite:** this build runs `gcloud run jobs update`, which only works on jobs that already exist. The jobs are created once in `gcp-setup.md` section 8 (or via `make create-appsflyer create-moengage create-play-console create-dbt`). If you run this build before creating the jobs, it fails with `NOT_FOUND`; go back and create them first.

**Watch the build progress:**

The command will print a build URL, for example:
```
https://console.cloud.google.com/cloud-build/builds/abc123?project=YOUR_PROJECT
```

Open that URL in your browser to see live logs. The build takes about 3-5 minutes.

**Expected result:** Build status `SUCCESS`. If it shows `FAILURE`, check the logs at that URL - the error message will say exactly which step failed.

> **What Cloud Build does NOT do:** It does not create or delete any GCP resources (datasets, jobs, scheduler, etc.). Those were already created in Step 1. Cloud Build only updates the container images on the existing jobs.

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

Expected: `state: SUCCEEDED`. Extract jobs run in parallel (extract-appsflyer, extract-moengage, extract-play-console). After all three complete, dbt-transform runs. See `docs/runbook.md` section 2 for how to verify each stage.

---

## Step 7: Set Up Failure Alerting (recommended)

This step is optional but strongly recommended for production. Without it, a
failed run is silent - nobody is told, and a broken pipeline can go unnoticed
for days until someone checks manually or notices stale dashboards.

Set up an email alert that fires whenever a pipeline run ends in `FAILED`. It
takes about 10 minutes, once per project. The two `gcloud` commands (create a
notification channel, then an alert policy) are in `docs/runbook.md` section 10
("Adding email alerting"), with Slack and PagerDuty variants. `docs/gcp-setup.md`
section 11 has the same commands in the provisioning context.

Use a team distribution list as the alert email, not a personal inbox, so the
alert survives staff changes. After setup, confirm it works by waiting for the
next real failure or by deliberately failing a run.

---

## What's Automatic After Setup

| Event | What happens automatically |
|---|---|
| Push to `main` on GitLab | Cloud Build trigger fires → build images → roll new images onto Cloud Run Jobs |
| Cloud Scheduler (twice daily, 08:00 and 20:00 WIB) | Triggers Cloud Workflows → runs extract-appsflyer (8 pulls), extract-moengage, and extract-play-console in parallel → runs dbt |
| Extractor failure | Workflow polling detects non-success, marks the execution `FAILED` (dbt does NOT run) |
| dbt test failure | Job exits non-zero → Workflow marks the execution `FAILED` |

> **Schedule assumption:** The 08:00 and 20:00 WIB schedule is a default based on the TSD (twice daily to catch late-arriving data). The client has not confirmed a final schedule. To change: `gcloud scheduler jobs update http pipeline-trigger-morning --schedule="0 H * * *" --location=asia-southeast2 --project=PROJECT` (and same for `pipeline-trigger-afternoon`). See runbook.md for more.

> **Alerting is not provisioned by default.** Failures surface as a `FAILED` Workflow execution, visible via `gcloud workflows executions list` or the Console - but nobody is notified automatically until you set it up. For production you almost certainly want email alerting so a failed run does not go unnoticed for days. Runbook.md section 10 has two ready-to-run `gcloud` commands (create a notification channel, then an alert policy on the `workflows.googleapis.com/finished_execution_count` metric filtered to `status=FAILED`). Allow about 10 minutes to set up.

---

## Ongoing Operations

See `docs/runbook.md` for:
- Manual pipeline trigger
- Backfilling historical data
- Rotating API tokens
- Checking for failures and adding email alerting (section 10)
- Adding a new source

---

## What the Consultant Hands Over

| Artifact | Location |
|---|---|
| All pipeline code | GitLab repo (this repo) |
| GCP provisioning guide | `docs/gcp-setup.md` (authoritative deploy method  -  gcloud) |
| This handover guide | `docs/handover.md` |
| Operations runbook | `docs/runbook.md` |
| Data catalog (AppsFlyer) | `docs/data-catalog-appsflyer.md` |
| Data catalog (MoEngage) | `docs/data-catalog-moengage.md` |
| Data catalog (Play Console) | `docs/data-catalog-play-console.md` |
| CI/CD config | `cloudbuild/` |
| Infrastructure as code (reference only) | `infra/` (Terraform  -  not used in deploy; gcloud is authoritative) |

After handover, the client's team can operate the pipeline independently using the runbook. No consultant access to prod GCP is required or expected.
