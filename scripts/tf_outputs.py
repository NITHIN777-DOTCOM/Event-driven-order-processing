"""Read `terraform output -json` from infra/main so scripts never hard-code resource names/URLs."""

from __future__ import annotations

import json
import subprocess
from functools import lru_cache
from pathlib import Path

INFRA_MAIN = Path(__file__).resolve().parents[1] / "infra" / "main"


@lru_cache(maxsize=1)
def load_outputs() -> dict:
    """Return {output_name: value} for every Terraform output."""
    raw = subprocess.run(
        ["terraform", f"-chdir={INFRA_MAIN}", "output", "-json"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return {name: item["value"] for name, item in json.loads(raw).items()}
