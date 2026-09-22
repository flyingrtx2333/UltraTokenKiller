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
HERMES_PLUGIN_NAME = "utk-rewrite"
HERMES_PLUGIN_INIT = '''"""Hermes plugin adapter for UltraTokenKiller command rewriting."""
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys

_utk_executable = None
_missing_warned = False


def _resolve_utk():
    names = ("utk.exe", "utk") if os.name == "nt" else ("utk",)
    configured = os.environ.get("UTK_EXECUTABLE")
    if configured and Path(configured).is_file():
        return str(Path(configured).resolve())
    discovered = shutil.which("utk")
    if discovered:
        return discovered
    candidates = []
    candidates.extend(str(Path(sys.executable).with_name(name)) for name in names)
    state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    candidates.extend(str(state / "utk" / "venv" / "bin" / name) for name in names)
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    return None


def _utk_session(session_id):
    if not isinstance(session_id, str) or not session_id:
        return ""
    return "hermes_" + hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32]


def register(ctx):
    """Register a fail-open Hermes pre-tool callback."""
    global _utk_executable, _missing_warned
    _utk_executable = _resolve_utk()
    if not _utk_executable:
        if not _missing_warned:
            print("utk: hermes plugin warning: utk executable unavailable", file=sys.stderr)
            _missing_warned = True
        return
    ctx.register_hook("pre_tool_call", _pre_tool_call)
    ctx.register_middleware("llm_request", _llm_request)
    ctx.register_tool(
        name="utk_retrieve",
        toolset="utk",
        schema={
            "name": "utk_retrieve",
            "description": "Retrieve original content referenced by a UTK compression marker.",
            "parameters": {
                "type": "object",
                "properties": {
                    "handle": {"type": "string", "description": "UTK recovery handle"},
                    "offset": {"type": "integer", "minimum": 0, "default": 0},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 64000, "default": 32000},
                },
                "required": ["handle"],
                "additionalProperties": False,
            },
        },
        handler=_retrieve,
        description="Retrieve original content referenced by a UTK compression marker.",
    )


def _llm_request(request=None, session_id="", **_extra):
    session = _utk_session(session_id)
    if not session or not isinstance(request, dict):
        return None
    updated = dict(request)
    headers = dict(updated.get("extra_headers") or {})
    headers["x-utk-session-id"] = session
    updated["extra_headers"] = headers
    return {"request": updated, "source": "utk-rewrite", "reason": "session binding"}


def _retrieve(args=None, session_id="", **_extra):
    session = _utk_session(session_id)
    if not session:
        return "Original unavailable: Hermes session identifier is missing."
    args = args if isinstance(args, dict) else {}
    handle = args.get("handle")
    if not isinstance(handle, str) or not handle:
        return "Original unavailable: recovery handle is missing."
    command = [
        _utk_executable, "hermes-retrieve", "--session", session,
        "--handle", handle, "--offset", str(args.get("offset", 0)),
        "--limit", str(args.get("limit", 32000)),
    ]
    try:
        result = subprocess.run(command, shell=False, timeout=10, capture_output=True, text=True)
        if result.returncode != 0:
            return (result.stderr or "Original unavailable: UTK recovery failed.").strip()
        return "UTK_RETRIEVED_ORIGINAL\\n" + result.stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        _warn(f"utk retrieve failed: {type(error).__name__}")
        return "Original unavailable: UTK recovery service could not be reached."


def _pre_tool_call(tool_name="", args=None, session_id="", profile="", **extra):
    if tool_name not in {"terminal", "shell"} or not isinstance(args, dict):
        return
    command = args.get("command")
    if not isinstance(command, str) or not command.strip():
        return
    payload = {
        "hook_event_name": "pre_tool_call",
        "tool_name": tool_name,
        "tool_input": args,
        "session_id": session_id,
        "profile": profile,
        "extra": extra,
    }
    try:
        result = subprocess.run(
            [_utk_executable, "hermes-hook"],
            input=json.dumps(payload),
            shell=False,
            timeout=5,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            _warn(f"utk hermes-hook exited with {result.returncode}")
            return
        directive = json.loads(result.stdout or "{}")
        modified = directive.get("args") if directive.get("action") == "modify" else None
        if isinstance(modified, dict) and isinstance(modified.get("command"), str):
            args.update(modified)
            return {"action": "modify", "args": modified}
    except Exception as exc:
        _warn(str(exc))


def _warn(message):
    print(f"utk: hermes plugin warning: {message}", file=sys.stderr)
'''
HERMES_PLUGIN_MANIFEST = '''name: utk-rewrite
version: "0.2.0"
description: Bind Hermes requests and terminal output to UltraTokenKiller sessions.
author: UltraTokenKiller
hooks:
  - pre_tool_call
provides_hooks:
  - pre_tool_call
provides_middleware:
  - llm_request
provides_tools:
  - utk_retrieve
'''


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
        plugin = _hermes_plugin_enabled(text)
        detail = ("OpenAI-compatible provider; managed plugin " + ("enabled" if plugin else "not enabled")) if supported else "Current provider is not OpenAI-compatible"
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
        managed = _set_hermes_plugin(_add_hermes_block(text, proxy_port, caveman), enabled=True)
        _validate_hermes_config(managed)
        allowlist = self.root / HERMES_ALLOWLIST
        _backup(allowlist, backup_root)
        _install_hermes_plugin(self.root, backup_root)
        _atomic_write_text(self.config, managed)
        _revoke_hermes_hook(allowlist)
        return self.detect()

    def disable(self) -> ClientState:
        if self.config.exists():
            text = _remove_hermes_hook(self.config.read_text(encoding="utf-8"))
            text = _set_hermes_plugin(_remove_hermes_block(text), enabled=False)
            self.config.write_text(text, encoding="utf-8")
        _revoke_hermes_hook(self.root / HERMES_ALLOWLIST)
        _remove_hermes_plugin(self.root)
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
        child = re.match(r"^  (base_url|coding_instructions):", line)
        if child:
            previous[child.group(1)] = line
        else:
            kept.append(line)
    state = base64.urlsafe_b64encode(json.dumps({"created": created, "previous": previous}).encode("utf-8")).decode("ascii")
    managed = [
        f"  {START}",
        f"  # utk-hermes-state: {state}",
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


def _hermes_plugin_enabled(text: str) -> bool:
    try:
        data = yaml.safe_load(text) if text.strip() else {}
    except yaml.YAMLError:
        return False
    if not isinstance(data, dict):
        return False
    plugins = data.get("plugins")
    enabled = plugins.get("enabled") if isinstance(plugins, dict) else None
    return isinstance(enabled, list) and HERMES_PLUGIN_NAME in enabled


def _set_hermes_plugin(text: str, *, enabled: bool) -> str:
    """Add or remove the managed plugin while preserving unrelated YAML text."""
    try:
        data = yaml.safe_load(text) if text.strip() else {}
    except yaml.YAMLError as exc:
        raise ValueError("Hermes config is not valid YAML") from exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("Hermes config root must be a mapping")
    plugins = data.get("plugins")
    if plugins is None:
        if not enabled:
            return text
        suffix = "" if not text or text.endswith("\n") else "\n"
        return text + suffix + f"\nplugins:\n  enabled:\n    - {HERMES_PLUGIN_NAME}\n"
    if not isinstance(plugins, dict):
        raise ValueError("Hermes plugins must be a mapping")
    current = plugins.get("enabled")
    if current is None:
        current = []
    if not isinstance(current, list) or not all(isinstance(item, str) for item in current):
        raise ValueError("Hermes plugins.enabled must be a list of names")
    names = [item for item in current if item != HERMES_PLUGIN_NAME]
    if enabled:
        names.append(HERMES_PLUGIN_NAME)
    if names == current:
        return text

    lines = text.splitlines(keepends=True)
    plugin_lines = [i for i, line in enumerate(lines) if re.match(r"^plugins:\s*(?:#.*)?(?:\r?\n)?$", line)]
    if len(plugin_lines) != 1:
        raise ValueError("Hermes config must have one block-style root plugins section")
    root = plugin_lines[0]
    end = len(lines)
    for i in range(root + 1, len(lines)):
        raw = lines[i].rstrip("\r\n")
        if raw.strip() and not raw.lstrip().startswith("#") and not raw[0].isspace():
            end = i
            break
    if not enabled and not names and set(plugins) == {"enabled"}:
        del lines[root:end]
        return "".join(lines).rstrip() + "\n"
    enabled_lines = [
        i
        for i in range(root + 1, end)
        if re.match(r"^  enabled:\s*", lines[i])
    ]
    rendered = "  enabled: []\n" if not names else "  enabled:\n" + "".join(
        f"    - {json.dumps(name, ensure_ascii=False)}\n" for name in names
    )
    if not enabled_lines:
        if not enabled:
            return text
        if root + 1 == end and not lines[root].endswith(("\n", "\r")):
            lines[root] += "\n"
        lines[end:end] = [rendered]
        return "".join(lines)
    if len(enabled_lines) != 1:
        raise ValueError("Hermes config has multiple plugins.enabled sections")
    start = enabled_lines[0]
    enabled_end = end
    for i in range(start + 1, end):
        raw = lines[i].rstrip("\r\n")
        if raw.strip() and not raw.lstrip().startswith("#") and len(raw) - len(raw.lstrip()) <= 2:
            enabled_end = i
            break
    lines[start:enabled_end] = [rendered]
    return "".join(lines)


def _hermes_plugin_dir(root: Path) -> Path:
    return root / "plugins" / HERMES_PLUGIN_NAME


def _install_hermes_plugin(root: Path, backup_root: Path) -> None:
    plugin_dir = _hermes_plugin_dir(root)
    plugin_dir.mkdir(parents=True, exist_ok=True)
    files = {
        plugin_dir / "__init__.py": HERMES_PLUGIN_INIT,
        plugin_dir / "plugin.yaml": HERMES_PLUGIN_MANIFEST,
    }
    for path, content in files.items():
        _backup(path, backup_root)
        _atomic_write_text(path, content)


def _remove_hermes_plugin(root: Path) -> None:
    plugin_dir = _hermes_plugin_dir(root)
    files = {
        plugin_dir / "__init__.py": HERMES_PLUGIN_INIT,
        plugin_dir / "plugin.yaml": HERMES_PLUGIN_MANIFEST,
    }
    for path, expected in files.items():
        try:
            if path.read_text(encoding="utf-8") == expected:
                path.unlink()
        except OSError:
            pass
    try:
        plugin_dir.rmdir()
    except OSError:
        pass


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
    plugins = data.get("plugins")
    if not isinstance(plugins, dict):
        raise ValueError("Hermes plugins must be a mapping")
    enabled = plugins.get("enabled")
    if not isinstance(enabled, list):
        raise ValueError("Hermes plugins.enabled must be a list")
    if enabled.count(HERMES_PLUGIN_NAME) != 1:
        raise ValueError("Hermes managed plugin did not merge exactly once")


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".utk.tmp")
    temporary.write_text(text, encoding="utf-8")
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
