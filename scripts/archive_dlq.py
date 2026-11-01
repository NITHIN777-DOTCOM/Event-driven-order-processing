"""Archive the dead-letter queues to a JSON file, and (separately) delete exactly the messages that were archived.

A DLQ should be empty: each poison message is inspected, archived, then removed (docs/runbooks/redrive-stuck-order.md).

    python scripts/archive_dlq.py --out docs/evidence/dlq-archive-2026-11-01.json           # export, deletes nothing
    python scripts/archive_dlq.py --delete-archived docs/evidence/dlq-archive-2026-11-01.json # delete those messages

Queues: order-saga-orders-dlq and order-saga-psp-dlq (Terraform outputs dlq_url, psp_dlq_url).

Export: a full sweep. Each receive hides what it returned (VisibilityTimeout HIDE_SECONDS), so the next receive can
only return messages not seen yet; at the end every message is made visible again at once. Each message is saved with
its body, all system attributes and all message attributes. The sweep stops when it has seen as many distinct
messages as the queue reports, or after 3 empty receives.

Delete: sweeps again and deletes ONLY messages whose MessageId is in the archive file, never PurgeQueue: a message
that arrived after the export is not in the file and stays (it is reported, not touched). A message's receipt
handle expires with its visibility timeout, which is why deletion re-receives instead of reusing export handles.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tf_outputs import load_outputs  # noqa: E402

HIDE_SECONDS = 120  # long enough for a full sweep of a few hundred messages
QUEUE_OUTPUTS = {"order-saga-orders-dlq": "dlq_url", "order-saga-psp-dlq": "psp_dlq_url"}

OUT = load_outputs()
sqs = boto3.client("sqs", region_name=OUT["region"])


def queue_count(url: str) -> int:
    attrs = sqs.get_queue_attributes(
        QueueUrl=url, AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"]
    )["Attributes"]
    return int(attrs["ApproximateNumberOfMessages"]) + int(attrs["ApproximateNumberOfMessagesNotVisible"])


def sweep(url: str, keep_ids: set[str] | None = None) -> tuple[list[dict], list[str]]:
    """Receive every message once. keep_ids=None: export mode (delete nothing). Otherwise: delete the messages whose
    MessageId is in keep_ids. Returns (messages seen, MessageIds deleted). Undeleted messages become visible again."""
    total = queue_count(url)
    seen: dict[str, dict] = {}
    handles: dict[str, str] = {}
    deleted: list[str] = []
    empty = 0
    try:
        while len(seen) < total and empty < 3:
            batch = sqs.receive_message(
                QueueUrl=url, MaxNumberOfMessages=10, VisibilityTimeout=HIDE_SECONDS, WaitTimeSeconds=2,
                AttributeNames=["All"], MessageAttributeNames=["All"],
            ).get("Messages", [])
            empty = 0 if batch else empty + 1
            for m in batch:
                seen[m["MessageId"]] = m
                if keep_ids is not None and m["MessageId"] in keep_ids:
                    sqs.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])
                    deleted.append(m["MessageId"])
                else:
                    handles[m["MessageId"]] = m["ReceiptHandle"]
    finally:
        rest = list(handles.values())
        for i in range(0, len(rest), 10):
            sqs.change_message_visibility_batch(
                QueueUrl=url, Entries=[{"Id": str(n), "ReceiptHandle": h, "VisibilityTimeout": 0} for n, h in enumerate(rest[i : i + 10])]
            )
    return list(seen.values()), deleted


def export(path: Path) -> None:
    archive = {"exportedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "region": OUT["region"], "queues": {}}
    for name, output in QUEUE_OUTPUTS.items():
        url = OUT[output]
        reported = queue_count(url)
        messages, _ = sweep(url)
        rows = []
        for m in messages:
            body = m["Body"]
            try:
                parsed = json.loads(body)
            except ValueError:
                parsed = None
            rows.append({
                "messageId": m["MessageId"], "md5OfBody": m["MD5OfBody"], "body": body, "bodyParsed": parsed,
                "attributes": m.get("Attributes", {}), "messageAttributes": m.get("MessageAttributes", {}),
            })
        rows.sort(key=lambda r: int(r["attributes"].get("SentTimestamp", 0)))
        archive["queues"][name] = {"url": url, "reportedCount": reported, "archivedCount": len(rows), "messages": rows}
        print(f"{name}: queue reports {reported}, archived {len(rows)}")
        if len(rows) != reported:
            raise SystemExit(f"{name}: archived {len(rows)} but the queue reports {reported}; not writing a partial archive")
    path.write_text(json.dumps(archive, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Archive written: {path}")


def delete_archived(path: Path) -> None:
    archive = json.loads(path.read_text(encoding="utf-8"))
    for name, queue in archive["queues"].items():
        ids = {m["messageId"] for m in queue["messages"]}
        seen, deleted = sweep(queue["url"], keep_ids=ids)
        not_archived = [m["MessageId"] for m in seen if m["MessageId"] not in ids]
        missing = ids - set(deleted)
        print(f"{name}: deleted {len(deleted)} of {len(ids)} archived; left untouched (not in the archive): "
              f"{len(not_archived)} {not_archived}; archived but not found: {len(missing)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--out", type=Path, help="export both DLQs to this JSON file (deletes nothing)")
    group.add_argument("--delete-archived", type=Path, help="delete exactly the messages listed in this archive file")
    args = parser.parse_args()
    if args.out:
        export(args.out)
    else:
        delete_archived(args.delete_archived)


if __name__ == "__main__":
    main()
