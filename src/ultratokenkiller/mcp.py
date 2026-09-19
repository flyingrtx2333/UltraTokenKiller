"""Minimal MCP stdio server for session-scoped original retrieval."""
import json
import os
import sys

from .broker import BrokerClient

TOOL = {"name": "utk_retrieve", "description": "Retrieve a UTK-compressed original from this session's in-memory cache. Originals expire and do not survive restart.",
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
        "inputSchema": {"type": "object", "properties": {"handle": {"type": "string"}, "offset": {"type": "integer", "minimum": 0},
                                                         "limit": {"type": "integer", "minimum": 1, "maximum": 64000}},
                        "required": ["handle"], "additionalProperties": False}}


def dispatch(message, session, broker):
    method = message.get("method")
    if "id" not in message:
        return None
    identifier = message["id"]
    if method == "initialize":
        requested = message.get("params", {}).get("protocolVersion", "2024-11-05")
        version = requested if requested in {"2024-11-05", "2025-03-26", "2025-06-18"} else "2024-11-05"
        result = {"protocolVersion": version, "capabilities": {"tools": {}}, "serverInfo": {"name": "utk-recovery", "version": "0.2.0-dev"}}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": [TOOL]}
    elif method == "tools/call":
        params = message.get("params", {})
        if params.get("name") != "utk_retrieve":
            return {"jsonrpc": "2.0", "id": identifier, "error": {"code": -32602, "message": "Unknown tool"}}
        try:
            if not session:
                raise ValueError("UTK_SESSION_ID is missing; session isolation cannot be established")
            arguments = params.get("arguments", {})
            value = broker.retrieve(session, arguments["handle"], arguments.get("offset", 0), arguments.get("limit", 32000))
            result = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]}
        except Exception as error:
            result = {"isError": True, "content": [{"type": "text", "text": f"Original unavailable ({type(error).__name__}). Check session, expiry and broker connection."}]}
    else:
        return {"jsonrpc": "2.0", "id": identifier, "error": {"code": -32601, "message": "Method not found"}}
    return {"jsonrpc": "2.0", "id": identifier, "result": result}


def main():
    broker = BrokerClient()
    session = os.environ.get("UTK_SESSION_ID", "")
    # MCP stdio is UTF-8 regardless of the Windows console code page.
    for raw in sys.stdin.buffer:
        try:
            line = raw.decode("utf-8")
            result = dispatch(json.loads(line), session, broker)
        except (ValueError, TypeError, AttributeError):
            result = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Invalid JSON-RPC message"}}
        if result is not None:
            sys.stdout.buffer.write((json.dumps(result, ensure_ascii=False)+"\n").encode("utf-8"))
            sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
