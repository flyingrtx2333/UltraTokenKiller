"""Refresh source and evidence bindings for the frozen 256-item inventory."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from ultratokenkiller.capabilities import (
    _evidence_records,
    _full_item_fingerprint,
)


def generate(root: Path) -> dict:
    data = root / "src" / "ultratokenkiller" / "data"
    inventory = json.loads((data / "full-parity-inventory.json").read_text(encoding="utf-8"))
    lock = json.loads((data / "upstream-lock.json").read_text(encoding="utf-8"))
    items = {}
    for item in inventory["items"]:
        fingerprint = _full_item_fingerprint(root, item, lock[item["upstream"]]["commit"])
        records = _evidence_records(root, item.get("parity_evidence", []))
        items[item["id"]] = {
            "source_fingerprint": fingerprint,
            "evidence_hashes": {
                record["reference"]: record["sha256"]
                for record in records if record["present"]
            },
        }
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": items,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    target = root / "src" / "ultratokenkiller" / "data" / "full-parity-verification-ledger.json"
    payload = generate(root)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
