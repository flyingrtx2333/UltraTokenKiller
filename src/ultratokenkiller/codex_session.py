"""Version-gated, process-scoped Codex integration without credential copies."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import time

import httpx

from .config import Settings, choose_port, default_home
from .integrations import CodexAdapter

VERIFIED_CODEX = {"0.138.0", "0.153.4"}
SUBSCRIPTION_UPSTREAM = "https://chatgpt.com/backend-api/codex"


def codex_executable():
    executable = shutil.which("codex")
    if not executable and sys.platform == "darwin":
        candidates = [
            Path("/Applications/ChatGPT.app/Contents/Resources/codex"),
            Path.home() / "Applications/ChatGPT.app/Contents/Resources/codex",
        ]
        executable = next((str(path) for path in candidates if path.is_file()), None)
    if not executable:
        raise ValueError("Codex is not installed; UTK does not install it automatically")
    if executable.lower().endswith(".cmd"):
        script = Path(executable).parent / "node_modules/@openai/codex/bin/codex.js"
        node = shutil.which("node")
        if not node or not script.exists():
            raise ValueError("The installed Codex launcher cannot be resolved")
        return [node, str(script)]
    return [executable]


def toml_value(value):
    if isinstance(value, dict):
        return "{" + ", ".join(json.dumps(k) + "=" + toml_value(v) for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(v) for v in value) + "]"
    if isinstance(value, (str, bool, int)):
        return json.dumps(value, ensure_ascii=False)
    raise ValueError("Unsupported Codex override value")


def session_overrides(settings, home, session, config=None):
    """Share one opaque session across HTTP, MCP and command hooks.

    Existing inline hooks and explicit shell environment settings are retained.
    The caller owns the process environment; nothing is written to CODEX_HOME.
    """
    config = config or {}
    if not re.fullmatch(r"[a-f0-9]{32}", session):
        raise ValueError("Invalid UTK session")
    if "utk_recovery" in config.get("mcp_servers", {}):
        raise ValueError("Existing utk_recovery MCP configuration must be reviewed before launch")
    scoped = {"UTK_HOME": str(Path(home).resolve()), "UTK_SESSION_ID": session, "UTK_CLIENT": "codex"}
    shell_set = dict(config.get("shell_environment_policy", {}).get("set", {}))
    shell_set.update(scoped)
    # Codex loads hook groups from every layer; copying lower groups here would
    # execute user hooks twice. Add only this invocation's own group.
    hooks = []
    hooks.append({"matcher": "^Bash$", "hooks": [{"type": "command",
                  "command": "utk hook codex", "timeout": 10}]})
    provider = "utk_session_" + session[:12]
    route = settings.clients.get("codex", {})
    port = route.get("proxy_port", settings.headroom_port)
    values = {
        "model_provider": provider,
        f"model_providers.{provider}.name": "UTK native session",
        f"model_providers.{provider}.base_url": f"http://{settings.host}:{port}/v1",
        f"model_providers.{provider}.wire_api": "responses",
        f"model_providers.{provider}.requires_openai_auth": True,
        f"model_providers.{provider}.supports_websockets": False,
        f"model_providers.{provider}.env_http_headers": {"X-UTK-Session-Id": "UTK_SESSION_ID"},
        "mcp_servers.utk_recovery.command": sys.executable,
        "mcp_servers.utk_recovery.args": ["-m", "ultratokenkiller.mcp"],
        "mcp_servers.utk_recovery.env": scoped,
        "mcp_servers.utk_recovery.tools.utk_retrieve.approval_mode": "auto",
        "shell_environment_policy.set": shell_set,
        "features.hooks": True,
        "hooks.PreToolUse": hooks,
    }
    # Do not override approval policy, model, reasoning or unrelated MCP tools.
    return values, scoped


def validate_client(adapter, executable):
    version = subprocess.run(executable + ["--version"], capture_output=True, text=True,
                             encoding="utf-8", timeout=10, check=True).stdout
    match = re.search(r"\b(\d+\.\d+\.\d+)\b", version)
    if not match or match[1] not in VERIFIED_CODEX:
        raise ValueError("This Codex version has not been verified for automatic UTK sessions")
    if not adapter._uses_chatgpt_auth():
        raise ValueError("Automatic sessions currently require verified existing subscription login; no API fallback")
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    config = tomllib.loads(adapter.config.read_text(encoding="utf-8-sig")) if adapter.config.exists() else {}
    provider = config.get("model_provider", "openai")
    if provider not in {"openai", "headroom", "utk"}:
        raise ValueError("Unknown provider route; automatic upstream selection is unsupported")
    if provider == "headroom":
        from urllib.parse import urlparse
        base = config.get("model_providers", {}).get(provider, {}).get("base_url", "")
        if urlparse(base).hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Only the locally verified Headroom subscription route is recognized")
    return config


def ensure_route(home):
    from .runtime import start_processes
    settings = Settings.load(home)
    route = settings.clients.get("codex")
    if route and route.get("upstream_url") != SUBSCRIPTION_UPSTREAM:
        raise ValueError("Existing UTK Codex upstream differs; automatic route replacement is disabled")
    if not route:
        from .broker import BrokerClient
        from .recovery import RecoveryUnavailable
        broker_owned = False
        try:
            BrokerClient(home).retrieve("utk-launch-probe", "unavailable")
        except RecoveryUnavailable:
            broker_owned = True
        except (OSError, httpx.HTTPError, ValueError):
            pass
        excluded = {int(v["proxy_port"]) for v in settings.clients.values() if v.get("proxy_port")}
        settings.headroom_port = choose_port(settings.headroom_port, excluded=excluded | {settings.dashboard_port})
        if not broker_owned:
            settings.dashboard_port = choose_port(settings.dashboard_port, excluded=excluded | {settings.headroom_port})
        settings.clients["codex"] = {"proxy_port": settings.headroom_port, "managed": True,
                                     "upstream_url": SUBSCRIPTION_UPSTREAM}
        settings.save(home)
    start_processes(settings, home)
    port = settings.clients["codex"]["proxy_port"]
    with httpx.Client(timeout=1, trust_env=False) as client:
        for _ in range(50):
            try:
                proxy = client.get(f"http://{settings.host}:{port}/health").json()
                broker = client.get(f"http://{settings.host}:{settings.dashboard_port}/api/v1/health")
                expected = hashlib.sha256(SUBSCRIPTION_UPSTREAM.encode()).hexdigest()
                if proxy.get("engine") == "utk-native" and proxy.get("route_id") == expected and broker.is_success:
                    return settings
            except (httpx.HTTPError, ValueError):
                pass
            time.sleep(.1)
    raise ValueError("UTK route identity could not be verified; no Codex request was submitted")


def launch(arguments, home=None):
    if any(x in {"resume", "fork"} for x in arguments):
        raise ValueError("Resume/fork session recovery binding is not yet verified")
    root = Path(home or default_home()).expanduser().resolve()
    working = Path.cwd()
    for index, argument in enumerate(arguments):
        if argument == "--":
            break
        if argument in {"-C", "--cd"}:
            if index + 1 == len(arguments):
                raise ValueError("Codex working directory is missing")
            working = Path(arguments[index + 1]).expanduser().resolve()
        elif argument.startswith("--cd="):
            working = Path(argument.split("=", 1)[1]).expanduser().resolve()
    if not working.is_dir():
        raise ValueError("Codex working directory does not exist")
    executable = codex_executable()
    config = validate_client(CodexAdapter(), executable)
    # Validate conflicting MCP/hooks configuration before starting or writing anything.
    session = secrets.token_hex(16)
    session_overrides(Settings.load(root), root, session, config)
    settings = ensure_route(root)
    overrides, scoped = session_overrides(settings, root, session, config)
    from .codex_hook_trust import approve_session_hook
    overrides.update(approve_session_hook(executable, overrides, working))
    command = list(executable)
    for key, value in overrides.items():
        command.extend(["-c", key + "=" + toml_value(value)])
    command.extend(arguments)
    environment = {**os.environ, **scoped}
    return subprocess.call(command, env=environment)
