"""Who is calling? Read ONLY from the JWT claims that API Gateway's authorizer already verified.

The HTTP API's JWT authorizer (infra/main/api.tf) checks the token's signature against the Cognito
user pool's keys, its issuer, its audience (one of our two app clients) and its expiry before the Lambda
runs. It then passes the claims in event.requestContext.authorizer.jwt.claims (all values as strings).

Identity never comes from the request body, query string or headers: a client can put anything there.
  userId = the "sub" claim  (Cognito's immutable user id; an email can change or be reused, sub can't)
  email  = the "email" claim, accepted only if "email_verified" is "true"
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class Unauthorized(Exception):
    """No usable identity in the request. Maps to HTTP 401."""


class Forbidden(Exception):
    """Signed in, but not allowed (e.g. the email isn't verified). Maps to HTTP 403."""


@dataclass(frozen=True)
class Caller:
    user_id: str  # Cognito "sub"
    email: str  # verified, lower-cased


def claims_from(event: dict[str, Any]) -> dict[str, Any]:
    return ((event.get("requestContext") or {}).get("authorizer") or {}).get("jwt", {}).get("claims") or {}


def caller_from(event: dict[str, Any]) -> Caller:
    """The verified caller, or raise Unauthorized / Forbidden."""
    claims = claims_from(event)
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        # Only reachable if a route were deployed without the authorizer: fail closed.
        raise Unauthorized("Sign in required")
    email = claims.get("email")
    if not isinstance(email, str) or not email:
        # An access token has no email claim; the API expects the ID token.
        raise Forbidden("Send the ID token: it must carry a verified email")
    if str(claims.get("email_verified", "")).lower() != "true":
        raise Forbidden("Verify your email address first")
    return Caller(user_id=sub, email=email.strip().lower())
