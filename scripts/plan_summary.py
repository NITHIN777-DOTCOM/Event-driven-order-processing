"""Turn `terraform show -json tfplan` into a short Markdown summary for a pull-request comment.

    terraform -chdir=infra/main show -json tfplan > plan.json
    python scripts/plan_summary.py plan.json > plan-summary.md

The output starts with a hidden marker, so the CI job can update its previous comment instead of
adding a new one on every push.
"""

from __future__ import annotations

import json
import sys
from collections import Counter

MARKER = "<!-- order-saga-terraform-plan -->"
MAX_LISTED = 60

# Terraform action lists -> one label each
LABELS = {
    ("create",): "create",
    ("update",): "update",
    ("delete",): "destroy",
    ("delete", "create"): "replace",
    ("create", "delete"): "replace",
}
ICONS = {"create": "+", "update": "~", "destroy": "-", "replace": "-/+"}


def summarize(plan: dict) -> str:
    changes = [
        (LABELS[tuple(rc["change"]["actions"])], rc["address"])
        for rc in plan.get("resource_changes", [])
        if tuple(rc["change"]["actions"]) in LABELS
    ]
    counts = Counter(label for label, _ in changes)
    add = counts["create"] + counts["replace"]
    destroy = counts["destroy"] + counts["replace"]

    lines = [
        MARKER,
        "### Terraform plan · `infra/main`",
        "",
        f"**Plan: {add} to add, {counts['update']} to change, {destroy} to destroy.**",
        "",
    ]
    if not changes:
        lines.append("No changes. The infrastructure already matches this branch.")
    else:
        if destroy:
            lines += ["> ⚠️ This plan **destroys or replaces** resources. Review carefully before merging.", ""]
        lines += ["<details><summary>Resources</summary>", "", "```diff"]
        lines += [f"{ICONS[label]} {address}  ({label})" for label, address in sorted(changes, key=lambda c: c[1])[:MAX_LISTED]]
        if len(changes) > MAX_LISTED:
            lines.append(f"  … and {len(changes) - MAX_LISTED} more")
        lines += ["```", "", "</details>"]
    lines += ["", "_Read-only plan made by GitHub Actions with the `order-saga-github-plan-role` (OIDC)._"]
    return "\n".join(lines) + "\n"


def main() -> None:
    with open(sys.argv[1], encoding="utf-8") as handle:
        sys.stdout.write(summarize(json.load(handle)))


if __name__ == "__main__":
    main()
