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
  description = "Email subscribed to the SNS notification and ops-alert topics."
  type        = string
}
