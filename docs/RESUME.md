# Resume bullets: Event-Driven Order Processing on AWS

Every number is verified in this repo: 65 unit tests and 95% coverage (`pytest --cov=src`), 94 + 13 Terraform-managed
resources (`terraform state list`), 8/8 live e2e scenarios (`docs/evidence/e2e-failure-tests.md`), 10 Lambdas,
5 DynamoDB tables. Idle cost is about $0 because everything is pay-per-use. There are no load-test numbers yet.

**SDE-focused**
> Built an event-driven order saga on AWS (API Gateway, SQS, Step Functions, 10 Python Lambdas) with idempotency at 3 layers, retry with backoff and compensating refunds/stock release; verified by 65 unit tests (95% coverage) and 8/8 live failure-scenario tests.

**Cloud-focused**
> Designed and deployed a serverless order-processing platform (107 Terraform-managed resources, 5 DynamoDB tables, CloudFront + S3 storefront) with DLQ alarms, X-Ray and dashboards, and OIDC-based GitHub Actions CI/CD with no stored keys, at about $0 idle cost.

**One-liner**
> Serverless AWS order saga (Step Functions, SQS, DynamoDB, Lambda) with exactly-once payments, automatic refunds, and Terraform + OIDC CI/CD.

Link: https://github.com/NITHIN777-DOTCOM/Event-driven-order-processing · Live: https://dg38gx94mao9n.cloudfront.net
