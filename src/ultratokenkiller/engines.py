"""Original UTK compression rules. No external compression programs required."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path


def estimate_tokens(text: str) -> int:
    """UTF-8 byte heuristic, never provider usage or a billing measurement."""
    return (len(text.encode("utf-8")) + 3) // 4


def compact_repetitions(text: str, minimum: int = 4) -> str:
    """Collapse consecutive identical nonempty lines; preserve error diagnostics."""
    lines = text.splitlines(keepends=True)
    result: list[str] = []
    i = 0
    while i < len(lines):
        j = i + 1
        while j < len(lines) and lines[j] == lines[i]:
            j += 1
        line = lines[i]
        protected = re.search(r"error|fail|exception|traceback|fatal|warning", line, re.I)
        if j - i >= minimum and line.strip() and not protected:
            replacement = line.rstrip("\r\n") + f"\n[UTK: previous line repeated {j-i} times in total]\n"
            original = "".join(lines[i:j])
            result.append(replacement if len(replacement) < len(original) else original)
        else:
            result.extend(lines[i:j])
        i = j
    return "".join(result)


def compress_request(payload: dict, profile: str = "safe") -> tuple[dict, dict]:
    """Only older plain-text tool results; stable prefix and latest result untouched."""
    result = copy.deepcopy(payload)
    before = estimate_tokens(json.dumps(payload, ensure_ascii=False))
    changed = 0
    if profile != "off":
        items = result.get("messages", result.get("input", []))
        if isinstance(items, list):
            candidates = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                key = "content" if item.get("role") == "tool" else "output" if item.get("type") == "function_call_output" else None
                if key and isinstance(item.get(key), str):
                    candidates.append((item, key))
            for item, key in candidates[:-1]:
                value = item[key]
                # Structured JSON, code and patches require semantic preservation.
                if value.lstrip().startswith(("{", "[", "diff ", "@@", "```")):
                    continue
                compressed = compact_repetitions(value, 3 if profile == "aggressive" else 4)
                changed += compressed != value
                item[key] = compressed
    after = estimate_tokens(json.dumps(result, ensure_ascii=False))
    return result, {"estimated_input_before": before, "estimated_input_after": after,
                    "estimated_saved_tokens": max(0, before-after), "changed_tool_results": changed,
                    "estimator": "utf8_bytes_div_4"}


def supported_command(command: list[str]) -> bool:
    if not command or any(arg in {"|", "||", "&&", ";", ">", ">>", "<"} for arg in command):
        return False
    name = Path(command[0]).stem.lower()
    if name == "git":
        if command[1:] == ["status"]:
            return True
        # Do not alter patches, porcelain, binary data or machine-readable output.
        return len(command) > 1 and command[1] in {"status", "log", "show", "diff"} and any(
            arg in {"--stat", "--shortstat"} for arg in command[2:])
    return name in {"pytest", "rg", "grep"} and not any(
        arg in {"--json", "--null", "-0", "-z", "--null-data", "--junitxml"} or arg.startswith("--junitxml=") for arg in command[1:])


def compress_tool_output(command: list[str], text: str) -> str:
    if Path(command[0]).stem.lower() == "git" and command[1:] == ["status"]:
        # Only Git's known English instructional lines; retain all path/status lines.
        hints = ('  (use "git add ', '  (use "git restore ', '  (use "git reset ',
                 '  (use "git checkout ', '  (use "git commit ', '  (use "git push ',
                 '  (use "git pull ')
        text = "".join(line for line in text.splitlines(keepends=True) if not line.startswith(hints))
    return compact_repetitions(text)


def response_instruction(level: str) -> str:
    styles = {
        "off": "",
        "lite": (
            "Answer directly in concise complete sentences. Remove filler, hedging, pleasantries, "
            "and repeated conclusions. Keep articles and full sentences."
        ),
        "full": (
            "Lead with the result. Use compact sentences or clear fragments and only necessary "
            "evidence and actions. Remove filler, articles, and repetition. Do not narrate tool calls "
            "or add decorative tables or emoji."
        ),
        "ultra": (
            "Use the fewest words that fully answer. State each fact once. Omit conjunctions only "
            "when causality stays unambiguous. Never invent prose abbreviations or use causal arrows."
        ),
        "wenyan-lite": "以半文言简答，去客套、犹疑与复述，保留完整语法、事实与必要依据。",
        "wenyan-full": "以文言简答，省赘语，明因果与行动；勿因省字损准确。",
        "wenyan-ultra": "以极简文言答，事实仅述一次，存条件、否定与行动；难解术语用现代汉语。",
    }
    if level not in styles:
        raise ValueError("Unknown response style")
    if level == "off":
        return ""
    return styles[level] + (
        " Preserve correctness, uncertainty, risks, conditions, warnings, negations, identifiers, "
        "paths, numbers, units, technical terms, code blocks, API and CLI names, and exact error "
        "strings. Keep the user's language. Use complete unambiguous sentences for security warnings "
        "and irreversible actions. Follow explicit requests for detailed explanations. Compression "
        "must never make the answer longer."
    )


def apply_response_style(payload: dict, level: str, protocol: str = "openai") -> dict:
    instruction = response_instruction(level)
    if not instruction:
        return payload
    formatting = payload.get("response_format", payload.get("text", {}).get("format", {}) if isinstance(payload.get("text"), dict) else {})
    if isinstance(formatting, dict) and formatting.get("type") in {"json_schema", "json_object"}:
        return payload
    items = payload.get("messages", payload.get("input", []))
    last_user = next((item.get("content", "") for item in reversed(items) if isinstance(item, dict) and item.get("role") == "user"), "") if isinstance(items, list) else items
    if isinstance(last_user, str):
        if re.search(r"详细|逐步|完整解释|in detail|step.by.step|comprehensive", last_user, re.I):
            return payload
        if re.search(r"review|审查", last_user, re.I):
            instruction += " For reviews, include location, concrete failure and actionable correction for each finding."
        elif re.search(r"commit message|提交信息", last_user, re.I):
            instruction += " For commit messages, state the change and its intent precisely."
    instruction = "[UTK response policy]\n" + instruction
    result = copy.deepcopy(payload)
    if protocol == "anthropic":
        system = result.get("system", "")
        if isinstance(system, str) and "[UTK response policy]" not in system:
            result["system"] = (system+"\n\n"+instruction).strip()
        elif isinstance(system, list) and not any("[UTK response policy]" in str(item.get("text", "")) for item in system if isinstance(item, dict)):
            result["system"].append({"type": "text", "text": instruction})
    elif "messages" in result and isinstance(result["messages"], list):
        if not any("[UTK response policy]" in str(item.get("content", "")) for item in result["messages"] if isinstance(item, dict) and item.get("role") == "developer"):
            result["messages"].insert(0, {"role": "developer", "content": instruction})
    elif "input" in result:
        previous = result.get("instructions")
        if previous is None or isinstance(previous, str) and "[UTK response policy]" not in previous:
            result["instructions"] = ((previous or "") + "\n\n" + instruction).strip()
    return result
