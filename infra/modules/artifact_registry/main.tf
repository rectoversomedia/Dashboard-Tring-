variable "project_id" { type = string }
variable "region"     { type = string }
variable "repo_name"  { type = string }

resource "google_artifact_registry_repository" "images" {
  project       = var.project_id
  location      = var.region
  repository_id = var.repo_name
  format        = "DOCKER"
  description   = "Container images for Dashboard Monitoring & AI Insight data pipeline"
}

output "registry_url" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${var.repo_name}"
}
