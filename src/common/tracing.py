"""X-Ray instrumentation for AWS SDK calls.

Active tracing on its own only records each Lambda invocation as a whole. Patching botocore
records every call a handler makes (DynamoDB, SQS, Step Functions) as a subsegment. Those calls
then appear as separate nodes on the X-Ray service map, each with its own latency and error rate.

aws-xray-sdk comes from the AWS-managed "Powertools for AWS Lambda (Python)" layer attached by
Terraform, so nothing needs vendoring and there's no Docker build step. In local unit tests the
SDK isn't installed, and this becomes a no-op.
"""

from __future__ import annotations

_instrumented = False


def instrument_aws_sdk() -> None:
    """Patch botocore for X-Ray once per Lambda container. Call before making AWS calls."""
    global _instrumented
    if _instrumented:
        return
    try:
        from aws_xray_sdk.core import patch
    except ImportError:  # local tests: the layer isn't present
        return
    patch(["botocore"])
    _instrumented = True
