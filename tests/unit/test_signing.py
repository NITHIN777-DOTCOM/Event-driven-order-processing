"""common/signing.py: HMAC-SHA256 over "<timestamp>.<raw body>", 5-minute window, constant-time compare."""

from __future__ import annotations

import pytest

from common.signing import SignatureError, sign, signed_headers, verify

SECRET = "s3cret"
BODY = b'{"type":"payment.succeeded","paymentIntentId":"PI-ORD-1","amount":"10.00"}'
NOW = 1_761_730_000


def headers(secret=SECRET, body=BODY, at=NOW):
    return signed_headers(secret, body, now=at)


def test_valid_signature_passes():
    h = headers()
    verify(SECRET, h["X-Timestamp"], h["X-Signature"], BODY, now=NOW + 10)


def test_signature_is_hmac_sha256_of_timestamp_dot_body():
    # Known-answer test: anyone can recompute it with `openssl dgst -sha256 -hmac s3cret`.
    import hashlib
    import hmac

    expected = hmac.new(b"s3cret", b"123." + BODY, hashlib.sha256).hexdigest()
    assert sign(SECRET, "123", BODY) == expected


@pytest.mark.parametrize(
    "secret, body, reason",
    [
        ("wrong-secret", BODY, "signature mismatch"),
        (SECRET, BODY.replace(b"10.00", b"1.00"), "signature mismatch"),  # tampered body, original signature
    ],
)
def test_wrong_secret_or_tampered_body_is_rejected(secret, body, reason):
    h = headers(secret=secret)
    with pytest.raises(SignatureError, match=reason):
        verify(SECRET, h["X-Timestamp"], h["X-Signature"], body, now=NOW)


def test_changing_the_timestamp_breaks_the_signature():
    h = headers()
    with pytest.raises(SignatureError, match="mismatch"):
        verify(SECRET, str(NOW + 1), h["X-Signature"], BODY, now=NOW)


@pytest.mark.parametrize("skew", [301, -301, 3600, -86400])
def test_stale_or_future_timestamps_are_rejected(skew):
    h = headers(at=NOW)
    with pytest.raises(SignatureError, match="window"):
        verify(SECRET, h["X-Timestamp"], h["X-Signature"], BODY, now=NOW + skew)


@pytest.mark.parametrize("skew", [300, -300, 0])
def test_edges_of_the_window_are_accepted(skew):
    h = headers(at=NOW)
    verify(SECRET, h["X-Timestamp"], h["X-Signature"], BODY, now=NOW + skew)


@pytest.mark.parametrize(
    "timestamp, signature, reason",
    [(None, "abc", "missing"), ("123", None, "missing"), ("", "", "missing"), ("yesterday", "abc", "unix time")],
)
def test_missing_or_malformed_headers_are_rejected(timestamp, signature, reason):
    with pytest.raises(SignatureError, match=reason):
        verify(SECRET, timestamp, signature, BODY, now=NOW)


def test_uppercase_hex_signature_is_accepted():
    h = headers()
    verify(SECRET, h["X-Timestamp"], h["X-Signature"].upper(), BODY, now=NOW)
