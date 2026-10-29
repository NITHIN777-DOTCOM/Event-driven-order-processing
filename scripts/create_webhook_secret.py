"""Create the payment webhook's HMAC secret, if it doesn't exist yet.

    python scripts/create_webhook_secret.py

Idempotent: safe on every deploy (Deploy runs it before the smoke test). If the SSM SecureString
/order-saga/psp/webhook-secret exists, nothing changes; otherwise 32 random bytes (64 hex characters) are
generated and stored, encrypted with the AWS-managed aws/ssm key.

The secret is shared by DemoPay (signs callbacks) and payment_webhook (verifies them). It is never in Terraform
state, never in an environment variable, and never printed: this script only says whether it created one.
To rotate: delete the parameter and re-run (both Lambdas pick the new value up within 5 minutes; callbacks
signed with the old one in between are rejected and retried by DemoPay).
"""

from __future__ import annotations

import secrets

import boto3

from tf_outputs import load_outputs

PROJECT_TAGS = [{"Key": "Project", "Value": "aws-order-saga"}, {"Key": "ManagedBy", "Value": "create_webhook_secret.py"}]


def main() -> None:
    out = load_outputs()
    name = out["webhook_secret_parameter"]
    ssm = boto3.client("ssm", region_name=out["region"])
    try:
        ssm.get_parameter(Name=name)  # existence only: no decryption
        print(f"{name}: exists (unchanged)")
        return
    except ssm.exceptions.ParameterNotFound:
        pass
    ssm.put_parameter(
        Name=name,
        Description="HMAC-SHA256 secret for DemoPay -> POST /webhooks/payment callbacks (order-saga step 2.1)",
        Value=secrets.token_hex(32),
        Type="SecureString",
        Tags=PROJECT_TAGS,
    )
    print(f"{name}: created (SecureString, 256-bit random; value not shown)")


if __name__ == "__main__":
    main()
