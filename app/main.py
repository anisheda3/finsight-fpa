"""FastAPI app entrypoint."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from agents.hooks import set_redis_client
from agents.memory import init_memory
from app.api.routers import (
    actuals, forecasts, hitl, insights, variances, webhooks,
)
from app.core.config import get_settings
from app.core.db import close_db, get_pool, init_db
from app.core.logging import configure_logging
from app.core.redis import init_redis

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    configure_logging(s.log_level)
    pool = await init_db(s.postgres_url)
    init_memory(pool)
    set_redis_client(init_redis(s.redis_url))
    logger.info("FinSight API up env=%s", s.app_env)
    yield
    await close_db()


app = FastAPI(title="FinSight FP&A AI", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


# Correlation-ID middleware (per spec "production standards")
@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    cid = request.headers.get("x-correlation-id") or str(uuid.uuid4())
    request.state.correlation_id = cid
    response = await call_next(request)
    response.headers["x-correlation-id"] = cid
    return response


# Routers
app.include_router(actuals.router)
app.include_router(forecasts.router)
app.include_router(variances.router)
app.include_router(insights.router)
app.include_router(hitl.router)
app.include_router(webhooks.router)


@app.get("/api/v1/health")
async def health() -> dict[str, Any]:
    s = get_settings()
    pool = get_pool()
    db_ok = False
    if pool is not None:
        try:
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            db_ok = True
        except Exception:
            db_ok = False
    return {
        "status": "ok",
        "env": s.app_env,
        "db": db_ok,
        "temporal": s.temporal_address,
        "redis": s.redis_url,
    }


# WebSocket: live workflow status (spec requires /ws/workflow/{workflow_id})
@app.websocket("/ws/workflow/{workflow_id}")
async def ws_workflow(ws: WebSocket, workflow_id: str):
    await ws.accept()
    from app.core.redis import get_client
    client = get_client()
    pubsub = None
    try:
        if client is not None:
            pubsub = client.pubsub()
            pubsub.subscribe(f"workflow:{workflow_id}", "agent_activity:all")
        # Send initial hello
        await ws.send_json({"event": "subscribed", "workflow_id": workflow_id})
        while True:
            if pubsub is None:
                await asyncio.sleep(2)
                await ws.send_json({"event": "heartbeat"})
                continue
            msg = pubsub.get_message(timeout=1.0)
            if msg and msg.get("type") == "message":
                try:
                    data = msg["data"]
                    if isinstance(data, bytes): data = data.decode()
                    await ws.send_json(json.loads(data))
                except Exception:
                    await ws.send_text(str(msg.get("data")))
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        return
    finally:
        if pubsub is not None:
            try: pubsub.close()
            except Exception: pass
