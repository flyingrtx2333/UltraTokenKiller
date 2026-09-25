from ultratokenkiller.token_count import count_text


def test_known_model_count_is_explicitly_labeled():
    result = count_text("A short request with a stable token count.", "gpt-4o")
    assert result.value > 0
    assert result.method.startswith(("tiktoken:", "utf8_bytes_div_4"))
    if result.method.startswith("tiktoken:") and "model_unmapped" not in result.method:
        assert result.exact_for_model


def test_unknown_or_missing_model_uses_labeled_fallback():
    text = "A short request with a stable token count."
    unknown = count_text(text, "utk-model-not-in-the-tokenizer-registry")
    missing = count_text(text)

    assert unknown.value > 0
    assert missing.value > 0
    assert not unknown.exact_for_model
    assert not missing.exact_for_model
    assert "model_unmapped" in unknown.method or unknown.method == "utf8_bytes_div_4"
