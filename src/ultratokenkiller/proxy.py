"""UTK's native HTTP/SSE proxy. One configured upstream per local listener."""
from __future__ import annotations

import json
import logging
import os
import time
import asyncio
import copy
import uuid
import hashlib
import threading
from contextlib import asynccontextmanager, suppress
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse

from .config import Settings, default_home
from .identity import ensure_session_token, instance_id
from .engines import apply_response_style
from .broker import BrokerClient
from .read_lifecycle import classify_reads, frozen_prefix_message_count, tool_output_text_fields
from .prefix_guard import PrefixGuard
from .store import Store
from .token_count import count_text
from .pricing import event_cost_estimates

logger = logging.getLogger(__name__)
WEBSOCKET_CONNECT_ATTEMPTS = 3
WEBSOCKET_CONNECT_RETRY_BASE_SECONDS = 0.1


def websocket_proxy_policy(url: str):
    """Let websockets discover proxies except for local upstream routes."""
    return None if urlparse(url).hostname in {"127.0.0.1", "localhost", "::1"} else True

HOP_HEADERS = {"host", "content-length", "connection", "transfer-encoding", "keep-alive", "upgrade", "proxy-authorization", "proxy-authenticate", "te", "trailer"}
MODEL_ENDPOINTS = {"responses", "chat/completions", "messages"}
INPUT_COMPRESSION_TIMEOUT_SECONDS = 10.0


class CompressionBreaker:
    """Keep repeated local compression failures off the model request path."""

    def __init__(self, threshold=3, cooldown_seconds=30.0):
        self.threshold = threshold
        self.cooldown_seconds = cooldown_seconds
        self.failures = 0
        self.open_until = 0.0
        self.lock = threading.Lock()

    def is_open(self):
        with self.lock:
            return time.monotonic() < self.open_until

    def failure(self):
        with self.lock:
            self.failures += 1
            if self.failures >= self.threshold:
                self.open_until = time.monotonic() + self.cooldown_seconds
                self.failures = 0

    def success(self):
        with self.lock:
            self.failures = 0


def request_class(method: str, path: str) -> str:
    route = path.strip("/")
    if route.startswith("v1/"):
        route = route[3:]
    if method.upper() == "POST" and route in MODEL_ENDPOINTS:
        return "model"
    if route in {"api/show", "models"} or route.endswith("/models"):
        return "probe"
    return "transport"


def error_category(status: int, body: bytes) -> str | None:
    if status < 400:
        return None
    try:
        payload = json.loads(body)
        error = payload.get("error", payload) if isinstance(payload, dict) else {}
        if isinstance(error, dict):
            for key in ("code", "type"):
                value = error.get(key)
                if isinstance(value, str) and 1 <= len(value) <= 80:
                    return value
    except (ValueError, TypeError):
        pass
    return {400: "invalid_request", 401: "authentication", 403: "authentication",
            404: "not_found", 429: "rate_limit"}.get(status, "upstream_error")


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


