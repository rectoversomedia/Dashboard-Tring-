SHELL := /bin/bash
ENV ?= dev
REGION ?= asia-southeast2
# No default project IDs. Pass via env var: make deploy ENV=prod PROJECT_PROD=your-client-prod-project
PROJECT_DEV ?=
PROJECT_PROD ?=
REGISTRY ?= $(REGION)-docker.pkg.dev
REPO ?= tring-service

PROJECT ?= $(if $(filter prod,$(ENV)),$(PROJECT_PROD),$(PROJECT_DEV))
IMAGE_PIPELINE := $(REGISTRY)/$(PROJECT)/$(REPO)/pipeline

# Guard: GCP targets depend on this so an unset PROJECT fails fast with a clear message.
require-project:
	@test -n "$(PROJECT)" || { echo "ERROR: PROJECT is not set. Pass PROJECT=your-gcp-project (or PROJECT_DEV / PROJECT_PROD) - no default project is baked in."; exit 1; }

FROM ?= $(shell date -u +%Y-%m-%d)
TO ?= $(shell date -u +%Y-%m-%d)

.PHONY: setup lint test \
	require-project \
	build push \
	tf-init tf-plan tf-apply \
	create-appsflyer create-moengage create-play-console create-app-store create-dbt \
	deploy-appsflyer deploy-moengage deploy-play-console deploy-app-store deploy-dbt deploy-workflow deploy-scheduler \
	run-appsflyer-local run-appsflyer run-moengage run-play-console run-app-store run-pipeline deploy \
	cloudbuild-deploy-prod cloudbuild-deploy-dev

# -- Dev setup -----------------------------------------------------------------

setup:
	cd ingestion && uv sync --extra dev
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

# -- Docker build + push -------------------------------------------------------

build:
	docker build -t $(IMAGE_PIPELINE):latest .

push: require-project build
	docker push $(IMAGE_PIPELINE):latest

# -- Terraform -----------------------------------------------------------------

tf-init:
	terraform -chdir=infra/envs/$(ENV) init

tf-plan:
	terraform -chdir=infra/envs/$(ENV) plan -var-file=terraform.tfvars

tf-apply:
	terraform -chdir=infra/envs/$(ENV) apply -var-file=terraform.tfvars -auto-approve

# -- Cloud Run Job deploy (create-* = first-time, deploy-* = update existing job) --

# All jobs use IMAGE_PIPELINE. Each must set --command/--args (image has no ENTRYPOINT).
# Dates (DATE_FROM/DATE_TO) are injected at runtime by Cloud Workflows.

create-appsflyer: require-project
	gcloud run jobs create extract-appsflyer \
		--image $(IMAGE_PIPELINE):latest \
		--region $(REGION) \
		--project $(PROJECT) \
		--set-env-vars GCP_PROJECT=$(PROJECT),BQ_DATASET_RAW=appsflyer_raw,REGION=$(REGION) \
		--set-secrets APPSFLYER_API_TOKEN=appsflyer-api-token:latest \
		--service-account sa-extract-appsflyer@$(PROJECT).iam.gserviceaccount.com \
		--command python \
		--args "-m,tring_ingest,--source,appsflyer"

create-moengage: require-project
	gcloud run jobs create extract-moengage \
		--image $(IMAGE_PIPELINE):latest \
		--region $(REGION) \
		--project $(PROJECT) \
		--set-env-vars GCP_PROJECT=$(PROJECT),BQ_DATASET_RAW_MOENGAGE=moengage_raw,REGION=$(REGION) \
		--set-secrets MOENGAGE_API_CREDS=moengage-api-creds:latest \
		--service-account sa-extract-moengage@$(PROJECT).iam.gserviceaccount.com \
		--command python \
		--args "-m,tring_ingest,--source,moengage"

# PLAY_CONSOLE_SECRET_NAME tells config.py which Secret Manager secret holds the SA key JSON.
create-play-console: require-project
	gcloud run jobs create extract-play-console \
		--image $(IMAGE_PIPELINE):latest \
		--region $(REGION) \
		--project $(PROJECT) \
		--set-env-vars GCP_PROJECT=$(PROJECT),BQ_DATASET_RAW_PLAY_CONSOLE=play_raw,REGION=$(REGION),PLAY_CONSOLE_SECRET_NAME=play-console-sa-key \
		--service-account sa-extract-play-console@$(PROJECT).iam.gserviceaccount.com \
		--command python \
		--args "-m,tring_ingest,--source,play_console"

