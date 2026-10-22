# Progress

Use this to resume work in a new session. See CLAUDE.md for the full spec and the phase plan.

## Current phase
**Phase 0 — Foundation & bootstrap: DONE (2026-10-22).** Next: **Phase 1 — Core workflow.**

## Done
### Phase 0
- Environment verified: IAM user `order-saga-admin`, region `ap-south-1`, Terraform 1.16.6,
  local Python 3.11.9 (accepted; the Lambda runtime is python3.12), git, origin remote.
- Repo skeleton, .gitignore, README, requirements-dev.txt, CLAUDE.md.
- `infra/bootstrap` (LOCAL state, do not delete `infra/bootstrap/terraform.tfstate`):
  - S3 `order-saga-tfstate-876889172858`: versioning on, SSE-S3, public access blocked,
    TLS-only bucket policy, noncurrent versions expire after 30 days, `prevent_destroy`.
  - Budget `order-saga-monthly-budget`: 5 USD/month; emails at 50% and 80% ACTUAL, 100% FORECASTED.
- `infra/main` skeleton with an S3 backend (`main/terraform.tfstate`, `use_lockfile = true`);
  init, validate and plan succeed with no resources.

## Next (Phase 1)
- DynamoDB tables, SQS + DLQ, SNS topics, Lambdas, Step Functions saga, HTTP API.

## Blockers / notes
- None.
- `terraform.tfvars` files are gitignored; copy them from `*.tfvars.example` on a new machine.
- The bootstrap state is local only. If it's lost, re-import the bucket and budget rather than recreating them.
