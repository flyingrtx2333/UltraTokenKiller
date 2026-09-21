from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from urllib.parse import urlparse
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings, default_home
from .integrations import CodexAdapter, HermesAdapter
from .identity import ensure_session_token, instance_id
from .runtime import headroom_health, headroom_ports, restart_managed_headrooms
from .store import Store

home = default_home()
settings = Settings.load(home)
store = Store(home / "metrics.sqlite3")
home.mkdir(parents=True, exist_ok=True)
session_token = ensure_session_token(home)
service_instance_id = instance_id(session_token)

app = FastAPI(title="UltraTokenKiller", version="0.2.0", docs_url=None, redoc_url=None)
from .broker import broker_router
from .recovery import RecoveryVault

recovery_vault = RecoveryVault(settings.recovery_capacity_bytes, settings.recovery_idle_seconds)
app.include_router(broker_router(recovery_vault, session_token, home))


@app.get("/api/v1/capabilities")
def api_capabilities():
    from .benchmark import capability_report
    return capability_report()


@app.get("/api/v1/benchmarks/latest")
def api_benchmark_latest(kind: str = Query("compression", pattern="^(compression|response)$")):
    path = home / "reports" / f"{kind}-latest.json"
    if not path.is_file():
        return JSONResponse({"schema_version": 1, "status": "not_run", "kind": kind}, status_code=404)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise HTTPException(500, "Stored benchmark report is invalid") from None
    if not isinstance(data, dict) or data.get("status") != "completed":
        raise HTTPException(500, "Stored benchmark report is invalid")
    return data


def clients() -> list[dict]:
    return [CodexAdapter().detect().json(), HermesAdapter().detect().json()]


async def headroom_stats() -> dict:
    return {"instances": [], "engine": "utk-native"}


def require_write(request: Request, x_utk_token: str | None) -> None:
    origin = request.headers.get("origin")
    if origin:
        parsed = urlparse(origin)
        host = request.headers.get("host", "")
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.netloc != host:
            raise HTTPException(403, "Origin not allowed")
    if x_utk_token != session_token:
        raise HTTPException(403, "Invalid local session token")


@app.get("/api/v1/health")
def api_health() -> dict:
    return {"status": "ok", "version": app.version, "instance_id": service_instance_id}


@app.get("/api/v1/status")
async def api_status() -> dict:
    managed_values = [bool(item.get("managed", True)) for item in settings.clients.values()]
    return {
        "service": True,
        "headroom": bool(headroom_ports(settings)) and all(headroom_health(settings, port) for port in headroom_ports(settings)),
        "rtk": True,
        "engine": "utk-native",
        "parity_certified": False,
        "recovery": recovery_vault.status(),
        "profile": settings.profile,
        "profile_controlled": all(managed_values) if managed_values else settings.headroom_managed,
        "caveman": settings.caveman,
        "auto_start": settings.auto_start,
        "ports": {"dashboard": settings.dashboard_port, "headroom": settings.headroom_port, "headroom_instances": headroom_ports(settings)},
        "clients": clients(),
    }


@app.get("/api/v1/metrics")
async def api_metrics(hours: int = Query(24, ge=1, le=24 * 90), client: str | None = None, model: str | None = None) -> dict:
    headroom = await headroom_stats()
    _ingest_headroom(headroom)
    store.prune(settings.retention_days)
    local = store.summary(hours, client, model)
    rtk = _rtk_summary()
    return {"local": local, "headroom": headroom, "rtk": rtk, "period_hours": hours}


@app.get("/api/v1/events")
async def api_events(limit: int = Query(100, ge=1, le=500)) -> list[dict]:
    headroom = await headroom_stats()
    _ingest_headroom(headroom)
    return store.events(limit)


