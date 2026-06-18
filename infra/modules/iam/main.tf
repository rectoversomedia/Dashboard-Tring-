variable "project_id" { type = string }
variable "appsflyer_raw_dataset"     { type = string }
variable "appsflyer_staging_dataset" { type = string }
variable "appsflyer_mart_dataset"    { type = string }

# Service account: AppsFlyer extractor
resource "google_service_account" "sa_extract_appsflyer" {
  project      = var.project_id
  account_id   = "sa-extract-appsflyer"
  display_name = "AppsFlyer extractor runtime"
}

# Service account: dbt transform
resource "google_service_account" "sa_dbt" {
  project      = var.project_id
  account_id   = "sa-dbt"
  display_name = "dbt transform runtime"
}

# Service account: Cloud Workflows
resource "google_service_account" "sa_workflows" {
  project      = var.project_id
  account_id   = "sa-workflows"
  display_name = "Cloud Workflows orchestrator"
}

# Service account: Cloud Scheduler
resource "google_service_account" "sa_scheduler" {
  project      = var.project_id
  account_id   = "sa-scheduler"
  display_name = "Cloud Scheduler trigger"
}

# AppsFlyer SA: access its own secret
resource "google_project_iam_member" "appsflyer_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.sa_extract_appsflyer.email}"
}

# AppsFlyer SA: BQ job user (required to run load jobs)
resource "google_project_iam_member" "appsflyer_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.sa_extract_appsflyer.email}"
}

# dbt SA: BQ job user
resource "google_project_iam_member" "dbt_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.sa_dbt.email}"
}

# Workflows SA: invoke Cloud Run jobs
resource "google_project_iam_member" "workflows_run_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.sa_workflows.email}"
}

output "sa_extract_appsflyer_email" {
  value = google_service_account.sa_extract_appsflyer.email
}

output "sa_dbt_email" {
  value = google_service_account.sa_dbt.email
}

output "sa_workflows_email" {
  value = google_service_account.sa_workflows.email
}

output "sa_scheduler_email" {
  value = google_service_account.sa_scheduler.email
}
