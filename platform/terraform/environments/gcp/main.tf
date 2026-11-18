module "platform" {
  source                     = "../../modules/gcp"
  project_id                 = var.project_id
  project_name               = var.project_name
  region                     = var.region
  enable_expensive_resources = var.enable_expensive_resources
  db_password                = var.db_password
}
variable "project_id" {
  type = string
}

variable "project_name" {
  type    = string
  default = "halcer-ideas"
}

variable "region" {
  type    = string
  default = "us-central1"
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
