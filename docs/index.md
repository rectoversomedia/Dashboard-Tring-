# Documentation Index

Start here. This page tells you which document to read, in what order, and explains the words used across all the docs.

If you are new to this project, read in this order:

1. **This page** - learn the vocabulary and the big picture (5 minutes).
2. **[gcp-setup.md](gcp-setup.md)** - how the GCP infrastructure is created, one command at a time. Read this even if someone else already ran it, so you understand what exists.
3. **[handover.md](handover.md)** - how to connect the code repository to GCP so deployments happen automatically. This is the production onboarding guide.
4. **[runbook.md](runbook.md)** - day-to-day operations: how to run the pipeline manually, check if it worked, backfill old data, rotate the API token.
5. **[testing.md](testing.md)** - how to test code changes before they reach GCP.
6. **[data-catalog-appsflyer.md](data-catalog-appsflyer.md)** - reference for the AppsFlyer data: tables, columns, row counts, rate limits. Look things up here when you need detail; you do not need to read it top to bottom.
7. **[data-catalog-moengage.md](data-catalog-moengage.md)** - reference for the MoEngage data: endpoints, columns, chunking limits, known metric behaviors (CTR scale, ALL_PLATFORMS, impression as open proxy). Look things up here when you need detail.
8. **[data-catalog-play-console.md](data-catalog-play-console.md)** - reference for the Play Console data: metric sets, review fields, API endpoints, GCP infra setup. Look things up here when you need detail.

---

## The big picture in one paragraph

Twice a day, a timer (Cloud Scheduler) starts an orchestrator (Cloud Workflows). The orchestrator runs two extract jobs **in parallel**: one downloads data from the AppsFlyer API and one from MoEngage. Both save raw data into BigQuery. Once both complete, a **transform** job (dbt) cleans and reshapes that raw data into analytics-ready tables. Those final tables feed a Looker Studio dashboard. That is the whole pipeline.

```
Cloud Scheduler (timer, 2x/day)
   -> Cloud Workflows (orchestrator)
        -> [parallel] extract-appsflyer job      (download AppsFlyer API -> BigQuery raw)
        -> [parallel] extract-moengage job       (download MoEngage API  -> BigQuery raw)
        -> [parallel] extract-play-console job   (download Play Console API -> BigQuery raw)
        -> dbt-transform job                     (raw -> staging -> mart tables)
              -> Looker Studio dashboard reads the mart tables
```

> Note: `extract-play-console` is in the diagram above but not yet wired into `pipeline.yaml` - it is the next step after GCP infra is provisioned. The current pipeline runs AppsFlyer + MoEngage in parallel.

---

## Glossary

Terms used throughout the docs, plain-language definitions.

### GCP services

| Term | What it is |
|---|---|
| **GCP** | Google Cloud Platform. The cloud provider everything runs on. |
| **GCP project** | A container that holds all the cloud resources (jobs, datasets, secrets). Identified by a project ID (for example `my-company-data-prod`). Everything is scoped to one project. |
| **BigQuery (BQ)** | Google's data warehouse. Where all the data lives, organized into datasets and tables. You query it with SQL. |
| **Dataset** | A folder inside BigQuery that groups related tables. This project has nine: `appsflyer_raw`, `appsflyer_staging`, `appsflyer_mart` for AppsFlyer data; `moengage_raw`, `moengage_staging`, `moengage_mart` for MoEngage data; and `play_raw`, `play_staging`, `play_mart` for Play Console data. |
| **Cloud Run Job** | A container that runs once, does its work, and stops (it is not a web server that stays up). The extract step and the dbt step are each a Cloud Run Job. |
| **Cloud Workflows** | The orchestrator. A small script that runs the jobs in order and waits for each to finish before starting the next. |
| **Cloud Scheduler** | A cron timer in the cloud. Fires on a schedule and starts the Workflow. |
| **Cloud Build** | GCP's build service. Builds the container images and deploys them. Runs in the cloud, so you do not need Docker installed on your laptop. |
| **Artifact Registry** | Where the built container images are stored, so Cloud Run Jobs can pull them. |
| **Secret Manager** | Where secrets (like the AppsFlyer API token) are stored securely. Never put secrets in code or git. |
| **Service account (SA)** | A non-human identity that a job runs as. Each job has its own SA with only the permissions it needs. |
| **IAM** | Identity and Access Management. The system that grants permissions (roles) to service accounts and people. |

### dbt and data layers

| Term | What it is |
|---|---|
| **dbt** | A tool that turns SQL files into BigQuery tables and views, and runs data quality tests. The transform step. |
| **Raw layer** | Data exactly as it came from the API, untouched. Dataset `appsflyer_raw`. Append-only (new rows added each run, nothing deleted). |
| **Staging layer** | Raw data cleaned and typed (text -> dates, numbers), deduplicated. Dataset `appsflyer_staging`. Built as views (no storage, recomputed on read). Models named `stg_*`. |
| **Mart layer** | Final analytics tables the dashboard reads. Dataset `appsflyer_mart`. Built as tables, fully rebuilt each run. Models named `mart_*`. |
| **Model** | One SQL file in dbt that produces one table or view. |
| **Seed** | A small CSV file dbt loads as a table (here: a mapping of AppsFlyer event names to categories). |

### Process words

| Term | What it is |
|---|---|
| **Pipeline** | The whole flow: extract + transform, end to end. |
| **Extract** | Downloading data from the source API. |
| **Transform** | Reshaping raw data into clean analytics tables (the dbt step). |
| **Pull** | One API call to one AppsFlyer endpoint for one app. This pipeline makes 8 pulls per run (4 endpoints x 2 platforms: Android + iOS). |
| **Backfill** | Re-running the pipeline for past dates to load historical data. |
| **T-1** | "Yesterday." The pipeline defaults to extracting yesterday's data, because today's data is not complete yet. |
| **Idempotent** | Safe to run more than once. Re-running a backfill does not create duplicates, because staging deduplicates. |
| **OOM** | Out Of Memory. A job crashed because it needed more RAM than it was given. |
| **CI / CI/CD** | Continuous Integration / Continuous Deployment. Automated checks (tests, lint) on each code change, and automated deploys on each push. |

### Abbreviations and units

| Term | What it is |
|---|---|
| **WIB** | Waktu Indonesia Barat, the Jakarta timezone (UTC+7). The schedule is expressed in WIB. |
| **UTC** | Coordinated Universal Time. AppsFlyer rate-limit quotas reset at 00:00 UTC, which is 07:00 WIB. |
| **API** | Application Programming Interface. How the code talks to AppsFlyer to request data. |
| **SA** | Service account (see above). |
| **BQ** | BigQuery (see above). |

---

## A note on `$PROJECT`

Almost every command in these docs uses `$PROJECT` as a placeholder for the GCP project ID. Before you run any of them, set it once in your terminal:

```bash
export PROJECT=your-gcp-project-id   # the GCP project ID for your environment
```

After that, `$PROJECT` expands to your project ID automatically in every command for the rest of that terminal session. If you open a new terminal window, set it again.

---

## Region

Everything in this project lives in one GCP region: **`asia-southeast2`** (Jakarta). If a command asks for a location or region, it is always `asia-southeast2`.
