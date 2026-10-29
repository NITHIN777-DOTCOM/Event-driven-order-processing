"""HMAC-SHA256 webhook signatures (the scheme Stripe and Razorpay use, simplified).

The payment provider signs every callback; our webhook recomputes the signature and compares.

    X-Timestamp: 1761730000                       (unix seconds, when the provider sent it)
    X-Signature: hex(HMAC_SHA256(secret, "<X-Timestamp>.<raw body>"))

Why each part matters:
  - HMAC with a shared secret: only someone holding the secret can produce a valid signature, so a caller on
    the internet can't fake "payment succeeded" (the webhook route has no JWT: it's server-to-server).
  - The RAW body, byte for byte: re-serialising parsed JSON can reorder keys or change spacing and break the
    signature, so we sign and verify the exact bytes that travelled.
  - The timestamp INSIDE the signed string, and a 5-minute window: a captured request can't be replayed later,
    and the timestamp can't be changed without breaking the signature.
  - hmac.compare_digest: constant-time comparison, so response timing doesn't reveal how many leading
    characters of a guessed signature were right.
"""

from __future__ import annotations

import hashlib
import hmac
import time

TOLERANCE_SECONDS = 300  # reject callbacks older (or further in the future) than 5 minutes


class SignatureError(Exception):
    """The request is not provably from the provider. Maps to HTTP 401. `reason` is safe to log."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def sign(secret: str, timestamp: str, body: bytes) -> str:
    """Hex HMAC-SHA256 of "<timestamp>.<body>"."""
    message = timestamp.encode() + b"." + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def signed_headers(secret: str, body: bytes, now: float | None = None) -> dict[str, str]:
    """The headers a sender attaches to `body`."""
    timestamp = str(int(time.time() if now is None else now))
    return {"X-Timestamp": timestamp, "X-Signature": sign(secret, timestamp, body)}


def verify(secret: str, timestamp: str | None, signature: str | None, body: bytes, now: float | None = None) -> None:
    """Raise SignatureError unless `signature` is valid for `body` and `timestamp` is within 5 minutes."""
    if not timestamp or not signature:
        raise SignatureError("missing X-Timestamp or X-Signature header")
    try:
        sent_at = int(timestamp)
    except ValueError:
        raise SignatureError("X-Timestamp is not a unix time") from None
    age = (time.time() if now is None else now) - sent_at
    if abs(age) > TOLERANCE_SECONDS:
        raise SignatureError(f"timestamp outside the {TOLERANCE_SECONDS} s window (age {int(age)} s)")
    expected = sign(secret, timestamp, body)
    if not hmac.compare_digest(expected, signature.strip().lower()):
        raise SignatureError("signature mismatch")
