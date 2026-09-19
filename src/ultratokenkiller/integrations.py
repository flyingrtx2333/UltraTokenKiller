from __future__ import annotations

import base64
import json
import os
import re
import shutil
import time
from dataclasses import dataclass, asdict
from pathlib import Path

import yaml


START = "# >>> ultratokenkiller managed >>>"
END = "# <<< ultratokenkiller managed <<<"
HERMES_HOOK_START = "# >>> ultratokenkiller hermes hook >>>"
HERMES_HOOK_END = "# <<< ultratokenkiller hermes hook <<<"
HERMES_HOOK_COMMAND = "utk hermes-hook"
HERMES_ALLOWLIST = "shell-hooks-allowlist.json"


@dataclass
class ClientState:
    name: str
    detected: bool
    enabled: bool
    supported: bool
    detail: str
    config_path: str | None = None

    def json(self) -> dict:
        return asdict(self)


def _replace_block(text: str, block: str, *, prepend: bool = False) -> str:
    pattern = re.compile(rf"\n?{re.escape(START)}.*?{re.escape(END)}\n?", re.S)
    clean = pattern.sub("\n", text).rstrip()
    managed = f"{START}\n{block.rstrip()}\n{END}\n"
    if not clean:
        return managed
    return f"{managed}\n{clean}\n" if prepend else f"{clean}\n\n{managed}"