async def compress_request(payload, settings, root, session, model=None, *,
                           frozen_message_count=0, allow_cold=False,
                           forwarded_prefix=None):
    result = copy.deepcopy(payload)
    before_count = count_text(json.dumps(payload, ensure_ascii=False), model)
    metadata = {"estimated_input_before": before_count.value,
                "estimator": before_count.method,
                "token_estimate_exact_for_model": before_count.exact_for_model,
                "estimated_saved_tokens_basis": "estimated_prompt_delta",
                "cost_estimate_status": "unavailable_no_price_catalog",
                "changed_tool_results": 0,
                "candidate_tool_results": 0, "tool_skip_reasons": {},
                "image_skip_reasons": {},
                "read_lifecycle": {"reads_total": 0, "reads_stale": 0,
                                   "reads_superseded": 0, "reads_fresh": 0,
                                   "transformed": 0, "skipped_small": 0,
                                   "fresh_passthrough": 0,
                                   "bytes_before": 0, "bytes_after": 0}}
    if not session:
        metadata["compression_fallback"] = "missing_session"
    else:
        broker = BrokerClient(root)
        items = result.get("messages", result.get("input", []))
        if isinstance(items, list):
            if forwarded_prefix is not None:
                items[:len(forwarded_prefix)] = copy.deepcopy(forwarded_prefix)
            frozen_message_count = max(
                frozen_message_count,
                0 if allow_cold else frozen_prefix_message_count(items),
            )
            query = next((user_text(item.get("content")) for item in reversed(items)
                          if isinstance(item, dict) and item.get("role") == "user"), "")
            read_fields = set()
            lifecycle_fields = set()
            classifications = classify_reads(
                items, frozen_message_count=frozen_message_count,
                compress_superseded=True,
            )
            lifecycle_stats = metadata["read_lifecycle"]
            lifecycle_stats["reads_total"] = len(classifications)
            lifecycle_stats["reads_stale"] = sum(item.state == "stale" for item in classifications)
            lifecycle_stats["reads_superseded"] = sum(item.state == "superseded" for item in classifications)
            lifecycle_stats["reads_fresh"] = sum(item.state == "fresh" for item in classifications)
            by_call_id = {item.call_id: item for item in classifications}
            for call_id, container, key in tool_output_text_fields(items[frozen_message_count:]):
                lifecycle = by_call_id.get(call_id)
                if lifecycle:
                    read_fields.add((id(container), key))
                original = container[key]
                if not lifecycle:
                    continue
                if lifecycle.state == "fresh":
                    lifecycle_stats["fresh_passthrough"] += 1
                    continue
                if len(original.encode("utf-8")) < 512:
                    lifecycle_stats["skipped_small"] += 1
                    continue
                if lifecycle.state == "stale":
                    marker = (f"[UTK: read of {lifecycle.path} is stale after a later edit or write; "
                              "re-read the file for current contents.]")
                else:
                    marker = (f"[UTK: read of {lifecycle.path} was superseded by a later read "
                              "that covers this range; re-read the file if needed.]")
                try:
                    pinned = await asyncio.to_thread(
                        broker.pin_transform, original, marker, session,
                        f"read_lifecycle_{lifecycle.state}",
                    )
                except Exception:
                    pinned = {"content": original}
                rendered = pinned.get("content", original)
                if rendered != original:
                    container[key] = rendered
                    lifecycle_fields.add((id(container), key))
                    metadata["candidate_tool_results"] += 1
                    metadata["changed_tool_results"] += 1
                    lifecycle_stats["transformed"] += 1
                    lifecycle_stats["bytes_before"] += len(original.encode("utf-8"))
                    lifecycle_stats["bytes_after"] += len(rendered.encode("utf-8"))
            for item in items[frozen_message_count:]:
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
                    if (id(block), key) in read_fields:
                        if (id(block), key) not in lifecycle_fields:
                            metadata["candidate_tool_results"] += 1
                        continue
                    metadata["candidate_tool_results"] += 1
                    try:
                        compressed, reason = await compress_tool_value(block[key], broker, session, query)
                    except Exception:
                        compressed, reason = block[key], "compression_error"
                    if compressed != block[key]:
                        metadata["changed_tool_results"] += 1
                        block[key] = compressed
                    else:
                        reasons = metadata["tool_skip_reasons"]
                        reasons[reason] = reasons.get(reason, 0) + 1
            metadata["changed_images"] = await compress_inline_images(
                items[frozen_message_count:], broker, session, query,
                metadata["image_skip_reasons"])
            if (not metadata["candidate_tool_results"] and not metadata["changed_images"]
                    and not metadata["tool_skip_reasons"] and not metadata["image_skip_reasons"]):
                metadata["tool_skip_reasons"] = {"no_tool_result": 1}
            skip_reasons = (metadata["tool_skip_reasons"], metadata["image_skip_reasons"])
            if any(reasons.get("compression_error") for reasons in skip_reasons):
                metadata["compression_fallback"] = "compression_error"
            elif any(reasons.get("broker_unavailable") for reasons in skip_reasons):
                metadata["compression_fallback"] = "broker_unavailable"
    after_count = count_text(json.dumps(result, ensure_ascii=False), model)
    metadata["estimated_input_after"] = after_count.value
    if after_count.method != before_count.method:
        metadata["estimator_after"] = after_count.method
    metadata["token_estimate_exact_for_model"] = (
        before_count.exact_for_model and after_count.exact_for_model
    )
    metadata["estimated_saved_tokens"] = max(0, metadata["estimated_input_before"]-metadata["estimated_input_after"])
    return result, metadata


def tool_skip_reason(value: object) -> str:
    allowed = {"already_compressed", "broker_unavailable", "disabled", "missing_session",
               "not_smaller_or_memory_full", "compressor_not_ready", "compression_error"}
    return value if isinstance(value, str) and value in allowed else "unchanged"


