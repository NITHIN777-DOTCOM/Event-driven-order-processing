output "state_bucket_name" {
  description = "S3 bucket that holds remote Terraform state for infra/main."
  value       = aws_s3_bucket.tfstate.bucket
}

output "budget_name" {
  description = "Name of the monthly cost budget."
  value       = aws_budgets_budget.monthly.name
}
