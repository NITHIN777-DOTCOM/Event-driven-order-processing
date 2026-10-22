variable "region" {
  description = "AWS region for all project resources."
  type        = string
  default     = "ap-south-1"
}

variable "project_prefix" {
  description = "Prefix used in every resource name."
  type        = string
  default     = "order-saga"
}

variable "alert_email" {
  description = "Email address that receives budget alerts."
  type        = string
}

variable "monthly_budget_usd" {
  description = "Monthly cost budget in USD."
  type        = string
  default     = "5"
}

variable "github_repository" {
  description = "owner/repo allowed to assume the CI/CD roles (case-sensitive, as GitHub reports it)."
  type        = string
  default     = "NITHIN777-DOTCOM/Event-driven-order-processing"
}

variable "github_oidc_subject_prefix" {
  description = "Prefix of the GitHub OIDC 'sub' claim for this repo (immutable owner/repo IDs). See github_oidc.tf."
  type        = string
  default     = "repo:NITHIN777-DOTCOM@180836916/Event-driven-order-processing@1429553651"
}
