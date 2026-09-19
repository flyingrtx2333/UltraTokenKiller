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
from ultratokenkiller.codex_session import codex_executable, session_overrides, toml_value, validate_client
from ultratokenkiller import coding_acceptance


def config_change_summary(before, after):
    """Record changed section names only; never persist configuration values."""
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    left = tomllib.loads(before.decode("utf-8"))
    right = tomllib.loads(after.decode("utf-8"))
    known = {"model", "model_provider", "model_providers", "hooks", "mcp_servers",
             "projects", "features", "notice", "windows", "sandbox_mode",
             "approval_policy", "model_reasoning_effort"}
    changed = {key for key in left.keys() | right.keys() if left.get(key) != right.get(key)}
    return {"bytes_unchanged": before == after, "semantic_unchanged": left == right,
            "changed_sections": sorted(changed & known),
            "other_sections_changed": bool(changed - known)}


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
        and (needed < 2 or report["scope"] == "coding_task" or report["input_compressed_records"] > 0)
        and (report["scope"] != "coding_task" or (report.get("automatic_hook_records", 0) > 0
             and report.get("coding_verification", {}).get("passed", False)))
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
    scenario.add_argument("--coding-task", action="store_true")
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
    try:
        command = codex_executable()
    except ValueError as error:
        raise SystemExit(str(error)) from error
    home.mkdir(parents=True, exist_ok=True)
    session = secrets.token_hex(16)
    working = home
    coding_baseline = None
    if arguments.coding_task:
        validate_client(adapter, command)
        budget = budget_status(home)
        remaining = (budget["ceiling"] or arguments.request_limit) - budget["consumed"]
        if not arguments.offline_preflight and remaining < 4:
            raise SystemExit("Coding acceptance needs four remaining authorized submissions; budget was not changed")
        working = home / "coding" / session
        coding_baseline = coding_acceptance.prepare(working)
    settings = Settings(profile="safe", caveman=arguments.response_profile, auto_start=False,
                        dashboard_port=choose_port(19870), headroom_port=choose_port(19880))
    settings.clients = {"codex": {"proxy_port": settings.headroom_port, "managed": True,
                                  "upstream_url": "https://chatgpt.com/backend-api/codex"}}
    settings.save(home)
    os.environ["UTK_HOME"] = str(home)
    os.environ["UTK_SESSION_ID"] = session
    os.environ["UTK_CLIENT"] = "codex"
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
            sandbox_arguments = ["utk", "exec", "--session", sandbox_session, "--", "grep", "-n", "-H", ".", fixture.name]
            sandbox_working = home
            if arguments.coding_task:
                from ultratokenkiller.hooks import codex_event
                event = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_use_id": "preflight-" + sandbox_session,
                         "tool_input": {"command": "grep -n -H . calculator.py"}}
                rewrite = codex_event(event, sandbox_session)["hookSpecificOutput"]["updatedInput"]["command"]
                sandbox_arguments = rewrite.split()
                sandbox_working = working
            sandbox_check = run_owned(command + ["sandbox", "--permissions-profile", ":workspace",
                "-c", 'windows.sandbox="unelevated"', "-C", str(sandbox_working)] + sandbox_arguments,
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
        hook_trust = {}
        if arguments.coding_task:
            from ultratokenkiller.codex_hook_trust import approve_session_hook
            automatic, _ = session_overrides(settings, home, session)
            hook_trust = approve_session_hook(command, automatic, working)
        after_preflight = adapter.config.read_bytes()
        if arguments.offline_preflight:
            print(json.dumps({"offline_mcp_preflight": "passed", "scoped_hook_trust_verified": bool(hook_trust),
                "model_requests": 0, "budget": budget_status(home),
                "original_config_unchanged": adapter.config.read_bytes() == original}))
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
        if arguments.coding_task:
            automatic, scoped = session_overrides(settings, home, session)
            overrides.update(automatic)
            overrides.update(hook_trust)
            os.environ.update(scoped)
            overrides["developer_instructions"] = "This is a bounded coding acceptance task. Only modify calculator.py, run its tests and inspect its diff. Preserve tests. Run the requested raw grep command exactly; UTK's installed hook wraps it. Do not wrap commands in rtk or headroom. Do not explore other directories or spawn agents."
            overrides["projects"] = {str(working): {"trust_level": "trusted"}}
        command += ["exec", "--ignore-user-config", "--ephemeral", "--json", "--skip-git-repo-check", "--sandbox", "workspace-write", "-C", str(working), "-m", model]
        for key, value in overrides.items():
            command += ["-c", key+"="+toml_value(value)]
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
        if arguments.coding_task:
            prompt = coding_acceptance.prompt()
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
                error_types = [name for name in ["ValueError", "KeyError", "FileNotFoundError", "HTTPStatusError", "ConnectError", "RecoveryUnavailable", "TypeError", "TimeoutException"] if name in str(item.get("error") or {})]
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
        report["config_changes"] = {
            "preflight": config_change_summary(original, after_preflight),
            "client_run": config_change_summary(after_preflight, adapter.config.read_bytes()),
        }
        if completed.returncode and not event_types:
            # Classify initialization failure without persisting client logs.
            report["initialization_failure"] = "mcp" if "mcp" in completed.stderr.lower() else "client_startup"
        report["response_profile"] = arguments.response_profile
        report["input_compressed_records"] = sum(e["metadata"].get("changed_tool_results", 0) > 0 for e in events)
        report["scope"] = "recovery_only" if arguments.recovery_only else "tools_recovery" if arguments.tools_only else "input_tools_recovery_response_policy"
        if arguments.coding_task:
            report["scope"] = "coding_task"
            report["automatic_hook_records"] = sum(e["kind"] == "tool" and e["metadata"].get("tool_call_id") is not None
                                                  and e["metadata"].get("optimized", False) for e in events)
            report["coding_verification"] = coding_acceptance.verify(working, coding_baseline)
            report["baseline_tests"] = {"failed": coding_baseline["baseline_failed"], "passed": coding_baseline["baseline_passed"]}
        report["passed"] = acceptance_passed(report)
        (home / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        (home / f"report-{report['budget']['consumed']:03d}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2), flush=True)
    finally:
        stop_processes(home)


if __name__ == "__main__":
    main()
