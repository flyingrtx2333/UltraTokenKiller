"""UTK's native HTTP/SSE proxy. One configured upstream per local listener."""
from __future__ import annotations

import json
import os
import time
import asyncio
import copy
import uuid
import hashlib
from contextlib import asynccontextmanager, suppress

import httpx
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse

from .config import Settings, default_home
from .identity import ensure_session_token, instance_id
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
            query = next((user_text(item.get("content")) for item in reversed(items)
                          if isinstance(item, dict) and item.get("role") == "user"), "")
            for item in items:
                if not isinstance(item, dict):
                    continue
                fields = []
                if item.get("role") == "tool":
                    fields.extend(tool_text_fields(item, "content"))
                if item.get("type") in {"function_call_output", "custom_tool_call_output"}:
                    fields.extend(tool_text_fields(item, "output"))
                if isinstance(item.get("content"), list):
                    for block in item["content"]:
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            fields.extend(tool_text_fields(block, "content"))
                for block, key in fields:
                    compressed = await asyncio.to_thread(broker.compress, block[key], session, query=query)
                    if compressed["content"] != block[key]:
                        metadata["changed_tool_results"] += 1
                        block[key] = compressed["content"]
            metadata["changed_images"] = await compress_inline_images(items, broker, session, query)
    metadata["estimated_input_after"] = estimate_tokens(json.dumps(result, ensure_ascii=False))
    metadata["estimated_saved_tokens"] = max(0, metadata["estimated_input_before"]-metadata["estimated_input_after"])
    return result, metadata


def user_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(part.get("text", "") for part in content if isinstance(part, dict)
                         and part.get("type") in {"text", "input_text"} and isinstance(part.get("text"), str))
    return ""


async def compress_inline_images(items, broker, session, query):
    changed = 0
    for item in items:
        content = item.get("content") if isinstance(item, dict) else None
        if not isinstance(content, list):
            continue
        markers = []
        for block in content:
            if not isinstance(block, dict):
                continue
            target = None
            if block.get("type") in {"input_image", "image_url"}:
                image = block.get("image_url")
                if isinstance(image, str):
                    target = (block, "image_url", image)
                elif isinstance(image, dict) and isinstance(image.get("url"), str):
                    target = (image, "url", image["url"])
            elif block.get("type") == "image" and isinstance(block.get("source"), dict):
                source = block["source"]
                if source.get("type") == "base64" and isinstance(source.get("data"), str):
                    target = (source, "data", f"data:{source.get('media_type', 'image/png')};base64,{source['data']}")
            if target is None or not target[2].startswith("data:image/"):
                continue
            result = await asyncio.to_thread(broker.compress, target[2], session, hint="image", query=query)
            if result["content"] == target[2]:
                continue
            rendered = result["content"]
            if target[1] == "data":
                header, rendered = rendered.split(",", 1)
                target[0]["media_type"] = header[5:].split(";", 1)[0]
            target[0][target[1]] = rendered
            marker_type = "input_text" if block.get("type") == "input_image" else "text"
            markers.append({"type": marker_type, "text": f"UTK original image: {result['recovery_id']}; use utk_retrieve"})
            changed += 1
        content.extend(markers)
    return changed


def tool_text_fields(container, key):
    """Select only text inside known tool results; preserve multimodal items."""
    content = container.get(key)
    if isinstance(content, str):
        return [(container, key)]
    if isinstance(content, list):
        return [(part, "text") for part in content if isinstance(part, dict)
                and part.get("type") in {"text", "input_text"} and isinstance(part.get("text"), str)]
    return []