async def compress_tool_value(text: str, broker: BrokerClient, session: str, query: str) -> tuple[str, str | None]:
    """Compress Hermes terminal output without discarding its status envelope."""
    if text.startswith("UTK_RETRIEVED_ORIGINAL\n"):
        return text, "restored_original"
    try:
        envelope = json.loads(text)
    except (ValueError, TypeError):
        envelope = None
    fallbacks = []
    if isinstance(envelope, dict):
        changed = False
        for key in ("output", "stdout", "stderr"):
            value = envelope.get(key)
            if not isinstance(value, str) or not value:
                continue
            if value.startswith("UTK_RETRIEVED_ORIGINAL\n"):
                continue
            compressed = await asyncio.to_thread(broker.compress, value, session, query=query)
            if compressed["content"] != value:
                envelope[key] = compressed["content"]
                changed = True
            else:
                fallbacks.append(tool_skip_reason(compressed.get("fallback")))
        if changed:
            return json.dumps(envelope, ensure_ascii=False, separators=(",", ":")), None
    compressed = await asyncio.to_thread(broker.compress, text, session, query=query)
    if compressed["content"] != text:
        return compressed["content"], None
    for reason in ("broker_unavailable", "already_compressed"):
        if reason in fallbacks:
            return text, reason
    return text, tool_skip_reason(compressed.get("fallback"))


def user_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(part.get("text", "") for part in content if isinstance(part, dict)
                         and part.get("type") in {"text", "input_text"} and isinstance(part.get("text"), str))
    return ""


