terraform {
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

# --- 0. Project Services (APIs) ---
resource "google_project_service" "enabled_services" {
  for_each = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "iam.googleapis.com",
    "bigquery.googleapis.com"
  ])
  project = var.project_id
  service = each.key
  disable_on_destroy = false
}

# --- 1. Cloud Storage Buckets ---

# Raw data upload bucket
resource "google_storage_bucket" "finance_raw" {
  name          = "${var.project_id}-raw-uploads"
  location      = var.region
  force_destroy = false
  uniform_bucket_level_access = true
  depends_on = [google_project_service.enabled_services]
}

# Processed data / internal bucket (if needed for temp files)
resource "google_storage_bucket" "finance_internal" {
  name          = "${var.project_id}-internal"
  location      = var.region
  force_destroy = false
  uniform_bucket_level_access = true
  depends_on = [google_project_service.enabled_services]
}


# --- 2. Firestore (Native Mode) ---
# Note: Firestore database creation often requires App Engine enablement or specific handling.
# Using 'google_firestore_database' resource.

resource "google_firestore_database" "database" {
  name                              = "(default)"
  location_id                       = var.region
  type                              = "FIRESTORE_NATIVE"
  concurrency_mode                  = "OPTIMISTIC"
  app_engine_integration_mode       = "DISABLED"
  depends_on = [google_project_service.enabled_services]
}

# --- 3. BigQuery ---

resource "google_bigquery_dataset" "finance_analytics" {
  dataset_id                  = "finance_analytics"
  friendly_name               = "Finance Analytics"
  description                 = "Bronze, Silver and Gold layers for Finance App"
  location                    = var.region
  depends_on = [google_project_service.enabled_services]
}

# Silver Table: Transaction Log
resource "google_bigquery_table" "transactions_silver" {
  dataset_id = google_bigquery_dataset.finance_analytics.dataset_id
  table_id   = "transactions_silver"

  schema = <<EOF
[
  {
    "name": "id",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "MD5 Hash ID"
  },
  {
    "name": "date",
    "type": "DATE",
    "mode": "REQUIRED"
  },
  {
    "name": "month_ref",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "YYYY-MM Reference"
  },
  {
    "name": "amount",
    "type": "FLOAT",
    "mode": "REQUIRED"
  },
  {
    "name": "merchant_raw",
    "type": "STRING",
    "mode": "NULLABLE"
  },
  {
    "name": "merchant_clean",
    "type": "STRING",
    "mode": "NULLABLE"
  },
  {
    "name": "owner",
    "type": "STRING",
    "mode": "REQUIRED"
  },
  {
    "name": "source_file",
    "type": "STRING",
    "mode": "NULLABLE"
  },
  {
    "name": "created_at",
    "type": "TIMESTAMP",
    "mode": "NULLABLE"
  }
]
EOF
}

# Gold Table: Enriched Data
resource "google_bigquery_table" "finance_gold" {
  dataset_id = google_bigquery_dataset.finance_analytics.dataset_id
  table_id   = "finance_gold"

  schema = <<EOF
[
  {
    "name": "id",
    "type": "STRING",
    "mode": "REQUIRED"
  },
  {
    "name": "date",
    "type": "DATE",
    "mode": "REQUIRED"
  },
  {
    "name": "month_ref",
    "type": "STRING",
    "mode": "REQUIRED"
  },
  {
    "name": "amount",
    "type": "FLOAT",
    "mode": "REQUIRED"
  },
  {
    "name": "merchant_clean",
    "type": "STRING",
    "mode": "NULLABLE"
  },
  {
    "name": "category",
    "type": "STRING",
    "mode": "NULLABLE"
  },
  {
    "name": "subcategory",
    "type": "STRING",
    "mode": "NULLABLE"
  },
  {
    "name": "type",
    "type": "STRING",
    "mode": "NULLABLE",
    "description": "Individual/Compartilhado"
  },
  {
    "name": "owner",
    "type": "STRING",
    "mode": "REQUIRED"
  },
  {
    "name": "created_at",
    "type": "TIMESTAMP",
    "mode": "NULLABLE"
  }
]
EOF
}

# --- 4. Artifact Registry ---
resource "google_artifact_registry_repository" "finance_repo" {
  location      = var.region
  repository_id = "finance-repo"
  description   = "Docker Docker repository for Finance App services"
  format        = "DOCKER"
  depends_on = [google_project_service.enabled_services]
}

# --- 5. Service Accounts ---

# Service Account for the Backend API
resource "google_service_account" "backend_sa" {
  account_id   = "finance-backend-sa"
  display_name = "Finance Backend Service Account"
}

# IAM Bindings (Minimal Privilege Principle)
# 1. Access to Buckets
resource "google_storage_bucket_iam_member" "backend_raw_access" {
  bucket = google_storage_bucket.finance_raw.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.backend_sa.email}"
}

# 2. Access to Firestore
resource "google_project_iam_member" "backend_firestore_access" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.backend_sa.email}"
}

# 3. Access to BigQuery Data
resource "google_bigquery_dataset_access" "backend_bq_access" {
  dataset_id    = google_bigquery_dataset.finance_analytics.dataset_id
  role          = "WRITER"
  user_by_email = google_service_account.backend_sa.email
}

# 4. Permission to run BigQuery Jobs (queries)
resource "google_project_iam_member" "backend_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.backend_sa.email}"
}

# --- 6. Cloud Run (Backend) ---
resource "google_cloud_run_v2_service" "backend" {
  name     = "finance-backend"
  location = var.region
  ingress = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.backend_sa.email
    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.finance_repo.name}/backend:latest"
      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "USE_SQLITE"
        value = "false" # Cloud mode
      }
    }
  }
  depends_on = [google_project_service.enabled_services]
}

# Make Backend Publicly Accessible
resource "google_cloud_run_service_iam_member" "public_backend" {
  location = google_cloud_run_v2_service.backend.location
  service  = google_cloud_run_v2_service.backend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

output "backend_url" {
  value = google_cloud_run_v2_service.backend.uri
}

# --- 7. Cloud Run (Frontend) ---
resource "google_cloud_run_v2_service" "frontend" {
  name     = "finance-frontend"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.finance_repo.name}/frontend:latest"
      # NEXT_PUBLIC_API_URL is baked in, so no env needed here, but good practice to keep other envs if needed
      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }
    }
  }
  depends_on = [google_project_service.enabled_services]
}

# Make Frontend Publicly Accessible
resource "google_cloud_run_service_iam_member" "public_frontend" {
  location = google_cloud_run_v2_service.frontend.location
  service  = google_cloud_run_v2_service.frontend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

output "frontend_url" {
  value = google_cloud_run_v2_service.frontend.uri
}
