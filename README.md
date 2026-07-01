# Dashboard Monitoring & AI Insight - Data Pipeline

Multi-source mobile app analytics into BigQuery for Looker Studio.
Live sources: AppsFlyer, MoEngage, Google Play Console, App Store Connect.

> **New here?** Read **[docs/index.md](docs/index.md)** first - reading order and
> a glossary of every term. Short path: `index.md` -> `gcp-setup.md` ->
> `handover.md` -> `runbook.md`.

## Architecture

```
Cloud Scheduler (2x daily)
  -> Cloud Workflows
       -> [parallel] extract-appsflyer      (4 endpoints x 2 platforms = 8 pulls)
       -> [parallel] extract-moengage       (campaign search + stats)
       -> [parallel] extract-play-console   (6 metric sets + reviews)
       -> [parallel] extract-app-store      (5 analytics reports + reviews)
       -> dbt transform   (after all extracts succeed)
  -> BigQuery (raw -> staging -> mart)
  -> Looker Studio
```

| Source | Extract | Tests | dbt | GCP | E2E |
|---|---|---|---|---|---|
| AppsFlyer | DONE | 12/12 | DONE | DONE | DONE |
| MoEngage | DONE | 12/12 | DONE | DONE | DONE |
| Play Console | DONE | 16/16 | DONE | DONE | DONE |
| App Store Connect | DONE | 11/11 | DONE | DONE | DONE |

Region: `asia-southeast2` (Jakarta). Envs: `dev` (consultant GCP), `prod`
(client GCP, deployed via GitLab + VPN).

## Layout

```
tring-data-pipeline/
  ingestion/      Python extractor + Dockerfile (one shared image, one job per source)
  transform/      dbt project + Dockerfile (staging + mart models)
  orchestration/  Cloud Workflows definition
  cloudbuild/     Cloud Build CI/CD configs
  infra/          Terraform modules (reference only, not the deploy path)
  docs/           Setup, handover, runbook, data catalogs
```

> **Single image** - one root `Dockerfile` packages both ingestion (Python) and dbt into a single `pipeline` image. One root `Dockerfile` packages both ingestion and dbt. Default `CMD` runs a minimal HTTP server so Cloud Run Service health checks pass (Jenkins CI/CD uses `gcloud run deploy`). Cloud Run Jobs override this with `--command`/`--args` for their actual workload. Cloud Build (`cloudbuild/build-push.yaml`) builds it. No local Docker needed.

## Prerequisites

- Python 3.12, [uv](https://docs.astral.sh/uv/) (local ingestion: `uv sync` in `ingestion/`)
- [dbt-core](https://docs.getdbt.com/) + `dbt-bigquery` (local transform: `cd transform && dbt run`)
- `gcloud` CLI authenticated to the target project
- Terraform >= 1.5 - optional, only if adopting IaC (provisioning is done via `gcloud`, see `docs/gcp-setup.md`)

## Quick Start

```bash
make setup     # install deps
make lint
make test
make deploy ENV=dev
```

## Running the Pipeline

Scheduled: Cloud Scheduler triggers the workflow twice daily (08:00 and 20:00
WIB - a default assumption from the TSD, client has not confirmed). No manual
action needed.

```bash
# manual run (default window: T-4 to T-3)
gcloud workflows run pipeline --location=asia-southeast2 --project=YOUR_PROJECT

# backfill a date range
gcloud workflows run pipeline \
  --data='{"date_from":"2026-06-01","date_to":"2026-06-10"}' \
  --location=asia-southeast2 --project=YOUR_PROJECT
```

The workflow auto-computes **T-4 to T-3** (3 days back) when no dates are passed. Play Console vitals API has a 3-day data lag -- requesting T-3 or newer returns HTTP 400. See `docs/runbook.md` for backfill, log reading, token rotation, and schedule changes.

## Branch Strategy

Two long-lived branches:

| Branch | Deploys to | Purpose |
|---|---|---|
| `develop` | Dev GCP project | Feature development + integration testing |
| `main` | Prod GCP project (client) | Live production pipeline |

**Why two branches?** Isolates work-in-progress from production. Changes are tested in the dev environment before reaching the client. Prevents untested code from breaking the live pipeline.

**Flow:** `feature/*` → PR → `develop` (auto-deploy to dev, verify E2E) → PR → `main` (auto-deploy to prod).

See `docs/contributing.md` for full workflow, commit format, and local checks.

---

## Documentation

| Doc | What |
|---|---|
| [docs/index.md](docs/index.md) | Start here - reading order + glossary |
| [docs/contributing.md](docs/contributing.md) | Branch strategy, PR flow, commit format, local checks |
| [docs/gcp-setup.md](docs/gcp-setup.md) | Provisioning: APIs, SAs, IAM, secrets, datasets, jobs |
| [docs/handover.md](docs/handover.md) | Client prod onboarding (GitLab + VPN + Cloud Build) |
| [docs/runbook.md](docs/runbook.md) | Ops: triggers, backfill, rotation, failures, adding a source |
| [docs/adding-endpoints.md](docs/adding-endpoints.md) | Add an endpoint to an existing source |
| [docs/testing.md](docs/testing.md) | Local + CI verification |
| Data catalogs | Per-source reference: [appsflyer](docs/data-catalog-appsflyer.md), [moengage](docs/data-catalog-moengage.md), [play-console](docs/data-catalog-play-console.md), [app-store](docs/data-catalog-appstore.md) |

## Secrets

All secrets live in Secret Manager. Never commit secret values. Add out of band:

```bash
echo -n "YOUR_TOKEN" | gcloud secrets versions add appsflyer-api-token --data-file=- --project=YOUR_PROJECT
```
