"""Slack interactive payload receiver."""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Form, HTTPException

from app.services.temporal_client import signal_workflow

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


@router.post("/slack")
async def slack_interactive(payload: str = Form(...)) -> dict[str, Any]:
    """Slack posts interactive payloads as form-encoded JSON in `payload`."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"bad json: {e}")
    actions = data.get("actions", [])
    if not actions:
        return {"status": "no_action"}
    value = actions[0].get("value", "")
    parts = value.split("|", 2)
    if len(parts) != 3:
        raise HTTPException(status_code=400, detail="bad action value")
    workflow_id, flag_id, decision = parts
    reviewer = data.get("user", {}).get("id")
    await signal_workflow(workflow_id, "hitl_decision", flag_id, decision, reviewer, None)
    return {"status": "signaled", "workflow_id": workflow_id, "flag_id": flag_id}
