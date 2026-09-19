from __future__ import annotations

import base64
import json
import os
import re
import shutil
import time
from dataclasses import dataclass, asdict
from pathlib import Path


START = "# >>> ultratokenkiller managed >>>"
END = "# <<< ultratokenkiller managed <<<"


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
            'supports_websockets = true\n'
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
        detail = "OpenAI-compatible provider" if supported else "Current provider is not OpenAI-compatible"
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
        self.config.write_text(_add_hermes_block(text, proxy_port, caveman), encoding="utf-8")
        return self.detect()

    def disable(self) -> ClientState:
        if self.config.exists():
            self.config.write_text(_remove_hermes_block(self.config.read_text(encoding="utf-8")), encoding="utf-8")
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


def _caveman_instruction(level: str) -> str:
    if level == "off":
        return "Run supported shell commands through utk exec -- and preserve exact technical details."
    styles = {
        "lite": "Use concise complete sentences. Remove filler and hedging.",
        "full": "Respond tersely. Keep technical substance, paths, numbers, errors, and code exact.",
        "ultra": "Use minimum clear words. Keep all technical facts, negations, numbers, errors, and code exact.",
    }
    return f"Run supported shell commands through utk exec --. {styles.get(level, styles['lite'])}"
