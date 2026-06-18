variable "project_id" { type = string }

# Secret container only. Value is added out of band via:
# echo -n "TOKEN" | gcloud secrets versions add appsflyer-api-token --data-file=- --project=PROJECT
resource "google_secret_manager_secret" "appsflyer_api_token" {
  project   = var.project_id
  secret_id = "appsflyer-api-token"

  replication {
    auto {}
  }
}

output "appsflyer_secret_name" {
  value = google_secret_manager_secret.appsflyer_api_token.name
}
