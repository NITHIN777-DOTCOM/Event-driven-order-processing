"""Cognito pre-token-generation trigger (event version V2_0): put the user's email in the ACCESS token.

Why: the API accepts access tokens (the token meant for calling APIs), but a Cognito access token normally
carries no email. The API needs the email to send order notifications and wants it verified, so this trigger
copies exactly two user attributes into the access token's claims, and nothing else:

    email           the user's email, as stored in the pool
    email_verified  true / false (a JSON boolean, the same type the ID token uses)

Cognito calls this function every time it issues tokens (sign-in, and every refresh), right before it signs
them. The claims we return are then part of the signed JWT, so API Gateway's JWT authorizer verifies them like
any other claim. The ID token is left exactly as Cognito builds it.

Cognito waits at most 5 seconds for this function; if it fails, the sign-in fails. So it is deliberately tiny:
no AWS calls, no SDK, only the event in and the event out.
"""

from __future__ import annotations

from typing import Any

from common.logger import get_logger

logger = get_logger("pre_token")


def access_token_claims(attributes: dict[str, str]) -> dict[str, Any]:
    """The claims to add to the access token: email + email_verified, or nothing if the user has no email."""
    email = attributes.get("email")
    if not email:
        return {}  # nothing to copy; the API will answer 403 and the user can fix their profile
    return {"email": email, "email_verified": str(attributes.get("email_verified", "")).lower() == "true"}


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    claims = access_token_claims(event.get("request", {}).get("userAttributes") or {})
    if claims:
        # V2_0 response shape. Only accessTokenGeneration: the ID token stays untouched.
        event.setdefault("response", {})["claimsAndScopeOverrideDetails"] = {
            "accessTokenGeneration": {"claimsToAddOrOverride": claims},
        }
    # No email in the logs: the user's sub (userName here) is enough to correlate.
    logger.info(
        "Access token claims set",
        triggerSource=event.get("triggerSource"),
        clientId=(event.get("callerContext") or {}).get("clientId"),
        userSub=event.get("userName"),
        claimsAdded=sorted(claims),
        emailVerified=claims.get("email_verified"),
    )
    return event
