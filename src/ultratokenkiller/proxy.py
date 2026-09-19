"""UTK's native HTTP/SSE proxy. One configured upstream per local listener."""
from __future__ import annotations

import json
import os
import time
import asyncio
import copy
import uuid
import hashlib
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse

from .config import Settings, default_home
from .engines import apply_response_style, estimate_tokens
from .broker import BrokerClient
from .store import Store

HOP_HEADERS = {"host", "content-length", "connection", "transfer-encoding", "keep-alive", "upgrade", "proxy-authorization", "proxy-authenticate", "te", "trailer"}


def usage_fields(payload: dict) -> dict:
    response = payload.get("response", payload.get("message", payload))
    usage = response.get("usage") if isinstance(response, dict) else None
    if not isinstance(usage, dict):
        return {}
    details = usage.get("input_tokens_details", usage.get("prompt_tokens_details", {})) or {}
    result = {"input_tokens": usage.get("input_tokens", usage.get("prompt_tokens")),
            "output_tokens": usage.get("output_tokens", usage.get("completion_tokens")),
            "cached_tokens": details.get("cached_tokens", usage.get("cache_read_input_tokens"))}
    return {key: value for key, value in result.items() if isinstance(value, int) and not isinstance(value, bool) and value >= 0}


async def compress_request(payload, settings, root, session):
    result = copy.deepcopy(payload)
    metadata = {"estimated_input_before": estimate_tokens(json.dumps(payload, ensure_ascii=False)),
                "estimator": "utf8_bytes_div_4", "changed_tool_results": 0}
    if not session:
        metadata["compression_fallback"] = "missing_session"
    else:
        broker = BrokerClient(root)
        items = result.get("messages", result.get("input", []))
        if isinstance(items, list):
            query = next((item.get("content", "") for item in reversed(items) if isinstance(item, dict) and item.get("role") == "user"), "")
            if not isinstance(query, str):
                query = ""
            for item in items:
                if not isinstance(item, dict):
                    continue
                fields = []
                if item.get("role") == "tool" and isinstance(item.get("content"), str):
                    fields.append((item, "content"))
                if item.get("type") == "function_call_output" and isinstance(item.get("output"), str):
                    fields.append((item, "output"))
                if isinstance(item.get("content"), list):
                    for block in item["content"]:
                        if isinstance(block, dict) and block.get("type") == "tool_result" and isinstance(block.get("content"), str):
                            fields.append((block, "content"))
                for block, key in fields:
                    compressed = await asyncio.to_thread(broker.compress, block[key], session, query=query)
                    if compressed["content"] != block[key]:
                        metadata["changed_tool_results"] += 1
                        block[key] = compressed["content"]
    metadata["estimated_input_after"] = estimate_tokens(json.dumps(result, ensure_ascii=False))
    metadata["estimated_saved_tokens"] = max(0, metadata["estimated_input_before"]-metadata["estimated_input_after"])
    return result, metadata


class UsageObserver:
    """Bounded side observation; wire bytes are always forwarded unchanged."""
    def __init__(self, sse: bool):
        self.sse = sse
        self.buffer = b""
        self.usage: dict = {}
        self.disabled = False
        self.event_data = []
        self.failed = False

    def feed(self, chunk: bytes):
        if self.disabled:
            return
        self.buffer += chunk
        if self.sse:
            while b"\n" in self.buffer:
                line, self.buffer = self.buffer.split(b"\n", 1)
                line = line.rstrip(b"\r")
                if line.startswith(b"data:"):
                    self.event_data.append(line[5:].lstrip(b" "))
                elif not line and self.event_data:
                    self.parse(b"\n".join(self.event_data))
                    self.event_data.clear()
                if sum(map(len, self.event_data)) > 2 * 1024 * 1024:
                    self.event_data.clear()
                    self.disabled = True
                    break
        if len(self.buffer) > 2 * 1024 * 1024:
            self.buffer = b""
            self.disabled = True

    def parse(self, value: bytes):
        try:
            data = json.loads(value)
            if isinstance(data, dict):
                self.usage.update(usage_fields(data))
                if data.get("type") in {"error", "response.failed", "response.incomplete"} or data.get("error"):
                    self.failed = True
        except (ValueError, TypeError, AttributeError):
            pass

    def finish(self):
        if not self.sse and not self.disabled:
            self.parse(self.buffer)