def _ingest_headroom(headroom: dict) -> None:
    for instance in headroom.get("instances", []):
      port = instance["port"]
      for index, item in enumerate(instance["stats"].get("recent_requests", [])):
        timestamp = item.get("timestamp")
        try:
            from datetime import datetime
            created = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()
        except (AttributeError, ValueError):
            created = None
        event_id = f"{port}:{item.get('request_id') or f'recent-{index}-{timestamp}'}"
        store.add(
            kind="headroom",
            client=item.get("provider", "model"),
            success=item.get("token_accounting_status") != "failed",
            model=item.get("model"),
            input_tokens=item.get("input_tokens_optimized"),
            output_tokens=item.get("output_tokens"),
            saved_tokens=item.get("tokens_saved", 0),
            duration_ms=round(item.get("total_latency_ms", 0)),
            metadata={"external_id": event_id, "proxy_port": port},
        )
        if created:
            with store.connect() as db:
                db.execute("UPDATE events SET created_at=? WHERE kind='headroom' AND json_extract(metadata, '$.external_id')=?", (created, event_id))


def _rtk_summary() -> dict:
    return {"engine": "utk-native"}


@app.get("/api/v1/config")
def api_config() -> dict:
    return {"schema_version": 2, "input": {"profile": settings.profile}, "tools": {"enabled": settings.tools_enabled},
            "response": {"mode": settings.caveman}, "profile": settings.profile, "caveman": settings.caveman,
            "auto_start": settings.auto_start, "session_token": session_token}


@app.patch("/api/v1/config")
async def update_config(request: Request, x_utk_token: str | None = Header(None)) -> dict:
    global settings
    from dataclasses import replace
    require_write(request, x_utk_token)
    pending = replace(settings)
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(422, "Configuration must be an object")
    if "input" in data:
        if not isinstance(data["input"], dict):
            raise HTTPException(422, "input must be an object")
        data["profile"] = data["input"].get("profile", pending.profile)
    if "response" in data:
        if not isinstance(data["response"], dict):
            raise HTTPException(422, "response must be an object")
        data["caveman"] = data["response"].get("mode", pending.caveman)
    if "profile" in data:
        status = await api_status()
        if not status["profile_controlled"]:
            raise HTTPException(409, "Legacy external proxy is not managed by UTK; reconnect to the native engine")
        if not isinstance(data["profile"], str) or data["profile"] not in {"safe", "aggressive", "off"}:
            raise HTTPException(422, "Unknown profile")
        pending.profile = data["profile"]
    if "caveman" in data:
        if not isinstance(data["caveman"], str) or data["caveman"] not in {"lite", "full", "ultra", "off", "wenyan-lite", "wenyan-full", "wenyan-ultra"}:
            raise HTTPException(422, "Unknown caveman mode")
        pending.caveman = data["caveman"]
    if "tools" in data:
        tools_config = data["tools"]
        if not isinstance(tools_config, dict) or not isinstance(tools_config.get("enabled"), bool):
            raise HTTPException(422, "tools.enabled must be a boolean")
        pending.tools_enabled = tools_config["enabled"]
    pending.save(home)
    settings = pending
    return await api_status()


@app.post("/api/v1/clients/{name}/{action}")
def update_client(name: str, action: str, request: Request, x_utk_token: str | None = Header(None)) -> dict:
    require_write(request, x_utk_token)
    adapters = {"codex": CodexAdapter(), "hermes": HermesAdapter()}
    if name not in adapters or action not in {"enable", "disable"}:
        raise HTTPException(404, "Unknown client action")
    adapter = adapters[name]
    port = int(settings.clients.get(name, {}).get("proxy_port", settings.headroom_port))
    state = adapter.enable(port, home / "backups", settings.caveman) if action == "enable" else adapter.disable()
    return state.json()


@app.get("/api/v1/stream")
async def stream(request: Request, hours: int = Query(24, ge=1, le=24 * 90)):
    async def events():
        while not await request.is_disconnected():
            payload = {"status": await api_status(), "metrics": await api_metrics(hours)}
            yield f"event: snapshot\ndata: {json.dumps(payload)}\n\n"
            await asyncio.sleep(5)
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


static = Path(__file__).parent / "static"
if static.exists():
    app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")
    brand = static / "brand"
    if brand.exists():
        app.mount("/brand", StaticFiles(directory=brand), name="brand")


@app.get("/dashboard")
@app.get("/")
def dashboard():
    index = static / "index.html"
    return FileResponse(index) if index.exists() else JSONResponse({"detail": "Dashboard assets are not installed"}, status_code=503)