def _remove_block(text: str) -> str:
    pattern = re.compile(rf"\n?{re.escape(START)}.*?{re.escape(END)}\n?", re.S)
    match = pattern.search(text)
    clean = pattern.sub("\n", text).strip()
    previous: dict[str, str] = {}
    if match:
        encoded = re.search(r"^# utk-previous-root: ([A-Za-z0-9_=-]+)$", match.group(0), re.M)
        if encoded:
            try:
                previous = json.loads(base64.urlsafe_b64decode(encoded.group(1)).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                previous = {}
    root_text = clean.split("[", 1)[0]
    existing = {key for key in previous if re.search(rf"(?m)^\s*{re.escape(key)}\s*=", root_text)}
    restored = [line for key, line in previous.items() if key not in existing]
    prefix = "\n".join(restored)
    return ((prefix + "\n" if prefix else "") + clean).strip() + "\n"


def _take_root_assignments(text: str, keys: set[str]) -> tuple[str, dict[str, str]]:
    lines = text.splitlines()
    previous: dict[str, str] = {}
    output: list[str] = []
    in_root = True
    for line in lines:
        if line.lstrip().startswith("["):
            in_root = False
        match = re.match(r"^\s*([A-Za-z0-9_-]+)\s*=", line) if in_root else None
        if match and match.group(1) in keys:
            previous[match.group(1)] = line
        else:
            output.append(line)
    return "\n".join(output).strip() + "\n", previous


def _backup(path: Path, backup_root: Path) -> Path | None:
    if not path.exists():
        return None
    backup_root.mkdir(parents=True, exist_ok=True)
    target = backup_root / f"{path.name}.{int(time.time())}.bak"
    shutil.copy2(path, target)
    return target


class CodexAdapter:
    name = "codex"

    def __init__(self, root: Path | None = None):
        self.root = root or Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
        self.config = self.root / "config.toml"

    def detect(self) -> ClientState:
        detected = shutil.which("codex") is not None or self.root.exists()
        text = self.config.read_text(encoding="utf-8") if self.config.exists() else ""
        return ClientState(self.name, detected, START in text, detected, "Codex user configuration", str(self.config))

    def upstream_url(self) -> str:
        if self._uses_chatgpt_auth():
            return "https://chatgpt.com/backend-api/codex"
        if not self.config.exists():
            return "https://api.openai.com/v1"
        try:
            try:
                import tomllib
            except ImportError:
                import tomli as tomllib
            data = tomllib.loads(_remove_block(self.config.read_text(encoding="utf-8")))
            provider = data.get("model_provider")
            configured = data.get("model_providers", {}).get(provider, {}) if provider else {}
            return str(configured.get("base_url") or "https://api.openai.com/v1")
        except (OSError, ValueError, TypeError, AttributeError):
            return "https://api.openai.com/v1"

    def enable(self, proxy_port: int, backup_root: Path, caveman: str = "lite") -> ClientState:
        self.root.mkdir(parents=True, exist_ok=True)
        text = self.config.read_text(encoding="utf-8") if self.config.exists() else ""
        _backup(self.config, backup_root)
        text = _remove_block(text) if START in text else text
        developer_instruction = ""
        try:
            try:
                import tomllib
            except ImportError:
                import tomli as tomllib
            developer_instruction = str(tomllib.loads(text).get("developer_instructions") or "")
        except (ValueError, TypeError):
            pass
        text, previous = _take_root_assignments(text, {"model_provider", "developer_instructions"})
        chatgpt = self._uses_chatgpt_auth()
        auth = "requires_openai_auth = true\n" if chatgpt else ""
        concise = _caveman_instruction(caveman)
        combined_instruction = f"{developer_instruction}\n\n{concise}".strip()
        encoded_previous = base64.urlsafe_b64encode(json.dumps(previous).encode("utf-8")).decode("ascii")
        block = (
            f'# utk-previous-root: {encoded_previous}\n'
            'model_provider = "utk"\n'
            f'developer_instructions = {json.dumps(combined_instruction, ensure_ascii=False)}\n'
            '[model_providers.utk]\n'
            'name = "UltraTokenKiller"\n'
            f'base_url = "http://127.0.0.1:{proxy_port}/v1"\n'
            'wire_api = "responses"\n'
            'supports_websockets = false\n'
            f'{auth}'
        )
        self.config.write_text(_replace_block(text, block, prepend=True), encoding="utf-8")
        return self.detect()

    def disable(self) -> ClientState:
        if self.config.exists():
            self.config.write_text(_remove_block(self.config.read_text(encoding="utf-8")), encoding="utf-8")
        return self.detect()

    def _uses_chatgpt_auth(self) -> bool:
        auth = self.root / "auth.json"
        if not auth.exists():
            return False
        try:
            data = json.loads(auth.read_text(encoding="utf-8"))
            return data.get("auth_mode") == "chatgpt" or bool(data.get("tokens", {}).get("account_id"))
        except (ValueError, OSError, AttributeError):
            return False


class HermesAdapter:
    name = "hermes"

    def __init__(self, root: Path | None = None):
        self.root = root or Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
        self.config = self.root / "config.yaml"

    def detect(self) -> ClientState:
        detected = shutil.which("hermes") is not None or self.root.exists()
        text = self.config.read_text(encoding="utf-8") if self.config.exists() else ""
        supported = not bool(re.search(r"provider:\s*(anthropic|bedrock|vertex)", text, re.I))
        hook = HERMES_HOOK_START in text
        detail = ("OpenAI-compatible provider; managed tool hook " + ("enabled" if hook else "not enabled")) if supported else "Current provider is not OpenAI-compatible"
        return ClientState(self.name, detected, START in text, detected and supported, detail, str(self.config))

    def upstream_url(self) -> str | None:
        if not self.config.exists():
            return "https://api.openai.com/v1"
        text = _remove_hermes_block(self.config.read_text(encoding="utf-8"))
        base = re.search(r"(?m)^\s{2}base_url:\s*['\"]?([^'\"\s#]+)", text)
        if base:
            return base.group(1)
        provider = re.search(r"(?m)^\s{2}provider:\s*['\"]?([^'\"\s#]+)", text)
        name = provider.group(1).lower() if provider else "openai"
        return {
            "openai": "https://api.openai.com/v1",
            "openrouter": "https://openrouter.ai/api/v1",
        }.get(name)

    def enable(self, proxy_port: int, backup_root: Path, caveman: str = "lite") -> ClientState:
        state = self.detect()
        if not state.supported:
            return state
        self.root.mkdir(parents=True, exist_ok=True)
        text = self.config.read_text(encoding="utf-8") if self.config.exists() else ""
        _backup(self.config, backup_root)
        text = _remove_hermes_block(text) if START in text else text
        text = _remove_hermes_hook(text)
        managed = _add_hermes_hook(_add_hermes_block(text, proxy_port, caveman))
        _validate_hermes_config(managed)
        allowlist = self.root / HERMES_ALLOWLIST
        _backup(allowlist, backup_root)
        _approve_hermes_hook(allowlist)
        _atomic_write_text(self.config, managed)
        return self.detect()

    def disable(self) -> ClientState:
        if self.config.exists():
            text = _remove_hermes_hook(self.config.read_text(encoding="utf-8"))
            self.config.write_text(_remove_hermes_block(text), encoding="utf-8")
        _revoke_hermes_hook(self.root / HERMES_ALLOWLIST)
        return self.detect()


def _add_hermes_block(text: str, proxy_port: int, caveman: str) -> str:
    match = re.search(r"(?m)^model:\s*(?:#.*)?$", text)
    created = match is None
    if created:
        text = text.rstrip() + ("\n\n" if text.strip() else "") + "model:\n"
        match = re.search(r"(?m)^model:\s*$", text)
    assert match is not None
    next_root = re.search(r"(?m)^[A-Za-z0-9_-]+:\s*", text[match.end():])
    end = match.end() + (next_root.start() if next_root else len(text[match.end():]))
    section = text[match.end():end]
    previous: dict[str, str] = {}
    kept: list[str] = []
    for line in section.splitlines():
        child = re.match(r"^  (provider|base_url|coding_instructions):", line)
        if child:
            previous[child.group(1)] = line
        else:
            kept.append(line)
    state = base64.urlsafe_b64encode(json.dumps({"created": created, "previous": previous}).encode("utf-8")).decode("ascii")
    managed = [
        f"  {START}",
        f"  # utk-hermes-state: {state}",
        "  provider: custom",
        f"  base_url: http://127.0.0.1:{proxy_port}/v1",
        f"  coding_instructions: {json.dumps(_caveman_instruction(caveman), ensure_ascii=False)}",
        f"  {END}",
    ]
    new_section = "\n" + "\n".join(managed + [line for line in kept if line.strip()]) + "\n"
    return text[:match.end()] + new_section + text[end:].lstrip("\n")


def _remove_hermes_block(text: str) -> str:
    pattern = re.compile(rf"(?ms)^  {re.escape(START)}$.*?^  {re.escape(END)}\s*$")
    match = pattern.search(text)
    if not match:
        return text
    state_match = re.search(r"^  # utk-hermes-state: ([A-Za-z0-9_=-]+)$", match.group(0), re.M)
    state: dict = {}
    if state_match:
        try:
            state = json.loads(base64.urlsafe_b64decode(state_match.group(1)).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            state = {}
    previous = list(state.get("previous", {}).values())
    replacement = "\n" + "\n".join(previous) if previous else ""
    clean = pattern.sub(replacement, text)
    if state.get("created"):
        clean = re.sub(r"(?m)^model:\s*\n(?=\S|\Z)", "", clean)
    return clean.strip() + "\n"


def _add_hermes_hook(text: str) -> str:
    """Merge one managed pre-tool hook without replacing user hook entries."""
    if HERMES_HOOK_START in text:
        return text
    lines = text.splitlines()
    hooks = [i for i, line in enumerate(lines) if re.match(r"^hooks:\s*(?:#.*)?$", line)]
    if len(hooks) > 1:
        raise ValueError("Hermes config has multiple root hooks sections")
    command_lines = [
        '- matcher: "^(terminal|shell)$"',
        f'  command: "{HERMES_HOOK_COMMAND}"',
        "  timeout: 5",
        "  fail_closed: false",
    ]
    if not hooks:
        block = [HERMES_HOOK_START, "hooks:", "  pre_tool_call:"]
        block += ["    " + line for line in command_lines]
        block.append(HERMES_HOOK_END)
        return text.rstrip() + "\n\n" + "\n".join(block) + "\n"

    root = hooks[0]
    end = len(lines)
    for i in range(root + 1, len(lines)):
        line = lines[i]
        if line and not line[0].isspace() and not line.lstrip().startswith("#"):
            end = i
            break
    events = [i for i in range(root + 1, end) if re.match(r"^  pre_tool_call:\s*(?:#.*)?$", lines[i])]
    if len(events) > 1:
        raise ValueError("Hermes config has multiple pre_tool_call hook sections")
    if not events:
        block = ["  " + HERMES_HOOK_START, "  pre_tool_call:"]
        block += ["    " + line for line in command_lines]
        block.append("  " + HERMES_HOOK_END)
        lines[end:end] = block
    else:
        event = events[0]
        event_end = end
        for i in range(event + 1, end):
            if re.match(r"^  [A-Za-z0-9_-]+:\s*", lines[i]):
                event_end = i
                break
        block = ["    " + HERMES_HOOK_START]
        block += ["    " + line for line in command_lines]
        block.append("    " + HERMES_HOOK_END)
        lines[event_end:event_end] = block
    return "\n".join(lines).rstrip() + "\n"


def _remove_hermes_hook(text: str) -> str:
    pattern = re.compile(
        rf"(?ms)^(?P<indent> *){re.escape(HERMES_HOOK_START)}\s*$.*?^(?P=indent){re.escape(HERMES_HOOK_END)}\s*$\n?"
    )
    return pattern.sub("", text).rstrip() + "\n"


def _validate_hermes_config(text: str) -> None:
    """Reject a merge unless Hermes' YAML shape remains usable."""
    try:
        data = yaml.safe_load(text) if text.strip() else {}
    except yaml.YAMLError as exc:
        raise ValueError("Hermes config is not valid YAML") from exc
    if not isinstance(data, dict):
        raise ValueError("Hermes config root must be a mapping")
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        raise ValueError("Hermes hooks must be a mapping")
    entries = hooks.get("pre_tool_call")
    if not isinstance(entries, list):
        raise ValueError("Hermes pre_tool_call hooks must be a list")
    matches = [
        entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("command") == HERMES_HOOK_COMMAND
    ]
    if len(matches) != 1 or matches[0].get("matcher") != "^(terminal|shell)$":
        raise ValueError("Hermes managed hook did not merge exactly once")


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".utk.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _approve_hermes_hook(path: Path) -> None:
    data: dict = {"approvals": []}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError("Hermes hook allowlist is not valid JSON") from exc
        if not isinstance(loaded, dict) or not isinstance(loaded.get("approvals", []), list):
            raise ValueError("Hermes hook allowlist has an unsupported shape")
        data = loaded
        data.setdefault("approvals", [])
    exists = any(
        isinstance(entry, dict)
        and entry.get("event") == "pre_tool_call"
        and entry.get("command") == HERMES_HOOK_COMMAND
        for entry in data["approvals"]
    )
    if exists:
        return
    data["approvals"].append(
        {
            "event": "pre_tool_call",
            "command": HERMES_HOOK_COMMAND,
            "approved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "script_mtime_at_approval": None,
            "managed_by": "utk",
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".utk.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _revoke_hermes_hook(path: Path) -> None:
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(data, dict) or not isinstance(data.get("approvals"), list):
        return
    kept = [
        entry
        for entry in data["approvals"]
        if not (
            isinstance(entry, dict)
            and entry.get("event") == "pre_tool_call"
            and entry.get("command") == HERMES_HOOK_COMMAND
            and entry.get("managed_by") == "utk"
        )
    ]
    if len(kept) == len(data["approvals"]):
        return
    data["approvals"] = kept
    temporary = path.with_name(path.name + ".utk.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _caveman_instruction(level: str) -> str:
    # Response style is applied by the native proxy on each request so toggles take effect.
    return "Run supported shell commands through utk exec --. Preserve exact command arguments."
