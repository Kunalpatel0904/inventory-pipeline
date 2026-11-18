module "platform" {
  source                     = "../../modules/aws"
  project_name               = var.project_name
  region                     = var.region
  enable_expensive_resources = var.enable_expensive_resources
  db_username                = var.db_username
  db_password                = var.db_password
}
variable "project_name" {
  type    = string
  default = "halcer-ideas"
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "enable_expensive_resources" {
  type    = bool
  default = false
}

variable "db_username" {
  type    = string
  default = "ideas"
}

variable "db_password" {
  type      = string
  sensitive = true
  nullable  = true
  default   = null
}
