"""TransactWriteItems that retries TransactionConflict (step 3.1, found by the oversell race test).

DynamoDB runs transactions optimistically. When two transactions touch the same item at the same moment (hundreds of
buyers claiming the last units of one product), one of them is cancelled with the reason TransactionConflict for that
item. Nothing was written, and it does NOT mean a condition failed: the stock may well still be there. boto3 doesn't
retry it. Reading it as "out of stock", which every TransactionCanceledException used to mean on the stock paths,
turns a busy product into false "sold out" answers.

transact_write retries while any cancellation reason is TransactionConflict, with full-jitter exponential backoff. That
is safe because a cancelled transaction applied nothing and every caller's transaction is guarded by conditions, so a
re-run can never apply twice. Every other cancellation (ConditionalCheckFailed: really out of stock, the hold had
already ended, ...) is raised at once for the caller to interpret, exactly as before. fulfill_item and write_off_lines
have their own loops of the same kind (their conflicts are between lines of one order).
"""

from __future__ import annotations

import random
import time
from typing import Any

from botocore.exceptions import ClientError

from common.orders import cancellation_codes

# 150 buyers on one row (the race test's round 1) still left 1 in ~150 conflicting through 8 tries with a 0.4 s cap,
# so: 10 tries, waits from 50 ms capped at 1 s. At most ~5.6 s of waiting (typically ~2.8 s), well inside the 30 s
# Lambda and API timeouts.
CONFLICT_ATTEMPTS = 10
BACKOFF_BASE_S, BACKOFF_CAP_S = 0.05, 1.0


def is_conflict(err: ClientError) -> bool:
    """True if a transaction was cancelled (at least partly) because another one held one of its items."""
    return err.response["Error"]["Code"] == "TransactionCanceledException" and "TransactionConflict" in cancellation_codes(err.response)


def transact_write(ddb_client: Any, items: list[dict[str, Any]], log: Any = None) -> int:
    """Run the transaction; retry conflicts. Returns how many conflicts were retried. Raises the last error if the
    transaction still conflicts after CONFLICT_ATTEMPTS tries, or at once for any other error."""
    for attempt in range(CONFLICT_ATTEMPTS):
        try:
            ddb_client.transact_write_items(TransactItems=items)
            if attempt and log is not None:
                log.info("Transaction committed after conflicts", conflictRetries=attempt)
            return attempt
        except ClientError as err:
            if not is_conflict(err) or attempt == CONFLICT_ATTEMPTS - 1:
                raise
            time.sleep(random.uniform(0, min(BACKOFF_CAP_S, BACKOFF_BASE_S * 2**attempt)))
    raise AssertionError("unreachable")
