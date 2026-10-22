output "state_bucket_name" {
  description = "S3 bucket that holds remote Terraform state for infra/main."
  value       = aws_s3_bucket.tfstate.bucket
}

output "budget_name" {
  description = "Name of the monthly cost budget."
  value       = aws_budgets_budget.monthly.name
}

output "github_deploy_role_arn" {
  description = "Set as the GitHub repo variable AWS_DEPLOY_ROLE_ARN."
  value       = aws_iam_role.github_deploy.arn
}

output "github_plan_role_arn" {
  description = "Set as the GitHub repo variable AWS_PLAN_ROLE_ARN."
  value       = aws_iam_role.github_plan.arn
}
