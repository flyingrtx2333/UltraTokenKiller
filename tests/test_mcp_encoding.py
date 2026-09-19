import io
import json

from ultratokenkiller import mcp


def test_stdio_utf8_independent_of_console_encoding(monkeypatch):
    class Broker:
        def retrieve(self, *args):
            return {"content": "中文🪨原文"}
    message = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "utk_retrieve", "arguments": {"handle": "x"}}}
    input_buffer = io.BytesIO((json.dumps(message)+"\n").encode("utf-8"))
    output_buffer = io.BytesIO()
    monkeypatch.setattr(mcp.sys, "stdin", io.TextIOWrapper(input_buffer, encoding="ascii"))
    monkeypatch.setattr(mcp.sys, "stdout", io.TextIOWrapper(output_buffer, encoding="ascii"))
    monkeypatch.setattr(mcp, "BrokerClient", Broker)
    monkeypatch.setenv("UTK_SESSION_ID", "bound")
    mcp.main()
    decoded = json.loads(output_buffer.getvalue().decode("utf-8"))
    assert "中文🪨原文" in decoded["result"]["content"][0]["text"]
