SHELL := /bin/bash
ENV ?= dev
REGION ?= asia-southeast2
# Set per environment. No default project IDs are baked in  -  the GCP project differs per env
# (consultant dev vs client prod). Set via env var or make arg:
#   make deploy ENV=prod PROJECT_PROD=your-client-prod-project
#   make run-appsflyer-local PROJECT=your-dev-project
PROJECT_DEV ?=
PROJECT_PROD ?=
REGISTRY ?= $(REGION)-docker.pkg.dev
REPO ?= tring-service

PROJECT ?= $(if $(filter prod,$(ENV)),$(PROJECT_PROD),$(PROJECT_DEV))
IMAGE_INGESTION := $(REGISTRY)/$(PROJECT)/$(REPO)/ingestion
IMAGE_DBT := $(REGISTRY)/$(PROJECT)/$(REPO)/dbt

# Guard: any target that talks to GCP must depend on `require-project` so an unset
# PROJECT fails fast with a clear message instead of building a broken //repo path.
# Lint/test/local targets do NOT require it.
require-project:
	@test -n "$(PROJECT)" || { echo "ERROR: PROJECT is not set. Pass PROJECT=your-gcp-project (or PROJECT_DEV / PROJECT_PROD) - no default project is baked in."; exit 1; }

FROM ?= $(shell date -u +%Y-%m-%d)
TO ?= $(shell date -u +%Y-%m-%d)

.PHONY: setup lint test \
	require-project \
	build-ingestion build-dbt \
	push-ingestion push-dbt \
	tf-init tf-plan tf-apply \
	create-appsflyer create-dbt \
	deploy-appsflyer deploy-dbt deploy-workflow deploy-scheduler \
	run-appsflyer-local deploy

# -- Dev setup -----------------------------------------------------------------

setup:
	cd ingestion && uv sync
	cd ingestion && uv run pre-commit install

# -- Lint ----------------------------------------------------------------------

lint:
	cd ingestion && uv run ruff check src/ tests/
	cd ingestion && uv run ruff format --check src/ tests/

# -- Test ----------------------------------------------------------------------

test:
	cd ingestion && uv run pytest tests/ -v
	# dbt parse only renders the project; it does not connect to BQ. GCP_PROJECT just needs
	# to be non-empty so profiles.yml resolves. Matches ci.yaml's GCP_PROJECT=ci-placeholder.
	cd transform && GCP_PROJECT=$${GCP_PROJECT:-ci-placeholder} dbt parse --profiles-dir .

# -- Docker build --------------------------------------------------------------

build-ingestion:
	docker build -t $(IMAGE_INGESTION):latest ingestion/

build-dbt:
	docker build -t $(IMAGE_DBT):latest transform/

# -- Docker push ---------------------------------------------------------------

push-ingestion: require-project build-ingestion
	docker push $(IMAGE_INGESTION):latest

push-dbt: require-project build-dbt
	docker push $(IMAGE_DBT):latest

# -- Terraform -----------------------------------------------------------------

tf-init:
	terraform -chdir=infra/envs/$(ENV) init

tf-plan:
	terraform -chdir=infra/envs/$(ENV) plan -var-file=terraform.tfvars

tf-apply:
	terraform -chdir=infra/envs/$(ENV) apply -var-file=terraform.tfvars -auto-approve

# -- Cloud Run Job deploy ------------------------------------------------------
# create-* = first-time job creation (run once per env)
# deploy-* = update existing job after new image push

# extract-appsflyer: --command/--args set the entrypoint; dates come from DATE_FROM/DATE_TO
# env vars injected at runtime by Cloud Workflows (or --update-env-vars on manual execute).
create-appsflyer: require-project
	gcloud run jobs create extract-appsflyer \
		--image $(IMAGE_INGESTION):latest \
		--region $(REGION) \
		--project $(PROJECT) \
		--set-env-vars GCP_PROJECT=$(PROJECT),BQ_DATASET_RAW=appsflyer_raw,REGION=$(REGION) \
		--set-secrets APPSFLYER_API_TOKEN=appsflyer-api-token:latest \
		--service-account sa-extract-appsflyer@$(PROJECT).iam.gserviceaccount.com \
		--command python \
		--args "-m,tring_ingest,--source,appsflyer"

# dbt-transform: NO --command/--args. The Dockerfile ENTRYPOINT runs
# `dbt build --profiles-dir /app --target prod`. Overriding it here would break dbt.
create-dbt: require-project
	gcloud run jobs create dbt-transform \
		--image $(IMAGE_DBT):latest \
		--region $(REGION) \
		--project $(PROJECT) \
		--set-env-vars GCP_PROJECT=$(PROJECT) \
		--service-account sa-dbt@$(PROJECT).iam.gserviceaccount.com

deploy-appsflyer: require-project
	gcloud run jobs update extract-appsflyer \
		--image $(IMAGE_INGESTION):latest \
		--region $(REGION) \
		--project $(PROJECT)

deploy-dbt: require-project
	gcloud run jobs update dbt-transform \
		--image $(IMAGE_DBT):latest \
		--region $(REGION) \
		--project $(PROJECT)

# -- Workflow + Scheduler deploy -----------------------------------------------

deploy-workflow: require-project
	gcloud workflows deploy pipeline \
		--source orchestration/workflows/pipeline.yaml \
		--location $(REGION) \
		--project $(PROJECT) \
		--service-account sa-workflows@$(PROJECT).iam.gserviceaccount.com

deploy-scheduler: require-project
	gcloud scheduler jobs update http pipeline-trigger-morning \
		--schedule "0 1 * * *" \
		--time-zone "Asia/Jakarta" \
		--uri "https://workflowexecutions.googleapis.com/v1/projects/$(PROJECT)/locations/$(REGION)/workflows/pipeline/executions" \
		--message-body '{}' \
		--oauth-service-account-email sa-scheduler@$(PROJECT).iam.gserviceaccount.com \
		--location $(REGION) \
		--project $(PROJECT)
	gcloud scheduler jobs update http pipeline-trigger-afternoon \
		--schedule "0 13 * * *" \
		--time-zone "Asia/Jakarta" \
		--uri "https://workflowexecutions.googleapis.com/v1/projects/$(PROJECT)/locations/$(REGION)/workflows/pipeline/executions" \
		--message-body '{}' \
		--oauth-service-account-email sa-scheduler@$(PROJECT).iam.gserviceaccount.com \
		--location $(REGION) \
		--project $(PROJECT)

# -- Local run -----------------------------------------------------------------

run-appsflyer-local: require-project
	cd ingestion && GCP_PROJECT=$(PROJECT) uv run python -m tring_ingest \
		--source appsflyer \
		--from $(FROM) \
		--to $(TO)

# -- Full deploy ---------------------------------------------------------------
# Rolls new images onto EXISTING jobs. The jobs/workflow/scheduler are created once
# via the create-* targets (or docs/gcp-setup.md steps 8-10). No Terraform.

deploy: require-project push-ingestion push-dbt deploy-appsflyer deploy-dbt deploy-workflow deploy-scheduler
	@echo "Deploy to $(ENV) complete."
