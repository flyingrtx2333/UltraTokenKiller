import importlib.util
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "scripts" / "verify_codex_live.py"
spec = importlib.util.spec_from_file_location("live_acceptance", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_config_diagnostics_distinguish_formatting_without_leaking_values():
    original = b'model = "private-model"\n[projects."private-path"]\ntrust_level = "trusted"\n'
    formatting = b'# comment\n' + original
    result = module.config_change_summary(original, formatting)
    assert result == {"bytes_unchanged": False, "semantic_unchanged": True,
                      "changed_sections": [], "other_sections_changed": False}
    changed = module.config_change_summary(original, original.replace(b'trusted', b'untrusted'))
    assert changed["changed_sections"] == ["projects"]
    assert not changed["semantic_unchanged"]
    assert "private" not in str(changed)


def report():
    return {"exit_code": 0, "timed_out": False, "final_marker": True,
        "submissions_this_run": 4, "provider_usage_records": 4,
            "original_config_unchanged": True, "scope": "input_tools_recovery_response_policy",
            "optimized_command_records": 1, "input_compressed_records": 1,
            "tools": [{"type": "command_execution", "status": "completed", "exit_code": 0},
                      {"type": "command_execution", "status": "completed", "exit_code": 0},
                      {"type": "mcp_tool_call", "status": "completed", "tool": "utk_retrieve", "error_types": []}]}


def test_marker_cannot_hide_denied_or_failed_commands():
    assert module.acceptance_passed(report())
    for field, value in [("status", "declined"), ("exit_code", 1)]:
        data = report()
        data["tools"][0][field] = value
        assert not module.acceptance_passed(data)
    data = report()
    data["tools"].pop(0)
    assert not module.acceptance_passed(data)


def test_marker_cannot_replace_actual_compression_or_recovery_evidence():
    for field in ["input_compressed_records", "optimized_command_records", "submissions_this_run", "provider_usage_records"]:
        data = report()
        data[field] = 0
        assert not module.acceptance_passed(data)
    data = report()
    data["tools"][-1]["error_types"] = ["RecoveryUnavailable"]
    assert not module.acceptance_passed(data)


def test_only_exact_last_completed_answer_is_a_success_marker():
    def event(text, kind="item.completed"):
        return {"type": kind, "item": {"type": "agent_message", "text": text}}
    assert not module.recovery_marker(event("Could not produce UTK_REAL_RECOVERY_OK"))
    assert not module.recovery_marker(event("UTK_REAL_RECOVERY_OK", "item.started"))
    assert module.recovery_marker(event("UTK_REAL_RECOVERY_OK"))
    assert not module.recovery_marker(event("Recovery failed"), True)
    assert module.recovery_marker({"type": "turn.completed"}, True)
