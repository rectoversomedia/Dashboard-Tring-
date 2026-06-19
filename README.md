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

Region: `asia-southeast2` (Jakarta). Environments: `dev` (hypefast-data-staging), `prod` (client GCP — deployed via GitLab + VPN).

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
| dev  | hypefast-data-staging | Consultant (dev + testing)              |
| prod | Client GCP project    | Client only — deployed via GitLab + VPN |

> **Prod deployment:** Code is pushed to the client's GitLab (VPN-gated). Cloud Build triggers on the client's GCP pick it up and deploy. No direct prod GCP access required from the consultant side.

## GCP Setup

See [docs/gcp-setup.md](docs/gcp-setup.md) for full provisioning steps: APIs, service accounts, IAM roles, secrets, Artifact Registry, and BigQuery datasets.

For client production onboarding (GitLab + VPN + Cloud Build setup), see [docs/handover.md](docs/handover.md).

## Adding a New Source

See `docs/runbook.md` section "Adding a source".

## Secrets

All secrets live in Secret Manager. Never commit secret values. Add values out of band:

```bash
echo -n "YOUR_TOKEN" | gcloud secrets versions add appsflyer-api-token --data-file=- --project=YOUR_PROJECT
```
