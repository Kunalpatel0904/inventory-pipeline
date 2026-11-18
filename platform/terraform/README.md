# Terraform operations

The AWS and GCP environments intentionally keep provider resources separate.
Run commands from the selected environment:

```powershell
terraform fmt -check -recursive ..\..
terraform init
terraform validate
terraform plan -var='enable_expensive_resources=false'
```

The default plan creates only low-cost networking, registry, and identity
resources where applicable. EKS/GKE and managed PostgreSQL resources require
`enable_expensive_resources=true` and a sensitive database password. Do not run
`terraform apply` without explicit approval and a reviewed plan.

Configure remote state in the consuming environment rather than committing
credentials:

```hcl
# AWS backend example
terraform {
  backend "s3" {
    bucket         = "REPLACE_WITH_STATE_BUCKET"
    key            = "halcer/aws.tfstate"
    region         = "REPLACE_WITH_REGION"
    dynamodb_table = "REPLACE_WITH_LOCK_TABLE"
    encrypt        = true
  }
}
```

```hcl
# GCP backend example
terraform {
  backend "gcs" {
    bucket = "REPLACE_WITH_STATE_BUCKET"
    prefix = "halcer/gcp"
  }
}
```

The examples are deliberately not active backend configuration. Create the
provider APIs, state bucket, encryption, retention, and locking policy through
your organization’s approved process.
