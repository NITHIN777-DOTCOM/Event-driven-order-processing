"""Read a SecureString from SSM Parameter Store, cached in memory per Lambda container.

The webhook secret lives only in SSM (created by scripts/create_webhook_secret.py), never in Terraform state,
environment variables or logs. Each container fetches it once and keeps it for CACHE_SECONDS, so a warm
invocation costs no SSM call, and a rotated secret is picked up within 5 minutes.
"""

from __future__ import annotations

import time

import boto3

CACHE_SECONDS = 300

_ssm = None
_cache: dict[str, tuple[str, float]] = {}


def get_secret(name: str) -> str:
    """The decrypted value of SecureString `name`. Never log it."""
    global _ssm
    cached = _cache.get(name)
    if cached and time.monotonic() - cached[1] < CACHE_SECONDS:
        return cached[0]
    if _ssm is None:
        _ssm = boto3.client("ssm")
    value = _ssm.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]
    _cache[name] = (value, time.monotonic())
    return value


def clear_cache() -> None:
    """For tests."""
    global _ssm
    _ssm = None
    _cache.clear()
