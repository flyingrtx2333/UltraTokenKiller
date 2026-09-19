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
from .codex_hook_trust import CODEX_SHELL_MATCHER, utk_hook_command
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


def local_broker_permissions(home, profile="utk_acceptance", parent=":workspace"):
    """Isolated acceptance policy: workspace writes, one socket, no domains.

    Requires ignore-user-config so older sandbox settings cannot override it.
    network.enabled alone is NOT restrictive; the proxy is mandatory.
    """
    from .local_transport import broker_socket
    if parent not in {":workspace", ":read-only"}:
        raise ValueError("Unsupported local broker filesystem policy")
    path = broker_socket(Path(home))
    if path is None:
        raise ValueError("Unix broker permissions require a Unix host")
    from .config import choose_port
    port = choose_port(19990)
    return {
        "default_permissions": profile,
        "features.network_proxy": True,
        f"permissions.{profile}.extends": parent,
        f"permissions.{profile}.network.enabled": True,
        f"permissions.{profile}.network.proxy_url": f"http://127.0.0.1:{port}",
        f"permissions.{profile}.network.enable_socks5": False,
        f"permissions.{profile}.network.domains": {},
        f"permissions.{profile}.network.unix_sockets": {str(path): "allow"},
    }


def macos_broker_overrides(home, working, session, config, arguments):
    """Add local IPC only for verified basic policies, without rewriting config.

    Explicit permission overrides, legacy settings and custom profiles must not
    silently lose rules when adding the IPC proxy. Refuse these before startup.
    """
    if sys.platform != "darwin":
        return {}
    unsupported = {"sandbox_mode", "sandbox_workspace_write", "profile"} & config.keys()
    feature = config.get("features", {}).get("network_proxy")
    if unsupported or feature not in (None, False):
        raise ValueError("Automatic Mac IPC is not verified with legacy sandbox or existing network proxy settings; original configuration was preserved")
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    restricted = {"sandbox_mode", "sandbox_workspace_write", "default_permissions", "permissions", "features", "profile", "profiles"}
    for index, arg in enumerate(arguments):
        if arg == "--":
            break
        if arg in {"-s", "--sandbox", "-p", "--profile", "--full-auto", "--approve-for-me", "--dangerously-bypass-approvals-and-sandbox"} or arg.startswith(("--sandbox=", "--profile=")) or (arg.startswith(("-s", "-p")) and not arg.startswith("--")):
            raise ValueError("Explicit permission/profile flags cannot be combined with automatic Mac IPC")
        value = arguments[index + 1] if arg in {"-c", "--config"} and index + 1 < len(arguments) else arg.split("=", 1)[1] if arg.startswith("--config=") else arg[2:] if arg.startswith("-c") else ""
        key = value.split("=", 1)[0]
        try:
            roots = set(tomllib.loads(key + "=0")) if key else set()
        except ValueError as error:
            raise ValueError("Unparseable config override; automatic Mac IPC was not applied") from error
        if roots & restricted:
            raise ValueError("Explicit permission/profile overrides cannot be combined with automatic Mac IPC")
    parent = config.get("default_permissions")
    if parent is None:
        # Match Codex's implicit profile: a known project (including explicitly
        # untrusted ones) gets workspace policy; otherwise remain read-only.
        known = False
        for path, project in config.get("projects", {}).items():
            candidate = Path(path).expanduser().resolve()
            if (candidate == working or candidate in working.parents) and project.get("trust_level") in {"trusted", "untrusted"}:
                known = True
                break
        parent = ":workspace" if known else ":read-only"
    if parent not in {":workspace", ":read-only"}:
        raise ValueError("Automatic Mac IPC is not verified with this custom permission profile; original configuration was preserved")
    return local_broker_permissions(home, "utk_local_" + session[:12], parent)


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
    hooks.append({"matcher": CODEX_SHELL_MATCHER, "hooks": [{"type": "command",
                                                    "command": utk_hook_command(), "timeout": 10}]})
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
    if sys.platform == "darwin" and match[1] != "0.153.4":
        raise ValueError("Automatic Mac IPC has only been verified with Codex 0.153.4")
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


def session_command(executable, arguments, overrides):
    """Keep all config flags in the final CLI scope (Codex 0.153.4).

    Clap drops root config flags when the subcommand also has config flags.
    Collect user flags in order, then append managed flags in that same scope.
    Arguments after -- are positional and must never be parsed or reordered.
    """
    command = list(executable)
    configs = []
    tail = []
    index = 0
    while index < len(arguments):
        arg = arguments[index]
        if arg == "--":
            tail = arguments[index:]
            break
        if arg in {"-c", "--config"}:
            index += 1
            if index >= len(arguments):
                raise ValueError("Missing Codex config override")
            configs.extend(["-c", arguments[index]])
        elif arg.startswith("--config="):
            configs.extend(["-c", arg.split("=", 1)[1]])
        elif arg.startswith("-c") and not arg.startswith("--"):
            configs.extend(["-c", arg[2:]])
        else:
            command.append(arg)
        index += 1
    command.extend(configs)
    for key, value in overrides.items():
        command.extend(["-c", key + "=" + toml_value(value)])
    return command + tail


def verify_session_config(executable, command, working, overrides):
    """Fail closed on effective route/MCP binding before any model submission."""
    from .codex_hook_trust import inspect_codex
    flags = []
    args = command[len(executable):]
    index = 0
    while index < len(args):
        if args[index] == "--":
            break
        if args[index] == "-c":
            flags.extend(args[index:index + 2])
            index += 1
        index += 1
    config = inspect_codex(list(executable) + ["app-server"] + flags, working,
        "config/read", {"includeLayers": False, "cwd": str(working)})["config"]
    provider = overrides["model_provider"]
    expected_url = overrides[f"model_providers.{provider}.base_url"]
    actual_url = config.get("model_providers", {}).get(provider, {}).get("base_url")
    recovery = config.get("mcp_servers", {}).get("utk_recovery", {})
    if (config.get("model_provider") != provider or actual_url != expected_url
            or recovery.get("command") != overrides["mcp_servers.utk_recovery.command"]
            or recovery.get("env") != overrides["mcp_servers.utk_recovery.env"]):
        raise ValueError("Effective Codex route or recovery binding differs; no model request was submitted")


def launch(arguments, home=None, *, session_id=None):
    if any(x in {"resume", "fork"} for x in arguments):
        raise ValueError("Resume/fork session recovery binding is not yet verified")
    for argument in arguments:
        if argument == "--":
            break
        if (argument in {"--oss", "--local-provider", "--profile", "-p"}
                or argument.startswith(("--local-provider=", "--profile="))
                or (argument.startswith("-p") and not argument.startswith("--"))):
            raise ValueError("Provider/profile selection can bypass the verified UTK route; no request was submitted")
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
    session = session_id or secrets.token_hex(16)
    if not re.fullmatch(r"[a-f0-9]{32}", session):
        raise ValueError("Invalid UTK session")
    permissions = macos_broker_overrides(root, working, session, config, arguments)
    session_overrides(Settings.load(root), root, session, config)
    settings = ensure_route(root)
    overrides, scoped = session_overrides(settings, root, session, config)
    overrides.update(permissions)
    from .codex_hook_trust import approve_session_hook
    overrides.update(approve_session_hook(executable, overrides, working))
    command = session_command(executable, arguments, overrides)
    verify_session_config(executable, command, working, overrides)
    environment = {**os.environ, **scoped}
    return subprocess.call(command, env=environment)
