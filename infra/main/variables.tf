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

variable "chaos_enabled" {
  description = "Step 3.2 chaos switches (E3 crash-after-write): sets CHAOS_ENABLED on the saga Lambdas. Keep false; a chaos run flips it with -var chaos_enabled=true and flips it back"
  type        = bool
  default     = false
}
