# Testing Guide

## Overview

Two test layers exist before code reaches GCP:

1. **Local tests** (no GCP, no real API)  -  run on every change
2. **Integration tests** (real GCP dev project)  -  run before deploying to prod

---

## 1. Setup

Install all dependencies including dev tools (pytest, ruff):

```bash
cd ingestion
uv sync --extra dev
```

What it does: creates `.venv/` and installs all packages from `pyproject.toml` into a local `.venv/`. The `--extra dev` flag includes pytest, ruff, and responses (HTTP mock library). Note: the Docker image uses `pip install .` directly (no uv), but for local dev `uv sync` is the right tool.

---

## 2. Lint

### Check for code errors and style issues

```bash
uv run ruff check src/ tests/
```

What it does: scans all Python files for syntax errors, unused imports, bad patterns. Fails with a list of issues if any found.

### Auto-fix fixable issues

```bash
uv run ruff check src/ tests/ --fix
```

What it does: automatically fixes issues that ruff can resolve (import ordering, simple style). Leaves issues that require manual judgment.

### Format code style

```bash
uv run ruff format src/ tests/
```

What it does: reformats all Python files to consistent style (quote style, line length, spacing). Similar to `black`. Safe to run anytime.

### Check format without changing files (used in CI)

```bash
uv run ruff format --check src/ tests/
```

What it does: exits with error if any file would be reformatted. Used in CI to block unformatted code.

---

## 3. Unit Tests

```bash
uv run pytest tests/ -v
```

What it does: runs all test cases in `tests/`. The `-v` flag shows each test name and pass/fail individually. Current suite: **63 tests total** (20 AppsFlyer + 13 MoEngage + 16 Play Console + 11 App Store + 3 BQ loader), all PASS.

### Test cases covered

**AppsFlyer (`test_appsflyer_extract.py`) - 20 tests:**

| Test class | Tests | What it tests |
|---|---|---|
| `TestEndpoints` | 7 | Endpoint count = 4, correct names, correct BQ table names, timezone param present, geo grouping in master-agg, hour chunking disabled by default, `maximum_rows=1_000_000` sent for in_app_events |
| `TestBuildWindows` | 6 | No chunking = single date-only window; hourly chunking covers every hour of each day; slices neither overlap nor skip (`HH:00`-`HH:59`) across 1/2/4/6-hour sizes; a chunk size not dividing 24 still ends at hour 23; rejects reversed date range; rejects chunk_hours outside 1-24 |
| `TestBqLoader` | 2 | Empty CSV returns 0 rows, all metadata columns stamped on rows |
| `TestExtractRun` | 4 | 8 HTTP pulls fired with chunking off (4 endpoints x 2 app IDs); `_extract_from`/`_extract_to` stay day-level (they are DATE columns, hour slices go to the API only); a pull that hits the 200k row cap is logged loudly but is not fatal; raises when any pull fails |
| `TestHttpRetry` | 1 | Retryable HTTP status triggers retry path |

> `TestBuildWindows` and the cap-logging test exist because of the truncation bug found 2026-07-25
> (see `data-catalog-appsflyer.md` -> "Two Independent Hard Limits on Raw Data Pulls"). Hour
> chunking ships **disabled**; the tests cover it as a fallback that is ready but not active.

**MoEngage (`test_moengage_extract.py`) - 13 tests:**

| Test class | Tests | What it tests |
|---|---|---|
| `TestStatsChunking` | 5 | Date range under/at 30 days is one chunk, 31 days splits in two, chunks cover the full range contiguously, attribution and metric type passed through |
| `TestFlattenStats` | 3 | Single platform, two platforms, and empty platforms each flatten correctly |
| `TestExtractRun` | 3 | Search runs before stats, raises on a stats chunk failure, skips stats when there are no campaigns |
| `TestMoEngageClient` | 1 | Auth header set correctly |

**Play Console (`test_play_console_extract.py`) - 16 tests:**

