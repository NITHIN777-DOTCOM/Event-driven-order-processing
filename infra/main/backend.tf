# Remote state lives in the bucket created by infra/bootstrap.
# Backend blocks can't use variables, so the bucket name is a literal here.
# use_lockfile uses S3-native state locking (Terraform >= 1.10), so no DynamoDB lock table is needed.
terraform {
  backend "s3" {
    bucket       = "order-saga-tfstate-876889172858"
    key          = "main/terraform.tfstate"
    region       = "ap-south-1"
    encrypt      = true
    use_lockfile = true
  }
}
