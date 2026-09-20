"""Run the offline suite and bind capability claims to exact source bytes."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ultratokenkiller.capabilities import _contract_fingerprint, _source_fingerprint  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path,
                        default=ROOT / "src" / "ultratokenkiller" / "data" / "verification-ledger.json")
    parser.add_argument("--skip-tests", action="store_true",
                        help="Only for reproducing a ledger after this exact suite already passed in the same run")
    arguments = parser.parse_args()

    command = [sys.executable, "-m", "pytest", "-q"]
    if not arguments.skip_tests:
        completed = subprocess.run(command, cwd=ROOT, check=False)
        if completed.returncode:
            return completed.returncode

    data = ROOT / "src" / "ultratokenkiller" / "data"
    manifest = json.loads((data / "capability-manifest.json").read_text(encoding="utf-8"))
    lock = json.loads((data / "upstream-lock.json").read_text(encoding="utf-8"))
    capabilities = {}
    for item in manifest:
        fingerprint = _source_fingerprint(ROOT, item, lock[item["upstream"]]["commit"])
        if fingerprint is not None and item["verification"] in {
            "offline_passed", "real_client_passed", "upstream_parity_passed"
        }:
            capabilities[item["id"]] = {
                "source_fingerprint": fingerprint,
                "offline_passed": True,
                "real_client_source_fingerprint": None,
                "upstream_source_fingerprint": None,
            }

    contracts = json.loads((data / "tool-contracts.json").read_text(encoding="utf-8"))
    command_contracts = {}
    for contract in contracts:
        fingerprint = _contract_fingerprint(ROOT, contract)
        if fingerprint is not None:
            command_contracts[contract["id"]] = {"source_fingerprint": fingerprint,
                                                  "offline_passed": True}

    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "suite_passed": True,
        "test_command": command,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "capabilities": capabilities,
        "command_contracts": command_contracts,
        "note": "Real-client and upstream states require separately source-bound evidence and are not inferred from offline tests.",
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(capabilities)} capability and {len(command_contracts)} command-contract results to {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
