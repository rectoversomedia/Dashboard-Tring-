terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

variable "project_id"    { type = string }
variable "region"        { type = string }
variable "github_owner"  { type = string }
variable "github_repo"   { type = string }
variable "alert_email"   { type = string }
variable "registry_repo" { type = string }

module "apis" {
  source     = "../../modules/project_apis"
  project_id = var.project_id
}

module "iam" {
  source                     = "../../modules/iam"
  project_id                 = var.project_id
  appsflyer_raw_dataset      = "appsflyer_raw"
  appsflyer_staging_dataset  = "appsflyer_staging"
  appsflyer_mart_dataset     = "appsflyer_mart"
  depends_on                 = [module.apis]
}

module "bigquery" {
  source                     = "../../modules/bigquery"
  project_id                 = var.project_id
  region                     = var.region
  sa_extract_appsflyer_email = module.iam.sa_extract_appsflyer_email
  sa_dbt_email               = module.iam.sa_dbt_email
  depends_on                 = [module.iam]
}

module "artifact_registry" {
  source     = "../../modules/artifact_registry"
  project_id = var.project_id
  region     = var.region
  repo_name  = var.registry_repo
  depends_on = [module.apis]
}

module "secrets" {
  source     = "../../modules/secrets"
  project_id = var.project_id
  depends_on = [module.apis]
}

module "cloud_run_jobs" {
  source                      = "../../modules/cloud_run_jobs"
  project_id                  = var.project_id
  region                      = var.region
  registry_url                = module.artifact_registry.registry_url
  sa_extract_appsflyer_email  = module.iam.sa_extract_appsflyer_email
  sa_dbt_email                = module.iam.sa_dbt_email
  appsflyer_secret_name       = module.secrets.appsflyer_secret_name
  depends_on                  = [module.artifact_registry, module.iam, module.secrets]
}

module "workflows" {
  source              = "../../modules/workflows"
  project_id          = var.project_id
  region              = var.region
  sa_workflows_email  = module.iam.sa_workflows_email
  sa_scheduler_email  = module.iam.sa_scheduler_email
  alert_email         = var.alert_email
  depends_on          = [module.cloud_run_jobs]
}

module "cloudbuild" {
  source        = "../../modules/cloudbuild"
  project_id    = var.project_id
  github_owner  = var.github_owner
  github_repo   = var.github_repo
  depends_on    = [module.apis]
}
