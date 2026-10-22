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

  # Every taggable resource gets these tags automatically.
  default_tags {
    tags = {
      Project   = "aws-order-saga"
      ManagedBy = "terraform"
    }
  }
}
