"""Tag values must pass the strictest AWS tag character set, checked before anything is deployed.

The plan-time check lives in infra/modules/tag_values (proven by its `terraform test`). These tests keep every tag
going through it: a Description tag written inline in either stack would bypass the validation, so it fails CI here.
The provider default_tags are checked directly.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

INFRA = Path(__file__).resolve().parents[2] / "infra"
INLINE_DESCRIPTION = re.compile(r'^\s*Description\s*=\s*"(.*)"\s*$', re.MULTILINE)
TAGS_FILE = INFRA / "main" / "tags.tf"


def allowed(value: str) -> bool:
    """Same rule as the module: letters, digits, spaces and _ . : = + - @ (Unicode letters/digits), max 256."""
    return len(value) <= 256 and all(ch.isalnum() or ch in " _.:=+@-" for ch in value)


@pytest.mark.parametrize("stack", ["main", "bootstrap"])
def test_no_inline_description_tags(stack):
    inline = [
        f"{path.name}: {match.group(1)}"
        for path in (INFRA / stack).glob("*.tf")
        if path != TAGS_FILE
        for match in INLINE_DESCRIPTION.finditer(path.read_text(encoding="utf-8"))
    ]
    assert inline == [], f'use module.tags.description["<key>"] instead of: {inline}'


def test_every_description_key_used_exists_in_tags_tf():
    defined = set(re.findall(r"^\s{4}(\w+)\s*=", TAGS_FILE.read_text(encoding="utf-8"), re.MULTILINE))
    used = {
        key
        for path in (INFRA / "main").glob("*.tf")
        for key in re.findall(r'module\.tags\.description\["(\w+)"\]', path.read_text(encoding="utf-8"))
    }
    assert used and used <= defined, f"undefined keys: {used - defined}"


def test_tag_values_use_the_strictest_character_set():
    values = re.findall(r'^\s{4}\w+\s*=\s*"(.*)"\s*$', TAGS_FILE.read_text(encoding="utf-8"), re.MULTILINE)
    assert values and [v for v in values if not allowed(v)] == []


def test_default_tags_use_the_strictest_character_set():
    block = re.search(r"default_tags\s*{\s*tags\s*=\s*{(.*?)}", (INFRA / "main" / "versions.tf").read_text(encoding="utf-8"), re.S)
    values = re.findall(r'=\s*"(.*?)"', block.group(1))
    assert values and all(allowed(v) for v in values)


@pytest.mark.parametrize("bad", ["wait (120 s timeout)", "orders/payments", "stock, reserved", "API · webhook", "x" * 257])
def test_the_rule_rejects_what_aws_rejected(bad):
    assert not allowed(bad)
