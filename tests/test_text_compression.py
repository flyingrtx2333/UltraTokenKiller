from ultratokenkiller.text_compression import summarize_cjk_text, summarize_cjk_text_with_reason
from ultratokenkiller.proxy import user_text
from ultratokenkiller.compression import compress_content
from ultratokenkiller.recovery import RecoveryVault


def test_chinese_selection_keeps_query_constraints_paths_and_numbers():
    chunks = ["这是普通背景段落，没有特殊信息。" for _ in range(20)]
    chunks[7] = "患者报告路径为 /data/病历-73.json，不得删除。"
    chunks[13] = "授权上限必须保持 128 次，失败时禁止重试。"
    text = "\n".join(chunks)
    result, reason = summarize_cjk_text_with_reason(text, "检查患者报告和授权上限", aggressive=True)
    assert reason == "compressed"
    assert len(result) < len(text)
    assert len(result) / len(text) < .65
    assert "/data/病历-73.json" in result and "不得删除" in result
    assert "128" in result and "禁止重试" in result
    assert "省略" in result
    assert result.index("/data/病历-73.json") < result.index("128 次")
    assert summarize_cjk_text(text, "检查患者报告和授权上限", aggressive=True) == result


def test_short_chinese_text_reports_why_it_was_not_compressed():
    text = "先检查服务状态。再查看日志内容。最后核对运行结果。"
    rendered, reason = summarize_cjk_text_with_reason(text, "检查服务")
    assert rendered == text
    assert reason == "too_few_segments"


def test_structured_user_text_drives_query_without_touching_media():
    content = [{"type": "input_text", "text": "查找失败原因"},
               {"type": "input_image", "image_url": "data:image/png;base64,opaque"}]
    assert user_text(content) == "查找失败原因"
    assert content[1]["image_url"].endswith("opaque")


def test_english_encoder_unavailable_fails_open_without_losing_original(monkeypatch, tmp_path):
    text = "\n\n".join(
        f"The service report explains how operators review a separate scenario carefully."
        for _ in range(20)
    )

    def unavailable(_directory):
        raise RuntimeError("local model assets are unavailable")

    monkeypatch.setattr("ultratokenkiller.text_compression.load_encoder", unavailable)
    result = compress_content(
        text,
        session="english-test",
        vault=RecoveryVault(),
        query="operators review service reports",
        home=tmp_path,
    )
    assert result.content == text
    assert result.saved_tokens == 0
    assert result.fallback == "compression_error"
