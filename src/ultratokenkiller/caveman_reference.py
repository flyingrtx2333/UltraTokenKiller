"""Verify UTK response-policy coverage against the fixed Caveman skill."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .engines import response_instruction
from .reference_runner import _git_head, _lock


ACTIVE_MODES = (
    "lite",
    "full",
    "ultra",
    "wenyan-lite",
    "wenyan-full",
    "wenyan-ultra",
)

RULES = (
    {
        "id": "facts-and-errors",
        "upstream": ("Technical terms exact.", "Code blocks unchanged.", "Errors quoted exact."),
        "utk": ("technical terms", "code blocks", "exact error strings"),
    },
    {
        "id": "negations-and-numbers",
        "upstream": ("Never drop not/never/no/only/except", "Numbers, units exact."),
        "utk": ("negations", "numbers", "units"),
    },
    {
        "id": "language-preservation",
        "upstream": ("preserve the user's dominant language",),
        "utk": ("Keep the user's language.",),
    },
    {
        "id": "safety-clarity",
        "upstream": ("Security warnings", "Irreversible action confirmations"),
        "utk": ("security warnings", "irreversible actions"),
    },
    {
        "id": "detail-override",
        "upstream": ("User asks to clarify or repeats question",),
        "utk": ("Follow explicit requests for detailed explanations.",),
    },
    {
        "id": "no-invented-abbreviations",
        "upstream": ("never invent new abbreviations", "No causal arrows"),
        "utk": ("Never invent prose abbreviations", "causal arrows"),
    },
    {
        "id": "never-grow",
        "upstream": ("Compression only style never grow output.",),
        "utk": ("must never make the answer longer.",),
    },
)


def compare_caveman_policy(skill_text: str) -> dict[str, Any]:
    mode_results = []
    for mode in ACTIVE_MODES:
        instruction = response_instruction(mode)
        mode_results.append(
            {
                "mode": mode,
                "upstream_declared": f"**{mode}**" in skill_text or f"`{mode}`" in skill_text,
                "utk_instruction_present": bool(instruction),
                "instruction_sha256": hashlib.sha256(instruction.encode("utf-8")).hexdigest(),
            }
        )
    rule_results = []
    combined = "\n".join(response_instruction(mode) for mode in ACTIVE_MODES)
    for rule in RULES:
        rule_results.append(
            {
                "id": rule["id"],
                "upstream_present": all(value in skill_text for value in rule["upstream"]),
                "utk_present": all(value in combined for value in rule["utk"]),
            }
        )
    off_instruction = response_instruction("off")
    passed = (
        all(item["upstream_declared"] and item["utk_instruction_present"] for item in mode_results)
        and all(item["upstream_present"] and item["utk_present"] for item in rule_results)
        and off_instruction == ""
    )
    return {
        "active_modes": mode_results,
        "off_is_noop": off_instruction == "",
        "rules": rule_results,
        "policy_contract_passed": passed,
        "paired_output_quality_passed": False,
        "live_model_calls": 0,
    }


def generate_caveman_reference(checkout: Path, output: Path) -> dict[str, Any]:
    checkout, output = Path(checkout).resolve(), Path(output)
    expected = _lock()["caveman"]["commit"]
    head = _git_head(checkout)
    if head != expected:
        raise ValueError(f"caveman checkout is {head}, expected frozen commit {expected}")
    candidates = (
        checkout / "plugins" / "caveman" / "skills" / "caveman" / "SKILL.md",
        checkout / "skills" / "caveman" / "SKILL.md",
    )
    skill = next((path for path in candidates if path.is_file()), None)
    if skill is None:
        raise ValueError("Frozen Caveman skill file is missing")
    source = skill.read_text(encoding="utf-8")
    result = {
        "schema_version": 1,
        "baseline": expected,
        "kind": "utk-fixed-caveman-policy-reference",
        "source": skill.relative_to(checkout).as_posix(),
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        **compare_caveman_policy(source),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, output)
    return result
