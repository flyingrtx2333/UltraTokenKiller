from ultratokenkiller.caveman_reference import ACTIVE_MODES, RULES, compare_caveman_policy
from ultratokenkiller.engines import response_instruction


def test_fixed_policy_contract_covers_modes_and_safety_rules():
    upstream = "\n".join(
        [
            *(f"**{mode}**" for mode in ACTIVE_MODES),
            *(value for rule in RULES for value in rule["upstream"]),
        ]
    )
    report = compare_caveman_policy(upstream)
    assert report["policy_contract_passed"] is True
    assert report["paired_output_quality_passed"] is False
    assert report["live_model_calls"] == 0


def test_all_active_modes_preserve_fixed_common_invariants():
    for mode in ACTIVE_MODES:
        instruction = response_instruction(mode)
        for value in (
            "negations",
            "identifiers",
            "paths",
            "numbers",
            "units",
            "code blocks",
            "exact error strings",
            "Keep the user's language.",
        ):
            assert value in instruction
    assert response_instruction("off") == ""
