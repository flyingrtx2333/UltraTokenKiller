"""UTK's native HTTP/SSE proxy. One configured upstream per local listener."""
from __future__ import annotations

import json
import os
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .config import Settings, default_home
from .engines import apply_response_style, compress_request
from .store import Store

HOP_HEADERS = {"host", "content-length", "connection", "transfer-encoding", "keep-alive", "upgrade", "proxy-authorization", "proxy-authenticate", "te", "trailer"}


def usage_fields(payload: dict) -> dict:
    response = payload.get("response", payload)
    usage = response.get("usage") if isinstance(response, dict) else None
    if not isinstance(usage, dict):
        return {}
    details = usage.get("input_tokens_details", usage.get("prompt_tokens_details", {})) or {}
    return {"input_tokens": usage.get("input_tokens", usage.get("prompt_tokens")),
            "output_tokens": usage.get("output_tokens", usage.get("completion_tokens")),
            "cached_tokens": details.get("cached_tokens")}


class UsageObserver:
    """Bounded side observation; wire bytes are always forwarded unchanged."""
    def __init__(self, sse: bool):
        self.sse = sse
        self.buffer = b""
        self.usage: dict = {}
        self.disabled = False

    def feed(self, chunk: bytes):
        if self.disabled:
            return
        self.buffer += chunk
        if self.sse:
            while b"\n" in self.buffer:
                line, self.buffer = self.buffer.split(b"\n", 1)
                if line.startswith(b"data:"):
                    self.parse(line[5:].strip())
        if len(self.buffer) > 2 * 1024 * 1024:
            self.buffer = b""
            self.disabled = True

    def parse(self, value: bytes):
        try:
            data = json.loads(value)
            if isinstance(data, dict):
                self.usage.update(usage_fields(data))
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
        if request.method == "POST" and path.rstrip("/").endswith(("responses", "chat/completions")):
            try:
                payload = json.loads(body)
                if isinstance(payload, dict):
                    model = payload.get("model")
                    # Style overhead is included before the compression estimate.
                    styled = apply_response_style(payload, settings.caveman)
                    compressed, estimates = compress_request(styled, settings.profile)
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
        headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP_HEADERS}
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
                          success=completed and response.is_success,
                          duration_ms=int((time.perf_counter()-started)*1000),
                          saved_tokens=metadata.get("estimated_saved_tokens", 0),
                          metadata=metadata, **observer.usage)

        response_headers = {k: v for k, v in response.headers.items()
                            if k.lower() not in HOP_HEADERS | {"content-encoding"}}
        return StreamingResponse(stream(), status_code=response.status_code, headers=response_headers)

    return app