async def compress_inline_images(items, broker, session, query, image_skip_reasons=None):
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
            try:
                result = await asyncio.to_thread(broker.compress, target[2], session, hint="image", query=query)
            except Exception:
                if image_skip_reasons is not None:
                    image_skip_reasons["compression_error"] = image_skip_reasons.get("compression_error", 0) + 1
                continue
            fallback = result.get("fallback") if isinstance(result, dict) else None
            if isinstance(fallback, str) and image_skip_reasons is not None:
                image_skip_reasons[fallback] = image_skip_reasons.get(fallback, 0) + 1
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
    compression_breaker = CompressionBreaker()
    prefix_guard = PrefixGuard()
    submission_limit = os.environ.get("UTK_MAX_MODEL_REQUESTS")

    async def guarded_compress(payload, settings, session, model, protocol):
        # A pre-existing provider prefix can include system instructions. Once a
        # session is observed, changing them would defeat prefix protection.
        styled = payload if session else apply_response_style(
            payload, settings.caveman, protocol=protocol)

        async def transform(source, frozen, cold, forwarded_prefix):
            return await compress_request(
                source, settings, root, session, model,
                frozen_message_count=frozen, allow_cold=cold,
                forwarded_prefix=forwarded_prefix,
            )

        result, estimates = await prefix_guard.process(
            styled, session=session, protocol=protocol, model=model,
            transform=transform,
        )
        estimates["response_style"] = settings.caveman
        estimates["response_style_applied"] = styled != payload
        if session and settings.caveman != "off":
            estimates["response_style_skipped"] = "cache_prefix"
        return result, estimates

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
        classification = request_class(request.method, path)
        if classification == "model" and not may_submit():
            return JSONResponse({"error": {"message": "UTK live verification request budget exhausted"}}, status_code=429)
        started = time.perf_counter()
        body = await request.body()
        metadata: dict = {"engine": "utk-native", "transport": "http",
                          "request_class": classification, "path": "/" + path.lstrip("/")}
        model = None
        settings = Settings.load(root)
        session = request.headers.get("x-utk-session-id", "")
        if len(session) > 256:
            session = ""
        metadata["request_id"] = uuid.uuid4().hex
        if session:
            metadata["session_id"] = hashlib.sha256(session.encode()).hexdigest()
        if classification == "model" and not compression_breaker.is_open():
            try:
                payload = json.loads(body)
                if isinstance(payload, dict):
                    model = payload.get("model")
                    # Style overhead is included before the compression estimate.
                    protocol = ("anthropic" if path.rstrip("/").endswith("messages") else
                                "openai-chat" if path.rstrip("/").endswith("chat/completions") else "openai")
                    compressed, estimates = await asyncio.wait_for(
                        guarded_compress(payload, settings, session, model, protocol),
                        timeout=INPUT_COMPRESSION_TIMEOUT_SECONDS)
                    metadata.update(estimates)
                    if compressed != payload:
                        body = json.dumps(compressed, ensure_ascii=False).encode("utf-8")
                    if metadata.get("compression_fallback") in {"broker_unavailable", "compression_error"}:
                        compression_breaker.failure()
                    else:
                        compression_breaker.success()
            except asyncio.TimeoutError:
                metadata["compression_fallback"] = "compression_timeout"
                compression_breaker.failure()
            except Exception:
                # Any optimization failure retains the exact original request bytes.
                metadata["compression_fallback"] = "compression_error"
                compression_breaker.failure()
        elif classification == "model":
            metadata["compression_fallback"] = "compression_circuit_open"
            try:
                original_payload = json.loads(body)
                if isinstance(original_payload, dict):
                    model = original_payload.get("model")
            except (ValueError, UnicodeDecodeError):
                pass
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
            store.add(kind="input" if classification == "model" else "transport",
                      client=client_name, model=model, success=False,
                      duration_ms=int((time.perf_counter()-started)*1000), metadata=metadata)
            return JSONResponse({"error": {"message": "UTK upstream connection failed"}}, status_code=502)
        observer = UsageObserver("text/event-stream" in response.headers.get("content-type", "").lower())
        metadata["upstream_status"] = response.status_code
        metadata["method"] = request.method

        async def stream():
            completed = False
            error_body = bytearray()
            try:
                async for chunk in response.aiter_bytes():
                    observer.feed(chunk)
                    if response.status_code >= 400 and len(error_body) < 65536:
                        error_body.extend(chunk[:65536 - len(error_body)])
                    yield chunk
                completed = True
            finally:
                await response.aclose()
                observer.finish()
                category = error_category(response.status_code, bytes(error_body))
                if observer.failed and category is None:
                    category = "upstream_stream_error"
                if category:
                    metadata["error_category"] = category
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
                saved_tokens = metadata.get("estimated_saved_tokens", 0)
                metadata.update(event_cost_estimates(
                    settings.model_pricing,
                    model,
                    client=client_name,
                    input_tokens=observer.usage.get("input_tokens"),
                    output_tokens=observer.usage.get("output_tokens"),
                    cached_tokens=observer.usage.get("cached_tokens"),
                    saved_tokens=saved_tokens,
                ))
                store.add(kind="input" if classification == "model" else "transport", client=client_name, model=model,
                          success=completed and response.is_success and not observer.failed,
                          duration_ms=int((time.perf_counter()-started)*1000),
                          saved_tokens=saved_tokens,
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
        session = socket.headers.get("x-utk-session-id", "")
        if len(session) > 256:
            session = ""
        responses_websocket = route.rstrip("/").endswith("responses")
        pending_requests: list[tuple[str | None, dict]] = []
        websocket_proxy = websocket_proxy_policy(url)
        for attempt in range(WEBSOCKET_CONNECT_ATTEMPTS):
            try:
                remote = await connect(url, additional_headers=headers, subprotocols=protocols or None,
                                       compression=None, max_size=16*1024*1024, max_queue=16,
                                       open_timeout=20, proxy=websocket_proxy)
                break
            except InvalidStatus as error:
                await socket.send_denial_response(JSONResponse({"error": "Upstream WebSocket handshake rejected"}, status_code=error.response.status_code))
                return
            except (OSError, asyncio.TimeoutError) as error:
                if attempt + 1 < WEBSOCKET_CONNECT_ATTEMPTS:
                    await asyncio.sleep(WEBSOCKET_CONNECT_RETRY_BASE_SECONDS * (2 ** attempt))
                    continue
                logger.warning("WebSocket upstream connection failed: %s", type(error).__name__)
                await socket.close(code=1013)
                return
            except Exception as error:
                logger.warning("WebSocket upstream connection failed: %s", type(error).__name__)
                await socket.close(code=1013)
                return
        await socket.accept(subprotocol=remote.subprotocol)
        async def to_upstream():
            try:
                while True:
                    message = await socket.receive()
                    if message["type"] == "websocket.disconnect":
                        return
                    text = message.get("text")
                    forwarded = text
                    if responses_websocket and isinstance(text, str):
                        try:
                            event = json.loads(text)
                        except (ValueError, TypeError):
                            event = None
                        if isinstance(event, dict) and event.get("type") == "response.create":
                            if not may_submit():
                                await socket.send_json({"type": "error", "error": {"message": "UTK live verification request budget exhausted"}})
                                return
                            response_payload = event.get("response")
                            model = response_payload.get("model") if isinstance(response_payload, dict) else None
                            metadata = {
                                "transport": "websocket",
                                "engine": "utk-native",
                                "request_class": "model",
                                "path": "/" + route.lstrip("/"),
                                "request_id": uuid.uuid4().hex,
                            }
                            if session:
                                metadata["session_id"] = hashlib.sha256(session.encode()).hexdigest()
                            if not compression_breaker.is_open() and isinstance(response_payload, dict):
                                try:
                                    settings = Settings.load(root)
                                    compressed, estimates = await asyncio.wait_for(
                                        guarded_compress(response_payload, settings, session,
                                                         model, "openai"),
                                        timeout=INPUT_COMPRESSION_TIMEOUT_SECONDS,
                                    )
                                    metadata.update(estimates)
                                    if compressed != response_payload:
                                        forwarded_event = dict(event)
                                        forwarded_event["response"] = compressed
                                        forwarded = json.dumps(forwarded_event, ensure_ascii=False)
                                    if metadata.get("compression_fallback") in {"broker_unavailable", "compression_error"}:
                                        compression_breaker.failure()
                                    else:
                                        compression_breaker.success()
                                except asyncio.TimeoutError:
                                    metadata["compression_fallback"] = "compression_timeout"
                                    compression_breaker.failure()
                                except Exception:
                                    metadata["compression_fallback"] = "compression_error"
                                    compression_breaker.failure()
                            else:
                                metadata["compression_fallback"] = (
                                    "compression_circuit_open" if compression_breaker.is_open()
                                    else "invalid_response_create"
                                )
                            pending_requests.append((model, metadata))
                    # Control frames such as response.cancel are transport events, not model calls.
                    await remote.send(forwarded if forwarded is not None else message["bytes"])
            except (WebSocketDisconnect, ConnectionClosed):
                return
        async def to_client():
            async for message in remote:
                if isinstance(message, str):
                    await socket.send_text(message)
                    try:
                        event = json.loads(message)
                        event_type = event.get("type")
                        if event_type in {"response.completed", "response.failed", "response.incomplete", "response.cancelled", "error"}:
                            model, metadata = pending_requests.pop(0) if pending_requests else (None, {})
                            response = event.get("response")
                            if isinstance(response, dict) and response.get("id"):
                                metadata["external_id"] = response["id"]
                            metadata.update({"transport": "websocket", "engine": "utk-native"})
                            if event_type in {"response.failed", "error"}:
                                metadata["error_category"] = "upstream_websocket_error"
                            elif event_type == "response.incomplete":
                                metadata["error_category"] = "upstream_incomplete"
                            elif event_type == "response.cancelled":
                                metadata["error_category"] = "upstream_cancelled"
                            succeeded = event_type == "response.completed"
                            saved_tokens = metadata.get("estimated_saved_tokens", 0) if succeeded else 0
                            metadata["estimated_saved_tokens"] = saved_tokens
                            usage = usage_fields(event)
                            metadata.update(event_cost_estimates(
                                Settings.load(root).model_pricing,
                                model,
                                client=client_name,
                                input_tokens=usage.get("input_tokens"),
                                output_tokens=usage.get("output_tokens"),
                                cached_tokens=usage.get("cached_tokens"),
                                saved_tokens=saved_tokens,
                            ))
                            store.add(kind="input", client=client_name, model=model,
                                      success=succeeded,
                                      saved_tokens=saved_tokens,
                                      metadata=metadata, **usage)
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
            for model, metadata in pending_requests:
                metadata.update({
                    "error_category": "websocket_interrupted",
                    "estimated_saved_tokens": 0,
                })
                store.add(kind="input", client=client_name, model=model,
                          success=False, saved_tokens=0, metadata=metadata)
            pending_requests.clear()
            with suppress(asyncio.CancelledError, ConnectionClosed):
                await remote.close()
            try:
                await socket.close(code=remote.close_code if remote.close_code in {1000, 1001, 1008, 1011, 1013} else 1011)
            except (RuntimeError, WebSocketDisconnect):
                pass

    return app