| Test | What it tests |
|---|---|
| `test_date_str_to_dict` | `'2026-06-01'` correctly converts to `{year:2026, month:6, day:1}` |
| `test_date_str_to_dict_zero_pad` | Month/day zero-padded correctly in date string |
| `test_flatten_reporting_row_basic` | Metric values + date + dimension extracted from API response |
| `test_flatten_reporting_row_confidence_interval` | CI bounds written when API returns them |
| `test_flatten_reporting_row_no_ci` | Row without CI bounds produces no `_ci_lower`/`_ci_upper` keys |
| `test_flatten_reporting_row_multi_dimension` | Multiple dimensions (reportType + versionCode) both extracted |
| `test_flatten_review_basic` | All review fields extracted, empty developer reply handled |
| `test_flatten_review_with_reply` | Developer reply text and timestamp extracted |
| `test_flatten_review_star_rating` | Star rating cast to string correctly |
| `test_pull_metric_set_returns_flattened` | `_pull_metric_set` calls API and returns flattened rows |
| `test_pull_metric_set_empty_response` | Empty API response returns empty list |
| `test_pull_all_reviews_single_page` | Single page of reviews returned correctly |
| `test_pull_all_reviews_pagination` | `nextPageToken` triggers second page call |
| `test_pull_all_reviews_empty` | Empty review list returns empty list |
| `test_run_calls_all_metric_sets_and_reviews` | `run()` fires all 6 metric sets + reviews pull (7 total) |
| `test_run_collects_errors_raises_at_end` | Failed pulls collected; `RuntimeError` raised at end with all failures |

**App Store (`test_appstore_extract.py`) - 11 tests:**

| Test | What it tests |
|---|---|
| `test_snake` | `_snake()` strips, lowercases, replaces spaces with underscores |
| `test_flatten_tsv_basic` | TSV text with 2 rows produces 2 dicts with correct keys |
| `test_flatten_tsv_empty` | Empty string returns empty list |
| `test_flatten_review` | All review fields (title, body, rating, territory, nickname) extracted correctly |
| `test_resolve_report_ids_returns_matched` | `_resolve_report_ids` matches reports by name, returns (report_id, table) pairs |
| `test_resolve_report_ids_pagination` | `nextPageToken` link triggers second GET call |
| `test_pull_analytics_report_downloads_and_decompresses` | Segments fetched, S3 URL downloaded via `get_unsigned`, gzip decompressed, rows returned |
| `test_pull_analytics_report_skips_missing_url` | Segment with no `url` attribute is skipped cleanly |
| `test_run_loads_reviews_and_analytics` | `run()` calls reviews pull + all 5 analytics reports, `load_json_rows_to_raw` called 6 times |
| `test_run_skips_unmatched_report` | Report not in ANALYTICS_REPORTS is ignored silently |
| `test_run_collects_errors_raises_at_end` | One analytics report fails, remaining reports still load, `RuntimeError` raised at end listing all failed reports |

All tests are mocked  -  no real HTTP calls, no real BigQuery connection needed.

### Run a single test class

```bash
uv run pytest tests/ -v -k TestBqLoader
```

What it does: runs only tests matching the pattern `TestBqLoader`. Useful when debugging a specific area.

### Run with output on failure

```bash
uv run pytest tests/ -v --tb=short
```

What it does: shows a short traceback when a test fails, easier to read than the full traceback.

---

## 4. dbt Parse (SQL Syntax Check)

```bash
cd transform
dbt parse --profiles-dir .
```

What it does: parses all `.sql` model files and `.yml` config files without connecting to BigQuery. Catches SQL syntax errors, missing `ref()` targets, bad YAML keys. Fast  -  completes in under 2 seconds.

### Check source freshness config

```bash
dbt source freshness --profiles-dir . --target dev
```

What it does: connects to BigQuery dev and checks that `_ingested_at` in each raw table is within the expected freshness window. Requires a live BQ connection.

---

## 5. Full Local Test Suite (run before every commit)

```bash
cd ingestion
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run pytest tests/ -v
cd ../transform
dbt parse --profiles-dir .
```

Or via Makefile from the repo root:

```bash
make test
```

What `make test` does: runs pytest and dbt parse in sequence. Fails fast if either fails.

If pre-commit is installed (see section 9), it runs ruff automatically on every `git commit` so you do not need to run lint manually before committing.

---

## 6. Integration Tests (requires GCP dev access)

These run against a real GCP dev project. Only run after local tests pass.

### Run the extractor locally against dev BQ

All three extractors require `--from` and `--to` date arguments. Run from inside the `ingestion/` directory.

**AppsFlyer** (shortcut via Makefile, run from repo root):
```bash
make run-appsflyer-local PROJECT=your-dev-project FROM=2026-06-22 TO=2026-06-22
```

**MoEngage** (run from inside `ingestion/`):
```bash
cd ingestion
GCP_PROJECT=your-dev-project uv run python -m tring_ingest \
  --source moengage \
  --from 2026-06-22 \
  --to 2026-06-22
```

**Play Console** (run from inside `ingestion/`):
```bash
cd ingestion
GCP_PROJECT=your-dev-project \
  PLAY_CONSOLE_SECRET_NAME=play-console-sa-key \
  uv run python -m tring_ingest \
  --source play_console \
  --from 2026-06-22 \
  --to 2026-06-22
```

