variable "project_id"                   { type = string }
variable "region"                        { type = string }
variable "registry_url"                  { type = string }
variable "sa_extract_appsflyer_email"   { type = string }
variable "sa_dbt_email"                  { type = string }
variable "appsflyer_secret_name"         { type = string }

resource "google_cloud_run_v2_job" "extract_appsflyer" {
  project  = var.project_id
  location = var.region
  name     = "extract-appsflyer"

  template {
    template {
      service_account = var.sa_extract_appsflyer_email
      containers {
        image = "${var.registry_url}/ingestion:latest"
        env {
          name  = "GCP_PROJECT"
          value = var.project_id
        }
        env {
          name  = "BQ_DATASET_RAW"
          value = "appsflyer_raw"
        }
        env {
          name  = "REGION"
          value = var.region
        }
        env {
          name = "APPSFLYER_API_TOKEN"
          value_source {
            secret_key_ref {
              secret  = var.appsflyer_secret_name
              version = "latest"
            }
          }
        }
      }
    }
  }
}

resource "google_cloud_run_v2_job" "dbt_transform" {
  project  = var.project_id
  location = var.region
  name     = "dbt-transform"

  template {
    template {
      service_account = var.sa_dbt_email
      containers {
        image = "${var.registry_url}/dbt:latest"
        command = ["dbt"]
        args    = ["build", "--profiles-dir", ".", "--target", "prod"]
        env {
          name  = "GCP_PROJECT"
          value = var.project_id
        }
      }
    }
  }
}
