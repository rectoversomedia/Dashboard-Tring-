# Contributing Guide

For developers working on this pipeline.

---

## Branch Strategy

Two long-lived branches:

| Branch | Deploys to | Purpose |
|---|---|---|
| `develop` | Dev GCP project | Integration testing, feature verification |
| `main` | Prod GCP project (client) | Live production pipeline |

**Never push directly to `main` or `develop`.** All changes go through a feature branch + PR first.

---

## Development Workflow

**Step 1 — Create feature branch from develop**
```bash
git checkout develop
git pull origin develop
git checkout -b feature/your-feature   # e.g. feature/add-appsflyer-endpoint
```

**Step 2 — Make changes + run local checks**
```bash
make test    # 38 tests + dbt parse
make lint    # ruff
```

**Step 3 — Stage, commit, push**
```bash
# stage specific files (never git add -A or git add . blindly)
git add path/to/changed/file.py

# commit — pre-commit hooks run automatically (ruff, trailing whitespace, detect-secrets)
# if ruff auto-fixes files, git add the fixed files then re-run git commit
git commit -m "feat ingestion - describe what changed"

# push to both remotes
git push origin feature/your-feature
git push rectoverso feature/your-feature
```

**Step 4 — Open PR: feature → develop**

1. Go to GitHub → rectoversomedia/Dashboard-Tring- (remote: `rectoverso`)
2. Banner "feature/your-feature had recent pushes" → click **Compare & pull request**
   - Or: Pull requests → New pull request → base: `develop` ← compare: `feature/your-feature`
3. Fill title + description → click **Create pull request**
4. Review changes → click **Merge pull request** → **Confirm merge**
5. Delete branch after merge (GitHub will prompt)

**Step 5 — Sync local develop after PR merged**
```bash
git checkout develop
git pull origin develop
git pull rectoverso develop   # keep rectoverso in sync
```

**Step 6 — Verify on dev GCP**
- Cloud Build auto-deploys to dev GCP (if trigger set up)
- Or deploy manually: `gcloud builds submit . --config=cloudbuild/deploy-dev.yaml --substitutions=_PROJECT=YOUR_DEV_PROJECT,COMMIT_SHA=latest --project=YOUR_DEV_PROJECT`
- Run E2E verify: `gcloud workflows run pipeline --location=asia-southeast2 --project=YOUR_DEV_PROJECT`
- Check Cloud Logging for errors (see runbook.md §1)

**Step 7 — Open PR: develop → main**

1. Go to GitHub → rectoversomedia/Dashboard-Tring- → Pull requests → New pull request
   - base: `main` ← compare: `develop`
2. Title: e.g. `release - deploy verified develop to prod`
3. Review → **Create pull request** → **Merge pull request** → **Confirm merge**
   - **NEVER** `git merge` directly — always use PR on GitHub

**Step 8 — Sync local main after PR merged**
```bash
git checkout main
git pull origin main
git push rectoverso main   # keep rectoverso in sync
```

---

## Local Checks (required before PR)

```bash
cd tring-data-pipeline

# install deps
cd ingestion && uv sync --extra dev && cd ..

# lint + format
make lint

# tests (ingestion unit tests + dbt parse)
make test
```

All checks must pass. Pre-commit hooks (ruff, trailing whitespace, detect-secrets) run automatically on `git commit`.

---

## Cloud Build Triggers (set up once by client admin)

| Trigger | Branch | Config file | Target |
|---|---|---|---|
| `deploy-develop` | `develop` | `cloudbuild/deploy-dev.yaml` | Dev GCP |
| `deploy-main` | `main` | `cloudbuild/deploy-prod.yaml` | Prod GCP |

Setup: see `docs/handover.md` Step 4. Requires GitLab connection + VPN access to client GCP.

Until triggers are set up, deploy manually:

```bash
# deploy to dev manually
gcloud builds submit . \
  --config=cloudbuild/deploy-dev.yaml \
  --substitutions=_PROJECT=YOUR_DEV_PROJECT,COMMIT_SHA=latest \
  --project=YOUR_DEV_PROJECT

# deploy to prod manually
gcloud builds submit . \
  --config=cloudbuild/deploy-prod.yaml \
  --substitutions=_PROJECT=YOUR_PROD_PROJECT,COMMIT_SHA=latest \
  --project=YOUR_PROD_PROJECT
```

---

## Commit Message Format

```
<type> <scope> - <short description>

Types: feat, fix, docs, chore, refactor, test
Scope: ingestion, transform, orchestration, infra, docs

Examples:
  feat ingestion - add new appsflyer endpoint
  fix transform - handle null values in mart_appsflyer
  docs - update runbook backfill section
  chore orchestration - bump workflow retry count
```

No `Co-authored-by` lines. No conventional commit prefixes with colon (`feat:` not allowed — use `feat scope - desc`).

---

## Environment Variables

Never hardcode credentials. All secrets via Secret Manager or `.env` (gitignored).

```bash
# local .env (never commit)
APPSFLYER_API_TOKEN=...
MOENGAGE_API_CREDS=...
PLAY_CONSOLE_SECRET_NAME=...
APPSTORE_KEY_ID=...
APPSTORE_ISSUER_ID=...
APPSTORE_P8_PATH=...
GCP_PROJECT=...
```

---

## Adding a New Data Source or Endpoint

See `docs/adding-endpoints.md` for step-by-step guide.
