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

What it does: runs all test cases in `tests/`. The `-v` flag shows each test name and pass/fail individually.

### Test cases covered

| Test class | What it tests |
|---|---|
| `TestEndpoints` | Endpoint count = 4, correct names, correct BQ table names, timezone param present, geo grouping in master-agg |
| `TestBqLoader` | Empty CSV returns 0 rows, all metadata columns stamped on rows, schema drift flag set when columns differ, schema flag empty when columns match |
| `TestExtractRun` | 8 HTTP pulls fired (4 endpoints x 2 app IDs), raises error when any pull fails |
| `TestHttpRetry` | HTTP 503 triggers retry, raises after 3 attempts |

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

---

## 6. Integration Tests (requires GCP dev access)

These run against the real your dev GCP project. Only run after local tests pass.

### Run the extractor locally against dev BQ

```bash
cd ingestion
make run-appsflyer-local FROM=2026-06-13 TO=2026-06-14
```

What it does: calls the real AppsFlyer API, loads rows into `appsflyer_raw` in the dev BigQuery project. Requires `gcloud auth application-default login` and the `appsflyer-api-token` secret to exist in Secret Manager.

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
4. `terraform validate` (dev and prod)

A PR cannot merge if any of these fail.
