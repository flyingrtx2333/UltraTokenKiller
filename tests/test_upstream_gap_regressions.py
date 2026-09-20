from ultratokenkiller.benchmark import fixture_options, fixtures
from ultratokenkiller.compression import compress_content
from ultratokenkiller.recovery import RecoveryVault


def _case(name: str):
    return next((text, required) for case, text, required in fixtures() if case == name)


def _compress(name: str):
    text, required = _case(name)
    result = compress_content(
        text,
        session=f"gap-{name}",
        vault=RecoveryVault(),
        **fixture_options(name),
    )
    return text, required, result


def test_repeated_protected_text_compresses_without_model_assets():
    original, required, result = _compress("prose-negation")
    assert result.metadata()["fallback"] is None
    assert len(result.content) < len(original) * 0.15
    assert all(fact in result.content for fact in required)
    assert "identical line repeated 49 more times" in result.content


def test_signature_query_can_omit_typescript_function_body():
    original, required, result = _compress("typescript-signature")
    assert result.metadata()["fallback"] is None
    assert len(result.content) < len(original) * 0.25
    assert all(fact in result.content for fact in required)
    assert "original body available through recovery" in result.content


def test_log_trace_keeps_error_chain_with_compact_context():
    original, required, result = _compress("log-trace")
    assert result.metadata()["fallback"] is None
    assert len(result.content) < len(original) * 0.35
    assert all(fact in result.content for fact in required)


def test_large_search_keeps_boundaries_and_caps_middle_hits():
    original, required, result = _compress("search-location")
    assert result.metadata()["fallback"] is None
    assert len(result.content) < len(original) * 0.30
    assert all(fact in result.content for fact in required)
    assert "src/very/long/path/source.py" in result.content
    assert "84 middle hits omitted" in result.content


def test_patch_summary_retains_every_changed_line_and_hunk():
    original, required, result = _compress("patch-change")
    assert result.metadata()["fallback"] is None
    assert len(result.content) < len(original) * 0.20
    assert all(fact in result.content for fact in required)
    assert "context omitted; summary" in result.content
