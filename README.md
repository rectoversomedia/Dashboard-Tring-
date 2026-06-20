# Dashboard Monitoring & AI Insight — Data Pipeline

Data pipeline for multi-source mobile app analytics. Sources: AppsFlyer, MoEngage, Google Play Console, App Store Connect. Target: BigQuery + Looker Studio.

## Architecture

```
  -> Cloud Workflows
      -> [parallel] Cloud Run Jobs (extract per source)
      -> Cloud Run Job (dbt transform)
  -> BigQuery (raw -> staging -> mart)
  -> Looker Studio (mart layer)
```

Region: `asia-southeast2` (Jakarta). Environments: `dev` (consultant GCP project), `prod` (client GCP — deployed via GitLab + VPN).

## Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- [dbt-core](https://docs.getdbt.com/) with `dbt-bigquery`
- Terraform >= 1.5
- `gcloud` CLI authenticated to the target project

> **Docker Desktop not required.** Container images are built and pushed via Cloud Build (GCP-native). No local Docker needed in dev or prod.

## Quick Start

```bash
# Install dependencies
make setup

# Lint
make lint

# Run tests
make test

# Deploy everything to dev
make deploy ENV=dev
```

## Repository Layout

```
tring-data-pipeline/
  cloudbuild/       Cloud Build CI/CD configs
  ingestion/        Python extractor (shared image, one job per source)
  transform/        dbt project (staging + mart models)
  orchestration/    Cloud Workflows definition
  infra/            Terraform (modules + per-env wiring)
  docs/             Runbook and reference
```

## Environments

| Env  | GCP Project           | Access                                  |
|------|-----------------------|-----------------------------------------|
| dev  | Consultant GCP project (set via `GCP_PROJECT`) | Consultant (dev + testing) |
| prod | Client GCP project    | Client only — deployed via GitLab + VPN |

> **Prod deployment:** Code is pushed to the client's GitLab (VPN-gated). Cloud Build triggers on the client's GCP pick it up and deploy. No direct prod GCP access required from the consultant side.

## GCP Setup

See [docs/gcp-setup.md](docs/gcp-setup.md) for full provisioning steps: APIs, service accounts, IAM roles, secrets, Artifact Registry, BigQuery datasets, and Cloud Run Job creation.

For client production onboarding (GitLab + VPN + Cloud Build setup), see [docs/handover.md](docs/handover.md).

## Running the Pipeline

**Scheduled:** Cloud Scheduler triggers Cloud Workflows twice daily (08:00 and 20:00 WIB). No manual action needed.

**Manual run (yesterday):**
```bash
gcloud workflows run pipeline --location=asia-southeast2 --project=YOUR_PROJECT
```

**Manual run (specific date range / backfill):**
```bash
gcloud workflows run pipeline \
  --data='{"date_from":"2026-06-01","date_to":"2026-06-10"}' \
  --location=asia-southeast2 \
  --project=YOUR_PROJECT
```

**Date handling:** Workflow auto-computes yesterday when no dates are passed. Pass `date_from`/`date_to` in `--data` to override for backfill.

See [docs/runbook.md](docs/runbook.md) for full ops procedures: manual triggers, backfill, log reading, token rotation, and alerts.

## Data Catalog

See [docs/data-catalog-appsflyer.md](docs/data-catalog-appsflyer.md) for full AppsFlyer endpoint reference: table schemas, column definitions, row volume estimates, and known issues.

## Adding a New Source

See `docs/runbook.md` section "Adding a source".

## Secrets

All secrets live in Secret Manager. Never commit secret values. Add values out of band:

```bash
echo -n "YOUR_TOKEN" | gcloud secrets versions add appsflyer-api-token --data-file=- --project=YOUR_PROJECT
```
