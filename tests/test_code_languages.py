import pytest

from ultratokenkiller.code_compression import parser_for
from ultratokenkiller.compression import compress_content
from ultratokenkiller.recovery import RecoveryVault


@pytest.mark.parametrize("language,source", [
    ("javascript", "function total(value) {"+"value += 1;"*100+"return value;}"),
    ("typescript", "function total(value: number): number {"+"value += 1;"*100+"return value;}"),
    ("go", "package test\nfunc total(value int) int {\n"+"value += 1\n"*100+"return value\n}"),
    ("rust", "fn total(mut value: i32) -> i32 {"+"value += 1;"*100+"value}"),
    ("java", "class Test { int total(int value) {"+"value += 1;"*100+"return value;} }"),
    ("c", "int total(int value) {"+"value += 1;"*100+"return value;}"),
    ("cpp", "int total(int value) {"+"value += 1;"*100+"return value;}"),
    ("perl", "sub total {\n my $value = 0;\n"+"$value += 1;\n"*100+"return $value;\n}"),
])
def test_syntax_and_original_preserved(language, source):
    vault = RecoveryVault()
    result = compress_content(source, session="test", vault=vault, hint="code:"+language)
    assert result.saved_tokens > 0, (language, result.fallback)
    assert not parser_for(language).parse(result.content.encode()).root_node.has_error
    assert "total" in result.content
    assert vault.retrieve("test", result.recovery_id)["content"] == source
