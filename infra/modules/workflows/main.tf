variable "project_id"        { type = string }
variable "region"            { type = string }
variable "sa_workflows_email" { type = string }
variable "sa_scheduler_email" { type = string }
variable "alert_email"       { type = string }

resource "google_workflows_workflow" "pipeline" {
  project         = var.project_id
  region          = var.region
  name            = "pipeline"
  service_account = var.sa_workflows_email
  source_contents = file("${path.module}/../../../orchestration/workflows/pipeline.yaml")
}

resource "google_cloud_scheduler_job" "pipeline_morning" {
  project     = var.project_id
  region      = var.region
  name        = "pipeline-trigger-morning"
  description = "Trigger pipeline at 08:00 WIB (01:00 UTC)"
  schedule    = "0 1 * * *"
  time_zone   = "Asia/Jakarta"

  http_target {
    uri         = "https://workflowexecutions.googleapis.com/v1/projects/${var.project_id}/locations/${var.region}/workflows/pipeline/executions"
    http_method = "POST"
    body        = base64encode("{}")
    oauth_token {
      service_account_email = var.sa_scheduler_email
    }
  }
}

resource "google_cloud_scheduler_job" "pipeline_afternoon" {
  project     = var.project_id
  region      = var.region
  name        = "pipeline-trigger-afternoon"
  description = "Trigger pipeline at 20:00 WIB (13:00 UTC)"
  schedule    = "0 13 * * *"
  time_zone   = "Asia/Jakarta"

  http_target {
    uri         = "https://workflowexecutions.googleapis.com/v1/projects/${var.project_id}/locations/${var.region}/workflows/pipeline/executions"
    http_method = "POST"
    body        = base64encode("{}")
    oauth_token {
      service_account_email = var.sa_scheduler_email
    }
  }
}
