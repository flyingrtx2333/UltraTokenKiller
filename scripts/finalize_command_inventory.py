"""Build the review denominator from the frozen RTK command registry."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "src" / "ultratokenkiller" / "data" / "upstream-lock.json"
INVENTORY_PATH = ROOT / "src" / "ultratokenkiller" / "data" / "command-inventory.json"
CONTRACTS_PATH = ROOT / "src" / "ultratokenkiller" / "data" / "tool-contracts.json"


def _kebab(value: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", value)
    return value.replace("_", "-").lower()


def _family(path: list[str]) -> str:
    command = path[0]
    groups = {
        "file_search": {"ls", "tree", "read", "smart", "find", "grep", "rg", "fd", "cat", "head", "tail", "json"},
        "git": {"git", "gh", "glab", "gt"},
        "javascript": {"npm", "npx", "pnpm", "yarn", "bun", "deno", "prisma", "vitest", "jest", "eslint", "prettier", "tsc"},
        "python": {"python", "pytest", "pip", "ruff", "mypy", "poetry", "uv"},
        "rust": {"cargo", "rustc"},
        "go": {"go", "gofmt"},
        "jvm": {"java", "mvn", "gradle", "sbt"},
        "dotnet": {"dotnet"},
        "cloud_infrastructure": {"docker", "compose", "kubectl", "oc", "aws", "terraform", "helm"},
        "data": {"psql", "mysql", "sqlite", "redis"},
    }
    return next((name for name, commands in groups.items() if command in commands), "general")


def _contract_ids(path: list[str], parameters: list[dict], contracts: list[dict]) -> list[str]:
    if any(parameter["role"] == "subcommand" for parameter in parameters):
        return []
    command = " ".join(path)
    matches = []
    for contract in contracts:
        for candidate in contract["commands"]:
            literal = " ".join(token for token in candidate.split() if not token.isupper())
            if command == literal:
                matches.append(contract["id"])
                break
    return sorted(set(matches))


def build_inventory(lock: dict, existing: list[dict], contracts: list[dict]) -> list[dict]:
    records: dict[tuple[str, str], dict] = {}
    enum_names: set[str] = set()
    for source in lock["rtk"]["sources"]:
        for variant in source.get("command_variants", []):
            key = (variant["enum"], variant["variant"])
            if key in records:
                raise ValueError(f"duplicate frozen RTK command variant: {key}")
            enum_names.add(variant["enum"])
            records[key] = {**variant, "source_path": source["path"], "source_url": source["url"]}

    parents: dict[str, list[tuple[str, str]]] = {}
    for (enum_name, variant_name), record in records.items():
        for argument in record["arguments"]:
            matches = [candidate for candidate in enum_names if candidate in argument["type"]]
            for child_enum in matches:
                parents.setdefault(child_enum, []).append((enum_name, variant_name))

    def command_path(enum_name: str, variant_name: str, seen: frozenset[str] = frozenset()) -> list[str]:
        if enum_name == "Commands":
            return [_kebab(variant_name)]
        if enum_name in seen or not parents.get(enum_name):
            base = re.sub(r"Commands?$", "", enum_name) or enum_name
            return [_kebab(base), _kebab(variant_name)]
        parent_enum, parent_variant = sorted(parents[enum_name])[0]
        return command_path(parent_enum, parent_variant, seen | {enum_name}) + [_kebab(variant_name)]

    previous = {item["id"]: item for item in existing}
    result: list[dict] = []
    commit = lock["rtk"]["commit"]
    for (enum_name, variant_name), record in sorted(records.items()):
        item_id = f"tools.{enum_name}.{variant_name}"
        old = previous.get(item_id, {})
        parameters = []
        for argument in record["arguments"]:
            child = next((name for name in enum_names if name in argument["type"]), None)
            parameters.append(
                {
                    "name": argument["name"],
                    "type": argument["type"],
                    "role": "subcommand" if child else "argument",
                    "required": not argument["type"].startswith("Option<"),
                }
            )
        path = command_path(enum_name, variant_name)
        contract_ids = _contract_ids(path, parameters, contracts)
        old_status = old.get("status", "unverified")
        status = "contract_mapped" if old_status == "unverified" and contract_ids else old_status
        result.append(
            {
                "id": item_id,
                "upstream": "rtk",
                "upstream_commit": commit,
                "source": record["source_path"],
                "source_url": f"{record['source_url']}#L{record['line']}",
                "source_line": record["line"],
                "command_path": path,
                "family": _family(path),
                "parameters": parameters,
                "output_formats": ["human_text"],
                "platforms": ["windows", "macos", "linux"],
                "disposition": "core",
                "input": old.get("input", variant_name),
                "behavior": old.get("behavior", "Match the frozen upstream command contract"),
                "exceptions": old.get("exceptions", "Unknown output formats pass through and remain unverified"),
                "status": status,
                "tests": old.get("tests", []),
                "contract_ids": contract_ids,
                "scope": "coverage_denominator",
            }
        )
    if len(result) != len(existing):
        raise ValueError(f"inventory changed from {len(existing)} to {len(result)} entries")
    return result


def main() -> None:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    existing = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    contracts = json.loads(CONTRACTS_PATH.read_text(encoding="utf-8"))
    inventory = build_inventory(lock, existing, contracts)
    INVENTORY_PATH.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(inventory)} frozen RTK command contracts to {INVENTORY_PATH}")


if __name__ == "__main__":
    main()
