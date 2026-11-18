terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "project_name" {
  type = string
}

variable "enable_expensive_resources" {
  type    = bool
  default = false
}

variable "db_password" {
  type      = string
  sensitive = true
  nullable  = true
  default   = null
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_compute_network" "main" {
  name                    = "${var.project_name}-network"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "main" {
  name          = "${var.project_name}-subnet"
  ip_cidr_range = "10.50.0.0/16"
  region        = var.region
  network       = google_compute_network.main.id
  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = "10.60.0.0/16"
  }
  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = "10.70.0.0/20"
  }
}

resource "google_artifact_registry_repository" "containers" {
  location      = var.region
  repository_id = var.project_name
  format        = "DOCKER"
}

resource "google_service_account" "workload" {
  account_id   = "${var.project_name}-workload"
  display_name = "Halcer workload identity service account"
}

resource "google_compute_firewall" "internal" {
  name    = "${var.project_name}-internal"
  network = google_compute_network.main.name
  allow {
    protocol = "tcp"
    ports    = ["8000", "5432"]
  }
  source_ranges = ["10.50.0.0/16"]
}

resource "google_container_cluster" "main" {
  count                    = var.enable_expensive_resources ? 1 : 0
  name                     = var.project_name
  location                 = var.region
  network                  = google_compute_network.main.name
  subnetwork               = google_compute_subnetwork.main.name
  remove_default_node_pool = true
  initial_node_count       = 1
  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }
}

resource "google_container_node_pool" "main" {
  count      = var.enable_expensive_resources ? 1 : 0
  name       = "${var.project_name}-nodes"
  location   = var.region
  cluster    = google_container_cluster.main[0].name
  node_count = 1
  node_config {
    machine_type    = "e2-small"
    service_account = google_service_account.workload.email
    oauth_scopes = [
      "https://www.googleapis.com/auth/devstorage.read_only",
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring",
      "https://www.googleapis.com/auth/servicecontrol",
      "https://www.googleapis.com/auth/service.management.readonly",
      "https://www.googleapis.com/auth/trace.append",
    ]
  }
}

resource "google_compute_global_address" "private_service_access" {
  count         = var.enable_expensive_resources ? 1 : 0
  name          = "${var.project_name}-private-db"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.main.id
}

resource "google_service_networking_connection" "private" {
  count                   = var.enable_expensive_resources ? 1 : 0
  network                 = google_compute_network.main.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_service_access[0].name]
}

resource "google_sql_database_instance" "main" {
  count               = var.enable_expensive_resources ? 1 : 0
  name                = var.project_name
  database_version    = "POSTGRES_16"
  region              = var.region
  deletion_protection = false
  depends_on          = [google_service_networking_connection.private]
  settings {
    tier              = "db-f1-micro"
    availability_type = "ZONAL"
    disk_type         = "PD_SSD"
    disk_size         = 20
    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.main.id
    }
  }
}

resource "google_sql_database" "ideas" {
  count    = var.enable_expensive_resources ? 1 : 0
  name     = "ideas"
  instance = google_sql_database_instance.main[0].name
}

resource "google_sql_user" "ideas" {
  count    = var.enable_expensive_resources ? 1 : 0
  name     = "ideas"
  instance = google_sql_database_instance.main[0].name
  password = var.db_password
  lifecycle {
    precondition {
      condition     = var.db_password != null
      error_message = "db_password must be supplied when GCP managed resources are enabled."
    }
  }
}

output "network" {
  value = google_compute_network.main.name
}

output "registry" {
  value = google_artifact_registry_repository.containers.name
}

output "gke_name" {
  value = var.enable_expensive_resources ? google_container_cluster.main[0].name : null
}

output "database_ip" {
  value     = var.enable_expensive_resources ? google_sql_database_instance.main[0].private_ip_address : null
  sensitive = true
}
