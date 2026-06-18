variable "project_id" { type = string }
variable "region"     { type = string }
variable "sa_extract_appsflyer_email" { type = string }
variable "sa_dbt_email"               { type = string }

resource "google_bigquery_dataset" "appsflyer_raw" {
  project     = var.project_id
  dataset_id  = "appsflyer_raw"
  location    = var.region
  description = "AppsFlyer raw verbatim data. Append-only, immutable."

  access {
    role          = "WRITER"
    user_by_email = var.sa_extract_appsflyer_email
  }
  access {
    role          = "READER"
    user_by_email = var.sa_dbt_email
  }
  access {
    role = "OWNER"
    special_group = "projectOwners"
  }
}

resource "google_bigquery_dataset" "appsflyer_staging" {
  project     = var.project_id
  dataset_id  = "appsflyer_staging"
  location    = var.region
  description = "AppsFlyer staging: typed, deduped, business logic in dbt views."

  access {
    role          = "WRITER"
    user_by_email = var.sa_dbt_email
  }
  access {
    role = "OWNER"
    special_group = "projectOwners"
  }
}

resource "google_bigquery_dataset" "appsflyer_mart" {
  project     = var.project_id
  dataset_id  = "appsflyer_mart"
  location    = var.region
  description = "AppsFlyer mart: aggregated, partitioned, clustered. Looker Studio reads here."

  access {
    role          = "WRITER"
    user_by_email = var.sa_dbt_email
  }
  access {
    role = "OWNER"
    special_group = "projectOwners"
  }
}
