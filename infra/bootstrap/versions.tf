# Bootstrap stack: creates the remote-state bucket and the budget alert.
# It uses LOCAL state on purpose (chicken-and-egg: the state bucket can't store its own state).
# The local terraform.tfstate in this folder must NOT be deleted.
terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region

  # Applied to every resource that supports tags.
  default_tags {
    tags = {
      Project   = "aws-order-saga"
      ManagedBy = "terraform"
    }
  }
}
