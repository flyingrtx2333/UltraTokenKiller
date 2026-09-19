"""One authenticated local broker owns all recoverable originals."""
from __future__ import annotations

import secrets
import asyncio

import httpx
from fastapi import APIRouter, HTTPException, Request

from .compression import compress_content
from .config import Settings, default_home
from .recovery import RecoveryUnavailable, RecoveryVault


def broker_router(vault: RecoveryVault, token: str, home=None):
    router = APIRouter()

    @router.post("/api/v1/internal/tool-events")
    async def tool_events(request: Request):
        from pydantic import ValidationError
        from .tool_events import ToolEvent
        from .store import Store
        authenticate(request)
        body = await read_body(request, require_session=False)
        try:
            event = ToolEvent.model_validate(body).model_dump(exclude_none=True)
        except ValidationError:
            raise HTTPException(422, "Invalid tool event metadata") from None
        event["metadata"]["external_id"] = event["metadata"]["execution_id"]
        store = Store((home or default_home()) / "metrics.sqlite3")
        event_id = await asyncio.to_thread(store.add, **event)
        return {"id": event_id}

    def authenticate(request: Request):
        if request.headers.get("origin"):
            raise HTTPException(403, "Recovery is not available to browser origins")
        if not secrets.compare_digest(request.headers.get("x-utk-token", ""), token):
            raise HTTPException(403, "Invalid broker token")

    async def read_body(request, require_session=True):
        body = bytearray()
        async for part in request.stream():
            body.extend(part)
            if len(body) > 16 * 1024 * 1024:
                raise HTTPException(413, "Compression input exceeds broker budget")
        import json
        try:
            data = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(422, "Invalid JSON")
        if not isinstance(data, dict) or (require_session and (not isinstance(data.get("session"), str) or not 1 <= len(data["session"]) <= 256)):
            raise HTTPException(422, "A bounded session identifier is required")
        return data

    @router.post("/api/v1/internal/compress")
    async def compress(request: Request):
        authenticate(request)
        data = await read_body(request)
        if not isinstance(data.get("content"), str) or data.get("profile", "safe") not in {"safe", "aggressive", "off"}:
            raise HTTPException(422, "Invalid compression input")
        if data.get("hint") is not None and not isinstance(data["hint"], str) or not isinstance(data.get("query", ""), str):
            raise HTTPException(422, "Invalid content hint or query")
        result = await asyncio.to_thread(compress_content, data["content"], session=data["session"], vault=vault,
                                        profile=data.get("profile", "safe"), hint=data.get("hint"), query=data.get("query", "")[:16000], home=home)
        return {"content": result.content, **result.metadata()}

    @router.post("/api/v1/internal/retrieve")
    async def retrieve(request: Request):
        authenticate(request)
        data = await read_body(request)
        try:
            return vault.retrieve(data["session"], data["handle"], int(data.get("offset", 0)), int(data.get("limit", 32000)))
        except RecoveryUnavailable as error:
            raise HTTPException(410, str(error)) from error
        except (KeyError, ValueError, TypeError):
            raise HTTPException(422, "Invalid recovery request")

    @router.get("/api/v1/recovery/status")
    async def status():
        return vault.status()

    return router


class BrokerClient:
    def __init__(self, home=None):
        self.home = home or default_home()
        self.settings = Settings.load(self.home)
        self.url = f"http://127.0.0.1:{self.settings.dashboard_port}"

    def headers(self):
        token = (self.home / "session-token").read_text(encoding="ascii").strip()
        return {"X-UTK-Token": token}

    def client(self, timeout=10):
        from .local_transport import broker_socket
        path = broker_socket(self.home)
        # Existing HTTP-only services remain usable; an advertised socket never
        # silently falls back to TCP when its access policy rejects a connection.
        transport = httpx.HTTPTransport(uds=str(path)) if path and path.exists() else None
        return httpx.Client(timeout=timeout, trust_env=False, transport=transport)

    def compress(self, text: str, session: str, hint=None, query=""):
        if not session:
            return {"content": text, "fallback": "missing_session", "saved_tokens": 0}
        try:
            with self.client() as client:
                response = client.post(self.url+"/api/v1/internal/compress", headers=self.headers(),
                                       json={"content": text, "session": session, "hint": hint, "query": query, "profile": self.settings.profile})
                response.raise_for_status()
                return response.json()
        except (OSError, httpx.HTTPError, ValueError):
            return {"content": text, "fallback": "broker_unavailable", "saved_tokens": 0}

    def retrieve(self, session: str, handle: str, offset=0, limit=32000):
        with self.client() as client:
            response = client.post(self.url+"/api/v1/internal/retrieve", headers=self.headers(),
                                   json={"session": session, "handle": handle, "offset": offset, "limit": limit})
            if response.status_code == 410:
                raise RecoveryUnavailable(response.json()["detail"])
            response.raise_for_status()
            return response.json()
