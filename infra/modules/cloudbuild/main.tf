variable "project_id"     { type = string }
variable "github_owner"   { type = string }
variable "github_repo"    { type = string }

# Cloud Build service account for CI/CD
resource "google_service_account" "sa_cloudbuild" {
  project      = var.project_id
  account_id   = "sa-cloudbuild"
  display_name = "Cloud Build CI/CD"
}

# Grant deploy roles to Cloud Build SA (least privilege)
locals {
  cloudbuild_roles = [
    "roles/run.developer",
    "roles/artifactregistry.writer",
    "roles/bigquery.user",
    "roles/bigquery.dataEditor",
    "roles/cloudbuild.builds.editor",
    "roles/iam.serviceAccountUser",
  ]
}

resource "google_project_iam_member" "cloudbuild_roles" {
  for_each = toset(local.cloudbuild_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.sa_cloudbuild.email}"
}

output "sa_cloudbuild_email" {
  value = google_service_account.sa_cloudbuild.email
}
