"""src/common/auth.py (which token, which claims) and the Cognito pre-token-generation trigger (step 2.0)."""

from __future__ import annotations

import importlib.util

import pytest

from common.auth import Forbidden, Unauthorized, caller_from
from conftest import EMAIL_A, SRC, USER_A, api_event, jwt_claims


# --- caller_from: identity only from verified claims --------------------------------------------


def test_access_token_with_verified_email_is_accepted():
    caller = caller_from(api_event(claims=jwt_claims(token_use="access")))

    assert (caller.user_id, caller.email) == (USER_A, EMAIL_A)


def test_email_is_normalised():
    assert caller_from(api_event(claims=jwt_claims(email="  Asha@Example.COM "))).email == EMAIL_A


@pytest.mark.parametrize(
    "claims",
    [
        jwt_claims(email=None),  # trigger added nothing (user without an email)
        jwt_claims(verified="false"),
        jwt_claims(verified=None),
    ],
)
def test_access_token_without_a_verified_email_is_forbidden(claims):
    with pytest.raises(Forbidden):
        caller_from(api_event(claims=claims))


@pytest.mark.parametrize("token_use", [None, "refresh", "ID", ""])
def test_unknown_token_use_is_unauthorized(token_use):
    claims = jwt_claims()
    claims["token_use"] = token_use
    with pytest.raises(Unauthorized):
        caller_from(api_event(claims=claims))


def test_id_token_is_still_accepted_during_the_rollout():
    assert caller_from(api_event(claims=jwt_claims(token_use="id"))).user_id == USER_A


def test_identity_ignores_headers_body_and_query():
    event = api_event(
        body={"userId": "someone-else", "email": "victim@example.com"},
        headers={"x-user-id": "someone-else", "x-email": "victim@example.com"},
        query={"email": "victim@example.com"},
    )
    assert caller_from(event) == caller_from(api_event())


@pytest.mark.parametrize("claims", [None, {}, {"email": EMAIL_A, "email_verified": "true", "token_use": "access"}])
def test_no_sub_is_unauthorized(claims):
    with pytest.raises(Unauthorized):
        caller_from(api_event(claims=claims))


# --- Cognito pre-token-generation trigger (V2_0) ------------------------------------------------


def trigger_event(attributes: dict, source: str = "TokenGeneration_Authentication") -> dict:
    """A trimmed V2_0 pre-token-generation event as Cognito sends it (attribute values are strings)."""
    return {
        "version": "2",
        "triggerSource": source,
        "region": "ap-south-1",
        "userPoolId": "ap-south-1_test",
        "userName": USER_A,
        "callerContext": {"awsSdkVersion": "aws-sdk-unknown", "clientId": "test-client"},
        "request": {
            "userAttributes": attributes,
            "groupConfiguration": {"groupsToOverride": [], "iamRolesToOverride": [], "preferredRole": None},
            "scopes": ["openid", "email", "profile"],
        },
        "response": {"claimsAndScopeOverrideDetails": None},
    }


@pytest.fixture
def trigger():
    # The trigger makes no AWS calls, so it needs no moto context (unlike conftest's load_handler).
    spec = importlib.util.spec_from_file_location("pre_token_handler", SRC / "lambdas" / "pre_token" / "handler.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("source", ["TokenGeneration_Authentication", "TokenGeneration_RefreshTokens"])
def test_trigger_adds_only_email_and_email_verified_to_the_access_token(trigger, source):
    attributes = {"sub": USER_A, "email": EMAIL_A, "email_verified": "true", "name": "Asha", "phone_number": "+910000000000"}

    result = trigger.lambda_handler(trigger_event(attributes, source), None)

    overrides = result["response"]["claimsAndScopeOverrideDetails"]
    assert overrides == {"accessTokenGeneration": {"claimsToAddOrOverride": {"email": EMAIL_A, "email_verified": True}}}
    assert "idTokenGeneration" not in overrides  # the ID token is left as Cognito builds it


def test_trigger_passes_an_unverified_email_through_as_false(trigger):
    result = trigger.lambda_handler(trigger_event({"email": EMAIL_A, "email_verified": "false"}), None)

    claims = result["response"]["claimsAndScopeOverrideDetails"]["accessTokenGeneration"]["claimsToAddOrOverride"]
    assert claims == {"email": EMAIL_A, "email_verified": False}


def test_trigger_adds_nothing_for_a_user_without_email(trigger):
    result = trigger.lambda_handler(trigger_event({"sub": USER_A}), None)

    assert result["response"]["claimsAndScopeOverrideDetails"] is None


def test_trigger_output_is_accepted_by_the_api(trigger):
    """End to end in miniature: the trigger's claims, stringified as API Gateway does, pass caller_from."""
    added = trigger.lambda_handler(trigger_event({"email": EMAIL_A, "email_verified": "true"}), None)[
        "response"
    ]["claimsAndScopeOverrideDetails"]["accessTokenGeneration"]["claimsToAddOrOverride"]
    claims = {"sub": USER_A, "token_use": "access", "client_id": "test-client", **{k: str(v).lower() for k, v in added.items()}}
    claims["email"] = added["email"]

    assert caller_from(api_event(claims=claims)).email == EMAIL_A


def test_trigger_never_logs_the_email(trigger, capsys):
    trigger.lambda_handler(trigger_event({"email": EMAIL_A, "email_verified": "true"}), None)

    assert EMAIL_A not in capsys.readouterr().out
