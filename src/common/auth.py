"""Who is calling? Read ONLY from the JWT claims that API Gateway's authorizer already verified.

The HTTP API's JWT authorizer (infra/main/api.tf) checks the token's signature against the Cognito
user pool's keys, its issuer, its audience (one of our two app clients) and its expiry before the Lambda
runs. It then passes the claims in event.requestContext.authorizer.jwt.claims (all values as strings).

Identity never comes from the request body, query string or headers: a client can put anything there.
  userId = the "sub" claim  (Cognito's immutable user id; an email can change or be reused, sub can't)
  email  = the "email" claim, accepted only if "email_verified" is "true"

Which token? (step 2.0) Only the ACCESS token. OAuth issues the access token for calling APIs; the ID token
tells the client app who signed in and is not meant to be sent to an API. Both are signed by the same pool and
both pass API Gateway's JWT authorizer (it checks "aud" on ID tokens and "client_id" on access tokens), so the
"token_use" claim is what tells them apart: an ID token is answered with 401.
Cognito's access tokens don't normally carry the email; the pre-token-generation trigger (src/lambdas/pre_token)
adds email + email_verified to them.
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
    if claims.get("token_use") == "id":
        raise Unauthorized("ID tokens are not accepted: send the access token in the Authorization header")
    if claims.get("token_use") != "access":
        raise Unauthorized("Send a Cognito access token in the Authorization header")
    email = claims.get("email")
    if not isinstance(email, str) or not email:
        # The pre-token trigger adds the email to every access token of a user who has one.
        raise Forbidden("The token carries no email address")
    if str(claims.get("email_verified", "")).lower() != "true":
        raise Forbidden("Verify your email address first")
    return Caller(user_id=sub, email=email.strip().lower())
