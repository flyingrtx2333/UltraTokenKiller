from ultratokenkiller.compression import classify, compress_content
from ultratokenkiller.recovery import RecoveryVault


def test_repeated_pipe_table_is_compressed_and_recoverable():
    text = "opaque record | preserve=all | code=73\n" * 4
    assert classify(text) == "table"
    vault = RecoveryVault()
    result = compress_content(text, session="table", vault=vault)
    assert result.content.count("opaque record") == 1
    assert "3 repeated table rows omitted" in result.content
    assert "code=73" in result.content
    assert result.recovery_id
    assert vault.retrieve("table", result.recovery_id)["content"] == text


def test_inconsistent_pipe_text_remains_plain_text():
    text = "one | two | three\none | two\none | two | three\none | two | three\n"
    assert classify(text) == "text"
