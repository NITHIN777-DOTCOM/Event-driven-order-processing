# Validates tag values at PLAN time, before any resource is touched.
#
# Why: every AWS service validates tag values with its own character set, and a bad value fails only at APPLY,
# on that one resource, after Terraform may already have changed or deleted others (step 2.1: a "(" in the state
# machine's Description tag failed the deploy after the old payment Lambda was already deleted).
#
# The allowed set below is the strictest one across the services this project tags (the intersection):
#   letters, digits, spaces and  _ . : = + - @     (Step Functions rejects "/", which DynamoDB and S3 accept)
# and at most 256 characters. Anything else ( ( ) , / · ' " ; ! ? & ) fails `terraform plan`.
#
# Usage (infra/main/tags.tf): every Description tag comes from module.tags.description["<key>"].
# Proven by tests/tag_values.tftest.hcl (`terraform test`, no AWS access needed).

variable "descriptions" {
  description = "Description tag value for each resource, keyed by a short resource name"
  type        = map(string)

  validation {
    condition = alltrue([
      for value in values(var.descriptions) :
      length(value) <= 256 && can(regex("^[\\p{L}\\p{N} _.:=+@-]*$", value))
    ])
    error_message = "Invalid tag value(s): ${join(" | ", [for key, value in var.descriptions : "${key} = \"${value}\"" if !(length(value) <= 256 && can(regex("^[\\p{L}\\p{N} _.:=+@-]*$", value)))])}. Tag values may contain only letters, digits, spaces and _ . : = + - @ (max 256 characters): the strictest set across DynamoDB, Step Functions, SQS, SNS, S3 and CloudFront."
  }
}

output "description" {
  description = "The validated Description tag values (same keys as the input)"
  value       = var.descriptions
}
