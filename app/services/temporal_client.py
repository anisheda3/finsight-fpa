"""Thin Temporal client for FastAPI side."""
from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)
_client: Any | None = None


async def get_client():
    global _client
    if _client is not None:
        return _client
    try:
        from temporalio.client import Client
    except ImportError:                          # pragma: no cover
        return None
    s = get_settings()
    _client = await Client.connect(s.temporal_address, namespace=s.temporal_namespace)
    return _client


async def signal_workflow(workflow_id: str, signal_name: str, *args: Any) -> None:
    client = await get_client()
    if client is None:
        logger.warning("temporal not available; cannot signal %s", workflow_id)
        return
    handle = client.get_workflow_handle(workflow_id)
    signal_arg = args if len(args) > 1 else args[0] if args else None
    await handle.signal(signal_name, signal_arg)


async def start_workflow(workflow_name: str, payload: dict[str, Any],
                         workflow_id: str) -> str:
    client = await get_client()
    if client is None:
        logger.warning("temporal not available; cannot start %s", workflow_name)
        return ""
    s = get_settings()
    handle = await client.start_workflow(
        workflow_name, payload, id=workflow_id, task_queue=s.temporal_task_queue,
    )
    return handle.id
