# Phase 5 evidence: CI/CD with GitHub Actions + OIDC

Repo: https://github.com/NITHIN777-DOTCOM/Event-driven-order-processing (private) · 2026-10-22

## Roles (infra/bootstrap/github_oidc.tf)

| Role | ARN | Who may assume it (OIDC `sub`) |
|---|---|---|
| Deploy | `arn:aws:iam::876889172858:role/order-saga-github-deploy-role` | `repo:NITHIN777-DOTCOM@180836916/Event-driven-order-processing@1429553651:ref:refs/heads/main` |
| Plan | `arn:aws:iam::876889172858:role/order-saga-github-plan-role` | `repo:NITHIN777-DOTCOM@180836916/Event-driven-order-processing@1429553651:pull_request` |

Both roles: audience `sts.amazonaws.com`, max session 1 h, no stored keys. The deploy role is scoped to `order-saga-*`
resources, and it's explicitly denied any IAM action on the two CI roles, so it can't escalate its own privileges.

## Runs

| # | What | Result | Run |
|---|---|---|---|
| 1 | CI on main (workflows pushed) | ✅ success | https://github.com/NITHIN777-DOTCOM/Event-driven-order-processing/actions/runs/39788933269 |
| 2 | Deploy #1 | ❌ `Could not assume role with OIDC` (see below) | https://github.com/NITHIN777-DOTCOM/Event-driven-order-processing/actions/runs/39789175044 |
| 3 | CI on main (trust fix) | ✅ success | https://github.com/NITHIN777-DOTCOM/Event-driven-order-processing/actions/runs/39791046851 |
| 4 | Deploy #2 | ✅ plan "No changes", apply 0/0/0, smoke `ORD-20261022-79bff2ed` COMPLETED 4.4 s, 1 DEBIT | https://github.com/NITHIN777-DOTCOM/Event-driven-order-processing/actions/runs/39791148585 |
| 5 | PR #1 CI (incl. plan comment) | ✅ success; comment "Plan: 0 to add, 0 to change, 0 to destroy" | https://github.com/NITHIN777-DOTCOM/Event-driven-order-processing/actions/runs/39791571167 |
| 6 | CI on main after the merge | ✅ success | https://github.com/NITHIN777-DOTCOM/Event-driven-order-processing/actions/runs/39791901048 |
| 7 | Deploy after the merge | ✅ smoke `ORD-20261022-631bd265` COMPLETED 0.9 s, 1 DEBIT | https://github.com/NITHIN777-DOTCOM/Event-driven-order-processing/actions/runs/39792175943 |

Pull request: https://github.com/NITHIN777-DOTCOM/Event-driven-order-processing/pull/1 (merged).

## Deploy #1 failure: root cause

CloudTrail `AssumeRoleWithWebIdentity` → `AccessDenied` showed the token's subject:

```
repo:NITHIN777-DOTCOM@180836916/Event-driven-order-processing@1429553651:ref:refs/heads/main
```

The repo uses GitHub's **immutable OIDC subject** (`gh api repos/<owner>/<repo>/actions/oidc/customization/sub` →
`"use_immutable_subject": true`), which embeds the numeric owner and repo IDs. The first trust policy expected the
name-only `repo:NITHIN777-DOTCOM/Event-driven-order-processing:...`. The fix pins the ID-based prefix
(`var.github_oidc_subject_prefix`). That's stronger: a repo deleted and re-created with the same name gets new IDs.

## Deploy smoke test (from the job log of run 7)

```
PASS  storefront https://dg38gx94mao9n.cloudfront.net -> HTTP 200
PASS  config.json apiUrl matches the API (https://8kyxed1rec.execute-api.ap-south-1.amazonaws.com)
PASS  POST /orders -> HTTP 202
PASS  order ORD-20261022-631bd265 is COMPLETED after 0.9s (expected COMPLETED within 60s)
PASS  DemoPay ledger: 1 DEBIT for the order (expected exactly 1)
```

## Deployed change visible on the site

The live bundle `/assets/index-B9VoLY5-.js` contains "v1.1 · deployed by GitHub Actions":

![Live footer](phase5-live-footer.png)

Note: CI-built Lambda zips are byte-identical to the ones built on Windows (`.gitattributes` keeps LF line
endings), so CI's `terraform plan` reported "No changes" instead of redeploying every function.
