from ultratokenkiller.text_compression import summarize_cjk_text
from ultratokenkiller.proxy import user_text


def test_chinese_selection_keeps_query_constraints_paths_and_numbers():
    chunks = ["这是普通背景段落，没有特殊信息。" for _ in range(20)]
    chunks[7] = "患者报告路径为 /data/病历-73.json，不得删除。"
    chunks[13] = "授权上限必须保持 128 次，失败时禁止重试。"
    text = "\n".join(chunks)
    result = summarize_cjk_text(text, "检查患者报告和授权上限", aggressive=True)
    assert len(result) < len(text)
    assert "/data/病历-73.json" in result and "不得删除" in result
    assert "128" in result and "禁止重试" in result
    assert "省略" in result


def test_structured_user_text_drives_query_without_touching_media():
    content = [{"type": "input_text", "text": "查找失败原因"},
               {"type": "input_image", "image_url": "data:image/png;base64,opaque"}]
    assert user_text(content) == "查找失败原因"
    assert content[1]["image_url"].endswith("opaque")