class UsageObserver:
    """Bounded side observation; wire bytes are always forwarded unchanged."""
    def __init__(self, sse: bool):
        self.sse = sse
        self.declared_sse = sse
        self.buffer = b""
        self.usage: dict = {}
        self.usage_objects = 0
        self.terminal_events = 0
        self.bytes_seen = 0
        self.data_lines = 0
        self.json_events = 0
        self.parse_errors = 0
        self.cr_seen = 0
        self.lf_seen = 0
        self.disabled = False
        self.event_data = []
        self.failed = False

    def feed(self, chunk: bytes):
        self.bytes_seen += len(chunk)
        self.cr_seen += chunk.count(b"\r")
        self.lf_seen += chunk.count(b"\n")
        if self.disabled:
            return
        self.buffer += chunk
        # Some compatible upstreams stream SSE with a missing or generic MIME
        # type. Detect only unambiguous SSE field prefixes; wire bytes unchanged.
        if not self.sse and not self.json_events:
            prefix = self.buffer.lstrip(b"\xef\xbb\xbf \t\r\n")
            if prefix.startswith((b"data:", b"event:", b":")):
                self.sse = True
                self.buffer = prefix
        if self.sse:
            while b"\n" in self.buffer:
                line, self.buffer = self.buffer.split(b"\n", 1)
                line = line.rstrip(b"\r")
                if line.startswith(b"data:"):
                    self.data_lines += 1
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
                self.json_events += 1
                response = data.get("response", data.get("message", data))
                self.usage_objects += int(isinstance(response, dict) and isinstance(response.get("usage"), dict))
                self.terminal_events += int(data.get("type") in {"response.completed", "response.done", "response.failed", "message_stop"})
                self.usage.update(usage_fields(data))
                if data.get("type") in {"error", "response.failed", "response.incomplete"} or data.get("error"):
                    self.failed = True
        except (ValueError, TypeError, AttributeError):
            self.parse_errors += 1

    def finish(self):
        if not self.sse and not self.disabled:
            self.parse(self.buffer)


def create_proxy(upstream: str | None = None, home=None, transport=None) -> FastAPI:
    root = home or default_home()
    proxy_instance_id = instance_id(ensure_session_token(root))
    upstream = upstream or os.environ.get("UTK_UPSTREAM_URL", "https://api.openai.com/v1")
    client_name = os.environ.get("UTK_CLIENT", "unknown")
    store = Store(root / "metrics.sqlite3")
    submission_limit = os.environ.get("UTK_MAX_MODEL_REQUESTS")

    def may_submit():
        if submission_limit is None:
            return True
        from .budgets import consume_submission
        return consume_submission(root, int(submission_limit))

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
        return {"status": "ok", "engine": "utk-native",
                "route_id": hashlib.sha256(upstream.encode()).hexdigest(),
                "instance_id": proxy_instance_id}

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
    async def forward(path: str, request: Request):
        if request.method == "POST" and not may_submit():
            return JSONResponse({"error": {"message": "UTK live verification request budget exhausted"}}, status_code=429)
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
        observer = UsageObserver("text/event-stream" in response.headers.get("content-type", "").lower())
        metadata["upstream_status"] = response.status_code
        metadata["method"] = request.method

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
                metadata["usage_observation"] = {
                    "status": "observed" if observer.usage else "observer_limit" if observer.disabled else "not_observed",
                    "usage_objects": observer.usage_objects,
                    "terminal_events": observer.terminal_events,
                    "sse_content_type": observer.declared_sse,
                    "sse_detected": observer.sse,
                    "bytes_seen": observer.bytes_seen,
                    "data_lines": observer.data_lines,
                    "json_events": observer.json_events,
                    "parse_errors": observer.parse_errors,
                    "cr_seen": observer.cr_seen,
                    "lf_seen": observer.lf_seen,
                }
                store.add(kind="input" if request.method == "POST" else "transport", client=client_name, model=model,
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
                    if not may_submit():
                        await socket.send_json({"type": "error", "error": {"message": "UTK live verification request budget exhausted"}})
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
            # A client disconnect can cancel the enclosing ASGI task before
            # the receive loop observes its disconnect frame (reproducible
            # with Starlette's TestClient on macOS).  Child cleanup must not
            # leak that cancellation back through the WebSocket context.
            with suppress(asyncio.CancelledError):
                await asyncio.gather(*tasks, return_exceptions=True)
            with suppress(asyncio.CancelledError, ConnectionClosed):
                await remote.close()
            try:
                await socket.close(code=remote.close_code if remote.close_code in {1000, 1001, 1008, 1011, 1013} else 1011)
            except (RuntimeError, WebSocketDisconnect):
                pass

    return app
