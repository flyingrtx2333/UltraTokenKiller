"""Explicit subscription-only acceptance with a persisted, explicitly authorized submission ceiling.

Never saves prompts or client output. Original Codex config/auth location is preserved.
"""
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx

from ultratokenkiller.budgets import budget_status
from ultratokenkiller.config import Settings, choose_port
from ultratokenkiller.integrations import CodexAdapter
from ultratokenkiller.runtime import start_processes, stop_processes
from ultratokenkiller.store import Store
from ultratokenkiller.processes import run_owned


def acceptance_passed(report):
    terminal = [t for t in report["tools"] if t.get("status") != "in_progress"]
    commands = [t for t in terminal if t.get("type") == "command_execution"]
    recovery = [t for t in terminal if t.get("tool") == "utk_retrieve"]
    needed = 0 if report["scope"] == "recovery_only" else 1 if report["scope"] == "tools_recovery" else 2
    return bool(
        report["exit_code"] == 0 and not report["timed_out"] and report["final_marker"]
        and report["original_config_unchanged"] and len(commands) == needed
        and all(t.get("status") == "completed" and t.get("exit_code") in (None, 0) for t in commands)
        and recovery and all(t.get("status") == "completed" and not t.get("error_types") for t in recovery)
        and (needed == 0 or report["optimized_command_records"] > 0)
        and (needed < 2 or report["input_compressed_records"] > 0)
    )


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    os.environ["PYTHONIOENCODING"] = "utf-8"
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--request-limit", type=int, required=True)
    parser.add_argument("--response-profile", choices=["off", "lite", "full", "ultra"], default="lite")
    parser.add_argument("--offline-preflight", action="store_true")
    scenario = parser.add_mutually_exclusive_group()
    scenario.add_argument("--recovery-only", action="store_true")
    scenario.add_argument("--tools-only", action="store_true")
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    import re
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", arguments.run_id) or arguments.request_limit < 1:
        raise SystemExit("A safe run ID and positive explicitly authorized request limit are required")
    home = root / "output" / arguments.run_id
    adapter = CodexAdapter()
    if not adapter._uses_chatgpt_auth():
        raise SystemExit("Subscription authentication unavailable; no API fallback permitted")
    original = adapter.config.read_bytes()
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    config = tomllib.loads(original.decode("utf-8"))
    model = arguments.model
    executable = shutil.which("codex")
    if not executable:
        raise SystemExit("Codex unavailable")
    command = [executable]
    if executable.lower().endswith(".cmd"):
        node_script = Path(executable).parent / "node_modules/@openai/codex/bin/codex.js"
        if not node_script.exists() or not shutil.which("node"):
            raise SystemExit("Cannot launch Codex without a shell wrapper")
        command = [shutil.which("node"), str(node_script)]
    home.mkdir(parents=True, exist_ok=True)
    session = secrets.token_hex(16)
    settings = Settings(profile="safe", caveman=arguments.response_profile, auto_start=False,
                        dashboard_port=choose_port(19870), headroom_port=choose_port(19880))
    settings.clients = {"codex": {"proxy_port": settings.headroom_port, "managed": True,
                                  "upstream_url": "https://chatgpt.com/backend-api/codex"}}
    settings.save(home)
    os.environ["UTK_HOME"] = str(home)
    os.environ["UTK_SESSION_ID"] = session
    os.environ["UTK_MAX_MODEL_REQUESTS"] = str(arguments.request_limit)
    fixture = home / "acceptance-fixture.log"
    fixture.write_text("UTK_RECOVERY_PROOF\n"+"\n".join(f"INFO synthetic record {i}: expected value" for i in range(240)), encoding="utf-8")
    start_processes(settings, home)
    try:
        with httpx.Client(trust_env=False, timeout=1) as client:
            deadline = time.monotonic()+20
            while time.monotonic() < deadline:
                try:
                    if client.get(f"http://127.0.0.1:{settings.dashboard_port}/api/v1/health").is_success and client.get(f"http://127.0.0.1:{settings.headroom_port}/health").is_success:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(.2)
            else:
                raise RuntimeError("Isolated UTK processes did not become healthy")
            token = (home / "session-token").read_text(encoding="ascii").strip()
            probe = client.post(f"http://127.0.0.1:{settings.dashboard_port}/api/v1/internal/compress",
                                headers={"X-UTK-Token": token}, json={"session": session, "content": json.dumps([{"probe": "UTK_RECOVERY_PROOF 中文🪨"}]*100, ensure_ascii=False)}).json()
        message = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "utk_retrieve", "arguments": {"handle": probe["recovery_id"], "limit": 2000}}}
        check = subprocess.run([sys.executable, "-m", "ultratokenkiller.mcp"], input=json.dumps(message)+"\n", text=True, encoding="utf-8",
                               capture_output=True, timeout=20)
        checked = json.loads(check.stdout)
        if checked.get("result", {}).get("isError") or "result" not in checked:
            raise RuntimeError("Offline MCP preflight failed: "+str(checked.get("error", checked.get("result", {}))))
        if os.name == "nt":
            sandbox_session = secrets.token_hex(16)
            sandbox_check = run_owned(command + ["sandbox", "--permissions-profile", ":workspace",
                "-c", 'windows.sandbox="unelevated"', "-C", str(home),
                "utk", "exec", "--session", sandbox_session, "--", "rg", "-n", "--with-filename", ".", fixture.name],
                input="", timeout=30)
            if sandbox_check.returncode or "UTK original:" not in sandbox_check.stdout:
                print("Sandbox preflight exit:", sandbox_check.returncode, flush=True)
                print("Sandbox preflight diagnostic:", sandbox_check.stderr[-1500:], flush=True)
                print("Tool metadata:", [e["metadata"] for e in Store(home / "metrics.sqlite3").events(5) if e["kind"] == "tool"], flush=True)
                raise RuntimeError("Offline sandbox tool compression failed; model submissions were not attempted")
            sandbox_hash = hashlib.sha256(sandbox_session.encode()).hexdigest()
            sandbox_events = Store(home / "metrics.sqlite3").events(100)
            if not any(e["kind"] == "tool" and e["metadata"].get("session_id") == sandbox_hash
                       and e["metadata"].get("optimized") for e in sandbox_events):
                raise RuntimeError("Offline sandbox metrics preflight failed; model submissions were not attempted")
        if arguments.offline_preflight:
            print(json.dumps({"offline_mcp_preflight": "passed", "model_requests": 0, "budget": budget_status(home)}))
            return
        overrides = {
            "model_provider": "utk_acceptance",
            "model_providers.utk_acceptance.name": "UTK acceptance",
            "model_providers.utk_acceptance.base_url": f"http://127.0.0.1:{settings.headroom_port}/v1",
            "model_providers.utk_acceptance.wire_api": "responses",
            "model_providers.utk_acceptance.requires_openai_auth": True,
            "model_providers.utk_acceptance.supports_websockets": False,
            "mcp_servers.utk_recovery.command": sys.executable,
            "mcp_servers.utk_recovery.args": ["-m", "ultratokenkiller.mcp"],
            "mcp_servers.utk_recovery.tools.utk_retrieve.approval_mode": "auto",
            "shell_environment_policy.inherit": "all",
            "approval_policy": "never",
            "developer_instructions": "This is a bounded acceptance task. Only run the requested fixture read and original-recovery tool. Do not explore repositories, spawn other agents or call other models.",
        }
        if os.name == "nt":
            overrides["windows.sandbox"] = "unelevated"
        command += ["exec", "--ignore-user-config", "--ephemeral", "--json", "--skip-git-repo-check", "--sandbox", "workspace-write", "-C", str(home), "-m", model]
        for key, value in overrides.items():
            command += ["-c", key+"="+json.dumps(value)]
        command += ["-c", 'model_providers.utk_acceptance.env_http_headers={"X-UTK-Session-Id"="UTK_SESSION_ID"}']
        env_inline = "{"+", ".join(json.dumps(k)+"="+json.dumps(os.environ[k]) for k in ["UTK_HOME", "UTK_SESSION_ID"])+"}"
        command += ["-c", "mcp_servers.utk_recovery.env="+env_inline, "-"]
        if not shutil.which("utk"):
            raise RuntimeError("Install the UTK CLI before client acceptance")
        wrapper = f"utk exec --session {session} -- rg -n --with-filename . acceptance-fixture.log"
        prompt = (
            "Perform this bounded integration test, in order. Use shell twice, with no other shell commands. "
            "First run: rg -n --with-filename . acceptance-fixture.log\n"
            "Second run: " + wrapper + "\n"
            "Each result should contain a UTK original recovery handle. Call utk_retrieve on each distinct handle "
            "with offset 0 and limit 2000. Verify recovered content contains UTK_RECOVERY_PROOF. "
            "Only after both commands and recovery succeed, answer exactly UTK_REAL_RECOVERY_OK. "
            "Do not inspect other files or run other tasks."
        )
        if arguments.recovery_only:
            prompt = (f"Use the utk_retrieve MCP tool exactly once with handle {probe['recovery_id']}, offset 0, limit 500. "
                      "Confirm its recovered content contains UTK_RECOVERY_PROOF. If it succeeds, answer exactly UTK_REAL_RECOVERY_OK. "
                      "Do not run shell commands or any other tools.")
        if arguments.tools_only:
            prompt = ("Run exactly this one read-only shell command: " + wrapper + "\n"
                      "Find the recovery handle in its output, call utk_retrieve with offset 0 and limit 2000, "
                      "verify UTK_RECOVERY_PROOF, then answer UTK_REAL_RECOVERY_OK. Do not run other shell commands.")
        before = budget_status(home)["consumed"]
        timed_out = False
        try:
            completed = run_owned(command, input=prompt, timeout=240)
        except subprocess.TimeoutExpired as error:
            timed_out = True
            output = error.stdout.decode("utf-8", errors="replace") if isinstance(error.stdout, bytes) else error.stdout or ""
            completed = subprocess.CompletedProcess(command, 124, stdout=output, stderr="acceptance timeout")
        event_types = []
        tool_types = []
        marker = False
        for line in completed.stdout.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            event_types.append(event.get("type"))
            item = event.get("item", {})
            if item.get("status") == "declined":
                # Shown only; never persisted in the metadata report.
                print("Client declined command: " + str(item.get("aggregated_output", item.get("error", "reason unavailable")))[:1200], flush=True)
            if item.get("type") in {"command_execution", "mcp_tool_call"}:
                error_types = [name for name in ["ValueError", "KeyError", "FileNotFoundError", "HTTPStatusError", "ConnectError", "RecoveryUnavailable", "TypeError", "TimeoutException"] if name in str(item)]
                tool_types.append({"type": item["type"], "status": item.get("status"), "tool": item.get("tool"),
                                   "error_types": error_types, "exit_code": item.get("exit_code"),
                                   "error_category": "sandbox" if "sandbox" in str(item).lower() else "permission" if "permission" in str(item).lower() else None})
            if item.get("type") == "agent_message" and "UTK_REAL_RECOVERY_OK" in item.get("text", ""):
                marker = True
        events = Store(home / "metrics.sqlite3").events(100)
        session_hash = hashlib.sha256(session.encode()).hexdigest()
        events = [e for e in events if e["metadata"].get("session_id") == session_hash]
        report = {"client": "codex", "model": model, "authentication": "existing_subscription", "exit_code": completed.returncode,
                  "timed_out": timed_out, "recovery_only": arguments.recovery_only,
                  "final_marker": marker, "event_types": event_types, "tools": tool_types,
                  "budget": budget_status(home), "submissions_this_run": budget_status(home)["consumed"]-before,
                  "provider_usage_records": sum(e["input_tokens"] is not None for e in events),
                  "optimized_command_records": sum(e["kind"] == "tool" and e["metadata"].get("optimized", False) for e in events),
                  "original_config_unchanged": hashlib.sha256(adapter.config.read_bytes()).digest() == hashlib.sha256(original).digest()}
        if completed.returncode and not event_types:
            # Classify initialization failure without persisting client logs.
            report["initialization_failure"] = "mcp" if "mcp" in completed.stderr.lower() else "client_startup"
        report["response_profile"] = arguments.response_profile
        report["input_compressed_records"] = sum(e["metadata"].get("changed_tool_results", 0) > 0 for e in events)
        report["scope"] = "recovery_only" if arguments.recovery_only else "tools_recovery" if arguments.tools_only else "input_tools_recovery_response_policy"
        report["passed"] = acceptance_passed(report)
        (home / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        (home / f"report-{report['budget']['consumed']:03d}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2), flush=True)
    finally:
        stop_processes(home)


if __name__ == "__main__":
    main()
