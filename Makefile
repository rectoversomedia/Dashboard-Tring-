SHELL := /bin/bash
ENV ?= dev
REGION ?= asia-southeast2
# Override PROJECT_DEV / PROJECT_PROD via env var or make arg for multi-env migration
PROJECT_DEV ?= dashboard-tring-dev
PROJECT_PROD ?= dashboard-tring-prod
REGISTRY ?= $(REGION)-docker.pkg.dev
REPO ?= tring-service

# Allow full PROJECT override: make run-appsflyer-local PROJECT=hypefast-data-staging
PROJECT ?= $(if $(filter prod,$(ENV)),$(PROJECT_PROD),$(PROJECT_DEV))
IMAGE_INGESTION := $(REGISTRY)/$(PROJECT)/$(REPO)/ingestion
IMAGE_DBT := $(REGISTRY)/$(PROJECT)/$(REPO)/dbt

FROM ?= $(shell date -u +%Y-%m-%d)
TO ?= $(shell date -u +%Y-%m-%d)

.PHONY: setup lint test \
	build-ingestion build-dbt \
	push-ingestion push-dbt \
	tf-init tf-plan tf-apply \
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
	cd transform && dbt parse --profiles-dir .

# -- Docker build --------------------------------------------------------------

build-ingestion:
	docker build -t $(IMAGE_INGESTION):latest ingestion/

build-dbt:
	docker build -t $(IMAGE_DBT):latest transform/

# -- Docker push ---------------------------------------------------------------

push-ingestion: build-ingestion
	docker push $(IMAGE_INGESTION):latest

push-dbt: build-dbt
	docker push $(IMAGE_DBT):latest

# -- Terraform -----------------------------------------------------------------

tf-init:
	terraform -chdir=infra/envs/$(ENV) init

tf-plan:
	terraform -chdir=infra/envs/$(ENV) plan -var-file=terraform.tfvars

tf-apply:
	terraform -chdir=infra/envs/$(ENV) apply -var-file=terraform.tfvars -auto-approve

# -- Cloud Run Job deploy ------------------------------------------------------

deploy-appsflyer:
	gcloud run jobs update extract-appsflyer \
		--image $(IMAGE_INGESTION):latest \
		--region $(REGION) \
		--project $(PROJECT) \
		--set-env-vars GCP_PROJECT=$(PROJECT),BQ_DATASET_RAW=appsflyer_raw,REGION=$(REGION) \
		--set-secrets APPSFLYER_API_TOKEN=appsflyer-api-token:latest \
		--service-account sa-extract-appsflyer@$(PROJECT).iam.gserviceaccount.com \
		--command python \
		--args "-m,tring_ingest,--source,appsflyer,--from,$(FROM),--to,$(TO)"

deploy-dbt:
	gcloud run jobs update dbt-transform \
		--image $(IMAGE_DBT):latest \
		--region $(REGION) \
		--project $(PROJECT) \
		--set-env-vars GCP_PROJECT=$(PROJECT),REGION=$(REGION) \
		--service-account sa-dbt@$(PROJECT).iam.gserviceaccount.com \
		--command dbt \
		--args "build,--profiles-dir,.,--target,$(ENV)"

# -- Workflow + Scheduler deploy -----------------------------------------------

deploy-workflow:
	gcloud workflows deploy pipeline \
		--source orchestration/workflows/pipeline.yaml \
		--location $(REGION) \
		--project $(PROJECT) \
		--service-account sa-workflows@$(PROJECT).iam.gserviceaccount.com

deploy-scheduler:
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

run-appsflyer-local:
	cd ingestion && uv run python -m tring_ingest \
		--source appsflyer \
		--from $(FROM) \
		--to $(TO)

# -- Full deploy ---------------------------------------------------------------

deploy: push-ingestion push-dbt tf-apply deploy-appsflyer deploy-dbt deploy-workflow deploy-scheduler
	@echo "Deploy to $(ENV) complete."