def create_proxy(upstream: str | None = None, home=None, transport=None) -> FastAPI:
    root = home or default_home()
    upstream = upstream or os.environ.get("UTK_UPSTREAM_URL", "https://api.openai.com/v1")
    client_name = os.environ.get("UTK_CLIENT", "unknown")
    store = Store(root / "metrics.sqlite3")

    @asynccontextmanager
    async def lifespan(app):
        # No retries: a retry after uncertain submission can duplicate a model request.
        async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=20), transport=transport,
                                     follow_redirects=False) as client:
            app.state.upstream = client
            yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)

    @app.get("/health")
    def health():
        return {"status": "ok", "engine": "utk-native"}

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
    async def forward(path: str, request: Request):
        started = time.perf_counter()
        body = await request.body()
        metadata: dict = {"engine": "utk-native", "transport": "http"}
        model = None
        settings = Settings.load(root)
        session = request.headers.get("x-utk-session-id", "")
        if len(session) > 256:
            session = ""
        metadata["request_id"] = uuid.uuid4().hex
        if session:
            metadata["session_id"] = hashlib.sha256(session.encode()).hexdigest()
        if request.method == "POST" and path.rstrip("/").endswith(("responses", "chat/completions", "messages")):
            try:
                payload = json.loads(body)
                if isinstance(payload, dict):
                    model = payload.get("model")
                    # Style overhead is included before the compression estimate.
                    styled = apply_response_style(payload, settings.caveman, protocol="anthropic" if path.rstrip("/").endswith("messages") else "openai")
                    compressed, estimates = await compress_request(styled, settings, root, session)
                    metadata.update(estimates)
                    metadata["response_style"] = settings.caveman
                    body = json.dumps(compressed, ensure_ascii=False).encode("utf-8")
            except Exception:
                # Any optimization failure retains the exact original request bytes.
                metadata["compression_fallback"] = True
        route = path
        if route.startswith("v1/"):
            route = route[3:]
        url = upstream.rstrip("/") + "/" + route
        if request.url.query:
            url += "?" + request.url.query
        excluded = HOP_HEADERS | {part.strip().lower() for part in request.headers.get("connection", "").split(",")} | {"x-utk-session-id", "x-utk-token"}
        headers = {k: v for k, v in request.headers.items() if k.lower() not in excluded}
        headers["accept-encoding"] = "identity"
        try:
            client = app.state.upstream
            outgoing = client.build_request(request.method, url, content=body, headers=headers)
            response = await client.send(outgoing, stream=True)
        except httpx.HTTPError:
            store.add(kind="input", client=client_name, model=model, success=False,
                      duration_ms=int((time.perf_counter()-started)*1000), metadata=metadata)
            return JSONResponse({"error": {"message": "UTK upstream connection failed"}}, status_code=502)
        observer = UsageObserver("text/event-stream" in response.headers.get("content-type", ""))

        async def stream():
            completed = False
            try:
                async for chunk in response.aiter_bytes():
                    observer.feed(chunk)
                    yield chunk
                completed = True
            finally:
                await response.aclose()
                observer.finish()
                store.add(kind="input", client=client_name, model=model,
                          success=completed and response.is_success and not observer.failed,
                          duration_ms=int((time.perf_counter()-started)*1000),
                          saved_tokens=metadata.get("estimated_saved_tokens", 0),
                          metadata=metadata, **observer.usage)

        response_headers = {k: v for k, v in response.headers.items()
                            if k.lower() not in HOP_HEADERS | {"content-encoding"}}
        return StreamingResponse(stream(), status_code=response.status_code, headers=response_headers)

    @app.websocket("/{path:path}")
    async def forward_websocket(path: str, socket: WebSocket):
        from websockets.asyncio.client import connect
        from websockets.exceptions import ConnectionClosed, InvalidStatus
        route = path[3:] if path.startswith("v1/") else path
        url = upstream.rstrip("/") + "/" + route
        url = url.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
        if socket.url.query:
            url += "?" + socket.url.query
        headers = {k: v for k, v in socket.headers.items() if k.lower() not in HOP_HEADERS | {"sec-websocket-key", "sec-websocket-version", "sec-websocket-extensions", "sec-websocket-protocol", "x-utk-session-id", "x-utk-token"}}
        protocols = [x.strip() for x in socket.headers.get("sec-websocket-protocol", "").split(",") if x.strip()]
        try:
            remote = await connect(url, additional_headers=headers, subprotocols=protocols or None,
                                   compression=None, max_size=16*1024*1024, max_queue=16, open_timeout=20)
        except InvalidStatus as error:
            await socket.send_denial_response(JSONResponse({"error": "Upstream WebSocket handshake rejected"}, status_code=error.response.status_code))
            return
        except Exception:
            await socket.close(code=1013)
            return
        await socket.accept(subprotocol=remote.subprotocol)
        async def to_upstream():
            try:
                while True:
                    message = await socket.receive()
                    if message["type"] == "websocket.disconnect":
                        return
                    # Transport parity first: WebSocket frames are not optimized until session binding is verified.
                    await remote.send(message.get("text") if message.get("text") is not None else message["bytes"])
            except (WebSocketDisconnect, ConnectionClosed):
                return
        async def to_client():
            observer = UsageObserver(False)
            async for message in remote:
                if isinstance(message, str):
                    await socket.send_text(message)
                    try:
                        event = json.loads(message)
                        if event.get("type") in {"response.completed", "response.failed", "response.incomplete"}:
                            store.add(kind="input", client=client_name, success=event["type"] == "response.completed",
                                      metadata={"transport": "websocket", "engine": "utk-native", "compression_fallback": "websocket_passthrough"},
                                      **usage_fields(event))
                    except (ValueError, AttributeError, TypeError):
                        pass
                else:
                    await socket.send_bytes(message)
        tasks = [asyncio.create_task(to_upstream()), asyncio.create_task(to_client())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await remote.close()
            try:
                await socket.close(code=remote.close_code if remote.close_code in {1000, 1001, 1008, 1011, 1013} else 1011)
            except (RuntimeError, WebSocketDisconnect):
                pass

    return app
