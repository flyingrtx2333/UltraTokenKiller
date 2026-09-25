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


def generate(root: Path, upstream: str | None = None) -> dict:
    data = root / "src" / "ultratokenkiller" / "data"
    inventory = json.loads((data / "full-parity-inventory.json").read_text(encoding="utf-8"))
    lock = json.loads((data / "upstream-lock.json").read_text(encoding="utf-8"))
    target = data / "full-parity-verification-ledger.json"
    previous = json.loads(target.read_text(encoding="utf-8")) if upstream else None
    items = dict(previous["items"]) if previous else {}
    for item in inventory["items"]:
        if upstream and item["upstream"] != upstream:
            continue
        fingerprint = _full_item_fingerprint(root, item, lock[item["upstream"]]["commit"])
        records = _evidence_records(root, item.get("parity_evidence", []))
        items[item["id"]] = {
            "source_fingerprint": fingerprint,
            "evidence_hashes": {
                record["reference"]: record["sha256"]
                for record in records if record["present"]
            },
        }
    if upstream:
        return {
            **previous,
            "items": items,
            "last_scoped_refresh": {
                "upstream": upstream,
                "at": datetime.now(timezone.utc).isoformat(),
            },
        }
    return {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "items": items}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--upstream", choices=("headroom", "rtk", "caveman"),
                        help="Refresh only this upstream and preserve other evidence bindings")
    args = parser.parse_args()
    root = args.root.resolve()
    target = root / "src" / "ultratokenkiller" / "data" / "full-parity-verification-ledger.json"
    payload = generate(root, upstream=args.upstream)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
