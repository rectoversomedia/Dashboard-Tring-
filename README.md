# Dashboard Monitoring & AI Insight  -  Data Pipeline

Data pipeline for multi-source mobile app analytics. Live sources: AppsFlyer, MoEngage, Google Play Console. App Store Connect is scaffolded for the future but not in scope yet. Target: BigQuery + Looker Studio.

## Architecture

```
  -> Cloud Workflows
      -> [parallel] Cloud Run Job (extract-appsflyer     -  8 pulls: 4 endpoints x 2 platforms)
      -> [parallel] Cloud Run Job (extract-moengage      -  2 endpoints: campaign search + stats)
      -> [parallel] Cloud Run Job (extract-play-console  -  6 metric sets + reviews)
      -> Cloud Run Job (dbt transform)   (runs after all three extracts succeed)
  -> BigQuery (raw -> staging/mart)
  -> Looker Studio (mart tables)
```

**Sources status:**

| Source | Extract code | Tests | dbt models | GCP infra | E2E |
|---|---|---|---|---|---|
| AppsFlyer | DONE | 12/12 | DONE | DONE | DONE |
| MoEngage | DONE | 12/12 | DONE | DONE | DONE |
| Play Console | DONE | 16/16 | DONE (7 staging + 2 mart) | DONE | DONE |
| App Store Connect | scaffold only (future, not in scope) | - | - | - | - |

Region: `asia-southeast2` (Jakarta). Environments: `dev` (consultant GCP project), `prod` (client GCP  -  deployed via GitLab + VPN).

## Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/)  -  for local ingestion development (`uv sync` in `ingestion/`)
- [dbt-core](https://docs.getdbt.com/) with `dbt-bigquery`  -  for local transform runs (`cd transform && dbt run`)
- Terraform >= 1.5  -  optional, only if adopting IaC (see note below)
- `gcloud` CLI authenticated to the target project

> **Docker Desktop not required.** Container images are built and pushed via Cloud Build (GCP-native). No local Docker needed in dev or prod.

> **Terraform not required.** `infra/` contains Terraform modules as IaC reference for the client, but all provisioning is done via `gcloud` commands (see `docs/gcp-setup.md`). Terraform is skipped because prod runs on client GitLab + VPN where Terraform state backend (GCS) adds unnecessary complexity. Client can adopt Terraform later without changing anything else.

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
  infra/            Terraform (optional  -  modules + per-env wiring, not used in current deploy)
  docs/             Runbook and reference
```

## Environments

| Env  | GCP Project           | Access                                  |
|------|-----------------------|-----------------------------------------|
| dev  | Consultant GCP project (set via `GCP_PROJECT`) | Consultant (dev + testing) |
| prod | Client GCP project    | Client only  -  deployed via GitLab + VPN |

> **Prod deployment:** Code is pushed to the client's GitLab (VPN-gated). Cloud Build triggers on the client's GCP pick it up and deploy. No direct prod GCP access required from the consultant side.

## Documentation

New to this project? Start with **[docs/index.md](docs/index.md)** - it lists every document, the order to read them in, and a glossary of all the terms (Cloud Run Job, dbt, WIB, T-1, backfill, etc.).

## GCP Setup

See [docs/gcp-setup.md](docs/gcp-setup.md) for full provisioning steps: APIs, service accounts, IAM roles, secrets, Artifact Registry, BigQuery datasets, and Cloud Run Job creation.

For client production onboarding (GitLab + VPN + Cloud Build setup), see [docs/handover.md](docs/handover.md).

## Running the Pipeline

**Scheduled:** Cloud Scheduler triggers Cloud Workflows twice daily (08:00 and 20:00 WIB). No manual action needed.

> **Note:** The 08:00 and 20:00 WIB schedule is a default assumption based on the TSD (twice daily to catch late-arriving data). The client has not confirmed a final schedule yet. To change it: `gcloud scheduler jobs update http pipeline-trigger-morning --schedule="0 HH * * *" --location=asia-southeast2 --project=PROJECT` (and same for `pipeline-trigger-afternoon`).

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

See [docs/runbook.md](docs/runbook.md) for full ops procedures: manual triggers, backfill, log reading, token rotation, and checking for failures.

## Data Catalog

- **AppsFlyer:** [docs/data-catalog-appsflyer.md](docs/data-catalog-appsflyer.md) - endpoint reference, table schemas, column definitions, row volumes, known issues.
- **MoEngage:** [docs/data-catalog-moengage.md](docs/data-catalog-moengage.md) - endpoint reference, column definitions, API limits (limit=15, max 10 IDs/request, 30d window), known metric behaviors (CTR scale, ALL_PLATFORMS, impression as open proxy).
- **Play Console:** [docs/data-catalog-play-console.md](docs/data-catalog-play-console.md) - metric sets, review fields, API endpoints, dbt models (7 staging + 2 mart), GCP infra and the two-project SA key setup.

## Adding a New Source

See `docs/runbook.md` section "Adding a source".

## Secrets

All secrets live in Secret Manager. Never commit secret values. Add values out of band:

```bash
echo -n "YOUR_TOKEN" | gcloud secrets versions add appsflyer-api-token --data-file=- --project=YOUR_PROJECT
```