**App Store** (run from inside `ingestion/`):
```bash
cd ingestion
GCP_PROJECT=your-dev-project \
  APPSTORE_SECRET_NAME=appstore-connect-key \
  APPSTORE_APP_ID=1350501409 \
  uv run python -m tring_ingest \
  --source app_store \
  --from 2026-06-22 \
  --to 2026-06-22
```

> Note: `--from`/`--to` only affects the reviews pull. Analytics downloads are stateless - Apple determines which date instances are available. dbt staging deduplicates on re-run.

What each does: calls the real API for that source, loads rows into the corresponding raw BQ dataset. Requires `gcloud auth application-default login` and the relevant secret to exist in Secret Manager.

### Run dbt against dev

```bash
cd transform
dbt build --profiles-dir . --target dev
```

What it does: runs all models (seed, staging, mart) and all tests against the dev BigQuery project. Requires data to exist in `appsflyer_raw` first (run the extractor above).

### Verify BQ tables after a run

```bash
bq query --project_id=${PROJECT} --use_legacy_sql=false \
  'SELECT COUNT(*) as row_count, MAX(_ingested_at) as latest FROM `appsflyer_raw.raw_installs`'
```

What it does: spot-check that rows landed in raw with a recent ingestion timestamp. Use `row_count` not `rows` - `rows` is a reserved word in BigQuery standard SQL.

---

## 7. What Each Test Layer Catches

| Layer | What it catches | When to run |
|---|---|---|
| `ruff check` | Syntax errors, unused imports, bad patterns | Every change |
| `ruff format` | Inconsistent formatting | Every change |
| `pytest` | Logic bugs, metadata stamping, retry behavior, 8-pull count | Every change |
| `dbt parse` | SQL syntax, broken `ref()`, bad YAML | Every dbt change |
| Local extractor run | Real API response shape, BQ load errors | Before merging AppsFlyer changes |
| `dbt build` on dev | Full pipeline correctness, dbt test failures | Before merging dbt changes |

---

## 8. CI Automation

The `cloudbuild/ci.yaml` trigger runs automatically on every pull request:

1. `ruff check` + `ruff format --check`
2. `pytest`
3. `dbt parse`

A PR cannot merge if any of these fail.

> CI does not validate Terraform. Terraform in `infra/` is reference-only and is not part of the deploy path (provisioning is done via `gcloud`, see `gcp-setup.md`). If the client later adopts Terraform, add a `terraform validate` step here.

---

## 9. Pre-commit Hooks (optional but recommended)

Pre-commit is a tool that runs checks automatically every time you run `git commit`. If any check fails, the commit is blocked and you have to fix the issue first. This prevents accidentally committing code with lint errors or formatting issues.

### What checks run on every commit

| Hook | What it does |
|---|---|
| `ruff` | Lint Python files, auto-fix what it can |
| `ruff-format` | Reformat Python files to consistent style |
| `trailing-whitespace` | Remove trailing spaces from all files |
| `end-of-file-fixer` | Make sure all files end with a newline |
| `check-yaml` | Validate YAML file syntax |
| `check-added-large-files` | Block commits that accidentally include large files |
| `detect-private-key` | Block commits that contain private key content |
| `check-merge-conflict` | Block commits that still have `<<<<<<` conflict markers |

The config file is `.pre-commit-config.yaml` at the repo root (same level as `.git`). Pre-commit reads this file to know which hooks to run.

### Setup (one-time, per developer machine)

Run this once after cloning the repo:

```bash
make setup
```

What `make setup` does: runs `uv sync` to install dependencies, then runs `pre-commit install` to register the hooks into `.git/hooks/pre-commit`. After this, every `git commit` in this repo will trigger the hooks automatically.

### How it works in practice

```bash
git add src/tring_ingest/some_file.py
git commit -m "fix something"
# pre-commit runs ruff, ruff-format, trailing-whitespace, etc.
# if all pass: commit goes through
# if any fail: commit is blocked, fix the issue, git add again, then commit
```

### Run hooks manually without committing

```bash
cd ingestion
uv run pre-commit run --all-files
```

What it does: runs all hooks against every file right now, without needing to do a git commit. Useful to check the whole codebase at once.

### If you need to skip hooks temporarily

```bash
git commit --no-verify -m "your message"
```

**Only do this if you have a good reason.** Skipping hooks means lint errors can slip into the repo. CI will still catch them and block the merge.
