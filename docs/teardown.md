# Teardown: remove everything, safely, in order

> **Read-only document. Nothing here has been run.** Every step deletes data that cannot be recovered
> (orders, wallets, ledgers, Terraform state). Project rule: no destroy without the owner's explicit "DESTROY".

Region `ap-south-1`, account default CLI profile. Do the steps in this order: each one removes something a later
step would otherwise trip over.

## 0. Before you start
- Export anything you want to keep: `docs/evidence/` is already in git; screenshots of the console if needed.
- Make sure nothing is running: no k6 load test, no `scripts/chaos_run.py`, no open checkout holds you care about.
- Check `CHAOS_ENABLED` is `false` (`chaos_enabled` in `infra/main/terraform.tfvars`) and the chaos bucket holds no
  `faults/active.json`.

## 1. Stop new traffic (optional but tidy)
- Disable the GitHub `Deploy` workflow (Actions -> Deploy -> "Disable workflow"), so a push can't recreate resources
  mid-teardown.

## 2. Empty the two app buckets (Terraform will not delete a non-empty bucket: `force_destroy = false`)
- Storefront: `order-saga-frontend-<account id>`
- Chaos fault configuration: the `order-saga-*` chaos bucket (`terraform output` / `infra/main/chaos.tf`)

`aws s3 rm s3://<bucket> --recursive` for each (they are not versioned).

## 3. Turn off the guard on the Cognito user pool
`infra/main/auth.tf` sets `deletion_protection = "ACTIVE"` on `order-saga-users`. Change it to `"INACTIVE"` and
`terraform apply` in `infra/main` (one in-place change), otherwise the destroy stops at the user pool.

## 4. Destroy the app stack
```
cd infra/main
terraform plan -destroy          # read it: ~204 resources, all named order-saga-*
terraform destroy
```
This removes the API, Lambdas, Step Functions, DynamoDB tables (deletion protection is off), queues + DLQs,
the outbox pipe, SNS topics + subscriptions, Scheduler groups (with any leftover one-time hold schedules),
alarms, dashboard, log groups, CloudFront and the IAM roles.

## 5. Delete what scripts created outside Terraform
- SSM SecureStrings: `/order-saga/psp/webhook-secret` (scripts/create_webhook_secret.py) and
  `/order-saga/test-users/*` (create_test_users.py, oversell_race.py, the load-test buyers).
  `aws ssm get-parameters-by-path --path /order-saga --recursive --query "Parameters[].Name"` lists them; delete each
  with `aws ssm delete-parameter --name <name>`.
- Cognito users went with the user pool in step 4.

## 6. Destroy the bootstrap stack (state bucket, budget, GitHub OIDC roles) - last
The app stack's state lives in this bucket, so only after step 4.
1. In `infra/bootstrap/main.tf`, remove `prevent_destroy = true` from the state bucket.
2. The bucket is **versioned**: delete every object version and delete marker (console: "Empty" the bucket).
3. `cd infra/bootstrap && terraform destroy` (local state): OIDC provider, `order-saga-github-deploy-role`,
   `order-saga-github-plan-role`, the state bucket and the $5 budget.

## 7. Outside AWS
- GitHub repo variables `AWS_DEPLOY_ROLE_ARN`, `AWS_PLAN_ROLE_ARN`, `ALERT_EMAIL` (Settings -> Variables).
- Unsubscribe or ignore the SNS emails (the subscriptions are already gone after step 4).

## 8. Check nothing is left
- Resource Groups & Tag Editor: tag `Project = aws-order-saga`, all regions: expect nothing.
- CloudFront distributions list, S3 bucket list, `aws logs describe-log-groups --log-group-name-prefix /aws/lambda/order-saga`.
- Cost Explorer the next day: no `order-saga` usage.
