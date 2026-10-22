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