create-app-store: require-project
	gcloud run jobs create extract-app-store \
		--image $(IMAGE_PIPELINE):latest \
		--region $(REGION) \
		--project $(PROJECT) \
		--set-env-vars GCP_PROJECT=$(PROJECT),BQ_DATASET_RAW_APPSTORE=appstore_raw,REGION=$(REGION),APPSTORE_SECRET_NAME=appstore-connect-key,APPSTORE_APP_ID=1350501409 \
		--service-account sa-extract-app-store@$(PROJECT).iam.gserviceaccount.com \
		--command python \
		--args "-m,tring_ingest,--source,app_store"

# DBT_PROFILES_DIR avoids --profiles-dir in args (gcloud parse error with multiple --*dir flags).
create-dbt: require-project
	gcloud run jobs create dbt-transform \
		--image $(IMAGE_PIPELINE):latest \
		--region $(REGION) \
		--project $(PROJECT) \
		--set-env-vars GCP_PROJECT=$(PROJECT),DBT_PROFILES_DIR=/app/transform \
		--service-account sa-dbt@$(PROJECT).iam.gserviceaccount.com \
		--command dbt \
		--args "build,--project-dir,/app/transform,--target,prod,--target-path,/tmp/dbt-target"

deploy-appsflyer: require-project
	gcloud run jobs update extract-appsflyer \
		--image $(IMAGE_PIPELINE):latest \
		--command python \
		--args "-m,tring_ingest,--source,appsflyer" \
		--region $(REGION) \
		--project $(PROJECT)

deploy-moengage: require-project
	gcloud run jobs update extract-moengage \
		--image $(IMAGE_PIPELINE):latest \
		--command python \
		--args "-m,tring_ingest,--source,moengage" \
		--region $(REGION) \
		--project $(PROJECT)

deploy-play-console: require-project
	gcloud run jobs update extract-play-console \
		--image $(IMAGE_PIPELINE):latest \
		--command python \
		--args "-m,tring_ingest,--source,play_console" \
		--region $(REGION) \
		--project $(PROJECT)

deploy-app-store: require-project
	gcloud run jobs update extract-app-store \
		--image $(IMAGE_PIPELINE):latest \
		--command python \
		--args "-m,tring_ingest,--source,app_store" \
		--region $(REGION) \
		--project $(PROJECT)

deploy-dbt: require-project
	gcloud run jobs update dbt-transform \
		--image $(IMAGE_PIPELINE):latest \
		--command dbt \
		--args "build,--project-dir,/app/transform,--target,prod,--target-path,/tmp/dbt-target" \
		--update-env-vars DBT_PROFILES_DIR=/app/transform \
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

# -- Cloud Run Job manual execute (triggers existing job on GCP, no Docker required) --
# Usage: make run-appsflyer PROJECT=your-project [FROM=2026-01-01 TO=2026-06-28]

run-appsflyer: require-project
	gcloud run jobs execute extract-appsflyer \
		--region $(REGION) \
		--project $(PROJECT) \
		--update-env-vars DATE_FROM=$(FROM),DATE_TO=$(TO) \
		--wait

run-moengage: require-project
	gcloud run jobs execute extract-moengage \
		--region $(REGION) \
		--project $(PROJECT) \
		--update-env-vars DATE_FROM=$(FROM),DATE_TO=$(TO) \
		--wait

run-play-console: require-project
	gcloud run jobs execute extract-play-console \
		--region $(REGION) \
		--project $(PROJECT) \
		--update-env-vars DATE_FROM=$(FROM),DATE_TO=$(TO) \
		--wait

run-app-store: require-project
	gcloud run jobs execute extract-app-store \
		--region $(REGION) \
		--project $(PROJECT) \
		--update-env-vars DATE_FROM=$(FROM),DATE_TO=$(TO) \
		--wait

run-pipeline: require-project
	gcloud workflows run pipeline \
		--location $(REGION) \
		--project $(PROJECT)

# -- Cloud Build deploy (no Docker Desktop needed; builds in Cloud Build and deploys all jobs) --

cloudbuild-deploy-prod: require-project
	gcloud builds submit . \
		--config=cloudbuild/deploy-prod.yaml \
		--substitutions="_PROJECT=$(PROJECT),COMMIT_SHA=latest" \
		--project=$(PROJECT)

cloudbuild-deploy-dev: require-project
	gcloud builds submit . \
		--config=cloudbuild/deploy-dev.yaml \
		--substitutions="_PROJECT=$(PROJECT),COMMIT_SHA=latest" \
		--project=$(PROJECT)

# -- Full deploy (rolls new image onto existing jobs; jobs must already exist via create-* targets) --

deploy: require-project push deploy-appsflyer deploy-moengage deploy-play-console deploy-app-store deploy-dbt deploy-workflow deploy-scheduler
	@echo "Deploy to $(ENV) complete."
