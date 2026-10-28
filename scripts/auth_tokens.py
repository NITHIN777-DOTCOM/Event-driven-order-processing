"""Sign in as a test user and return Cognito tokens, for every script that calls the API.

    from auth_tokens import auth_header, test_user
    http_json("GET", f"{api}/orders", headers=auth_header("a"))

How it works: the test users' credentials live in SSM Parameter Store as SecureStrings
(/order-saga/test-users/<label>, created by create_test_users.py). This module reads one with the
caller's AWS credentials and calls AdminInitiateAuth (ADMIN_USER_PASSWORD_AUTH) on the "automation"
app client. That flow is IAM-signed, so only principals allowed cognito-idp:AdminInitiateAuth can use it;
the browser client can't sign in with a password at all.

The password is held in memory only for that one call and is never printed or logged.
Tokens are cached per process and renewed 5 minutes before they expire (they last 60 minutes).
"""

from __future__ import annotations

import base64
import json
import time

import boto3

from tf_outputs import load_outputs

SSM_PREFIX = "/order-saga/test-users"
LABELS = ("a", "b")  # two users, so the scripts can prove one can't see the other's data
RENEW_BEFORE_S = 300

_cache: dict[str, dict] = {}


def parameter_name(label: str) -> str:
    return f"{SSM_PREFIX}/{label}"


def _claims(jwt: str) -> dict:
    """Decode a JWT's payload WITHOUT verifying it (we just received it from Cognito over TLS)."""
    payload = jwt.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def credentials(label: str) -> dict:
    """{email, password} from the SecureString. Callers must never print or log the password."""
    region = load_outputs()["region"]
    raw = boto3.client("ssm", region_name=region).get_parameter(Name=parameter_name(label), WithDecryption=True)
    return json.loads(raw["Parameter"]["Value"])


def _sign_in(label: str) -> dict:
    out = load_outputs()
    creds = credentials(label)
    result = boto3.client("cognito-idp", region_name=out["region"]).admin_initiate_auth(
        UserPoolId=out["user_pool_id"],
        ClientId=out["automation_client_id"],
        AuthFlow="ADMIN_USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": creds["email"], "PASSWORD": creds["password"]},
    )["AuthenticationResult"]
    del creds
    claims = _claims(result["IdToken"])
    return {
        "id_token": result["IdToken"],
        "access_token": result["AccessToken"],
        "sub": claims["sub"],
        "email": claims["email"],
        "expires_at": claims["exp"],
    }


def test_user(label: str = "a") -> dict:
    """{id_token, access_token, sub, email, expires_at} for test user `label` (signs in if needed)."""
    cached = _cache.get(label)
    if cached is None or cached["expires_at"] - time.time() < RENEW_BEFORE_S:
        _cache[label] = cached = _sign_in(label)
    return cached


def auth_header(label: str = "a") -> dict:
    """{"Authorization": "<ID token>"}. The API reads the user's id (sub) and verified email from the ID token."""
    return {"Authorization": test_user(label)["id_token"]}


if __name__ == "__main__":
    # Prints only non-secret facts, to check that sign-in works (e.g. in CI).
    for name in LABELS:
        user = test_user(name)
        print(f"user {name}: {user['email']}  sub={user['sub']}  token expires in {int(user['expires_at'] - time.time())} s")
