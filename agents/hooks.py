"""
Agent hooks — Redis stream emitters.

Spec requires at least 2 hooks:
    1. session_start_hook  → log period + data source to Redis
    2. tool_post_exec_hook → stream tool result to agent_activity:{agent_name}:{session_id}

Evaluator inspects these streams.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


# Lazy redis client (set by app.core.redis init)
_REDIS = None


def set_redis_client(client: Any) -> None:
    global _REDIS
    _REDIS = client


def _publish_safe(channel: str, payload: dict[str, Any]) -> None:
    if _REDIS is None:
        logger.debug("redis not configured; would emit %s -> %s", channel, payload)
        return
    try:
        # Support both sync-redis and aioredis-style: callers should ensure
        # they're using the right one.  For Redis Streams we use XADD with maxlen.
        _REDIS.xadd(channel, {"json": json.dumps(payload, default=str)}, maxlen=5000)
    except Exception as e:
        logger.warning("redis publish failed (%s): %s", channel, e)


def session_start_hook(
    *,
    agent_name: str,
    session_id: str,
    workflow_run_id: str | None = None,
    period: Any | None = None,
    data_source: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Emit session start event."""
    payload = {
        "event": "session_start",
        "agent_name": agent_name,
        "session_id": session_id,
        "workflow_run_id": workflow_run_id,
        "period": str(period) if period else None,
        "data_source": data_source,
        "extra": extra or {},
        "ts": datetime.utcnow().isoformat(),
    }
    _publish_safe(f"agent_activity:{agent_name}:{session_id}", payload)
    _publish_safe("agent_activity:all", payload)
    logger.info("session_start agent=%s session=%s period=%s",
                agent_name, session_id, period)


def tool_post_exec_hook(
    *,
    agent_name: str,
    session_id: str,
    tool_name: str,
    tool_args: dict[str, Any] | None = None,
    tool_result_summary: str | None = None,
    duration_ms: int | None = None,
    error: str | None = None,
) -> None:
    """Emit tool result to per-session stream."""
    payload = {
        "event": "tool_exec",
        "agent_name": agent_name,
        "session_id": session_id,
        "tool_name": tool_name,
        "tool_args_keys": list((tool_args or {}).keys()),
        "result_summary": tool_result_summary,
        "duration_ms": duration_ms,
        "error": error,
        "ts": datetime.utcnow().isoformat(),
    }
    _publish_safe(f"agent_activity:{agent_name}:{session_id}", payload)
    _publish_safe("agent_activity:all", payload)
