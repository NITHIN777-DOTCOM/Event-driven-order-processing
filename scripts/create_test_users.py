"""Create (or check) the two test users that scripts and CI sign in as.

    python scripts/create_test_users.py

Idempotent: safe to run on every deploy. For each user (a, b):
  - user exists AND its SSM parameter exists -> nothing to do
  - otherwise -> create the user if needed (email pre-verified, no invitation email), give it a new random
    permanent password, and store {email, password} as an SSM SecureString /order-saga/test-users/<label>
    (encrypted with the AWS-managed aws/ssm key).

Why not Terraform: a password set by Terraform would sit in plain text in the state file. Here it only
exists in this process's memory and in the SecureString. It is never printed.
"""

from __future__ import annotations

import json
import secrets
import string

import boto3

from auth_tokens import LABELS, parameter_name, test_user
from tf_outputs import load_outputs

EMAIL_TEMPLATE = "order-saga-test-{label}@example.com"  # example.com: reserved, never a real mailbox
PROJECT_TAGS = [{"Key": "Project", "Value": "aws-order-saga"}, {"Key": "ManagedBy", "Value": "create_test_users.py"}]


def new_password() -> str:
    """32 random characters that always meet the pool policy (upper, lower, digit, length >= 10)."""
    alphabet = string.ascii_letters + string.digits
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(32))
        if any(c.isupper() for c in password) and any(c.islower() for c in password) and any(c.isdigit() for c in password):
            return password


def parameter_exists(ssm, name: str) -> bool:
    try:
        ssm.get_parameter(Name=name)  # no decryption needed just to check existence
        return True
    except ssm.exceptions.ParameterNotFound:
        return False


def user_exists(cognito, pool_id: str, email: str) -> bool:
    try:
        cognito.admin_get_user(UserPoolId=pool_id, Username=email)
        return True
    except cognito.exceptions.UserNotFoundException:
        return False


def ensure_user(cognito, ssm, pool_id: str, label: str) -> str:
    email = EMAIL_TEMPLATE.format(label=label)
    name = parameter_name(label)
    exists = user_exists(cognito, pool_id, email)
    if exists and parameter_exists(ssm, name):
        return "exists"

    if not exists:
        cognito.admin_create_user(
            UserPoolId=pool_id,
            Username=email,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "name", "Value": f"Test User {label.upper()}"},
            ],
            MessageAction="SUPPRESS",  # no invitation email
        )
    password = new_password()
    cognito.admin_set_user_password(UserPoolId=pool_id, Username=email, Password=password, Permanent=True)
    value = json.dumps({"email": email, "password": password})
    # PutParameter can't tag and overwrite in one call: tag on first creation, overwrite afterwards.
    if parameter_exists(ssm, name):
        ssm.put_parameter(Name=name, Value=value, Type="SecureString", Overwrite=True)
    else:
        ssm.put_parameter(
            Name=name,
            Value=value,
            Type="SecureString",
            Description=f"Order Saga test user {label.upper()} (email + password) for scripts and CI",
            Tags=PROJECT_TAGS,
        )
    del password, value
    return "created" if not exists else "password reset (parameter was missing)"


def main() -> None:
    out = load_outputs()
    session = boto3.session.Session(region_name=out["region"])
    cognito, ssm = session.client("cognito-idp"), session.client("ssm")
    for label in LABELS:
        status = ensure_user(cognito, ssm, out["user_pool_id"], label)
        user = test_user(label)  # proves the stored credentials actually sign in
        print(f"test user {label}: {status}; sign-in OK as {user['email']} (sub {user['sub']})")


if __name__ == "__main__":
    main()
