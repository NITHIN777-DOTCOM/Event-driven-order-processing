terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source = "hashicorp/aws"
      # 6.x is needed for aws_cognito_managed_login_branding (Cognito managed login, step 1.2).
      # Pinned to 6.68.x patches; .terraform.lock.hcl is committed with linux_amd64 (CI) + windows_amd64 hashes.
      version = "~> 6.68.0"
    }
    # Zips the Lambda source code; no Docker or build step needed.
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

provider "aws" {
  region = var.region

  # Every taggable resource gets these tags automatically.
  default_tags {
    tags = {
      Project   = "aws-order-saga"
      ManagedBy = "terraform"
    }
  }
}
