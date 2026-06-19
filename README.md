# Tring! Data Pipeline

Data pipeline for Tring! by Pegadaian. Sources: AppsFlyer, MoEngage, Google Play Console, App Store Connect. Target: BigQuery + Looker Studio.

## Architecture

```
  -> Cloud Workflows
      -> [parallel] Cloud Run Jobs (extract per source)
      -> Cloud Run Job (dbt transform)
  -> BigQuery (raw -> staging -> mart)
  -> Looker Studio (mart layer)
```

Region: `asia-southeast2` (Jakarta). Environments: `dev` (`dashboard-tring-dev`), `prod` (`dashboard-tring-prod`).

## Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- [dbt-core](https://docs.getdbt.com/) with `dbt-bigquery`
- Docker
- Terraform >= 1.5
- `gcloud` CLI authenticated to the target project

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

| Env  | GCP Project          |
|------|----------------------|
| dev  | dashboard-tring-dev  |
| prod | dashboard-tring-prod |

## GCP Setup

See [docs/gcp-setup.md](docs/gcp-setup.md) for full provisioning steps: APIs, service accounts, IAM roles, secrets, Artifact Registry, and BigQuery datasets.

## Adding a New Source

See `docs/runbook.md` section "Adding a source".

## Secrets

All secrets live in Secret Manager. Never commit secret values. Add values out of band:

```bash
echo -n "YOUR_TOKEN" | gcloud secrets versions add appsflyer-api-token --data-file=- --project=dashboard-tring-dev
```
