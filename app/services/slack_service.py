"""
Slack service — posts HITL messages with interactive Approve/Reject/Adjust buttons.
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _hitl_blocks(flag_id: str, workflow_id: str, summary: str = "") -> list[dict]:
    return [
        {"type": "section",
         "text": {"type": "mrkdwn",
                  "text": f"*HITL review needed*\nFlag: `{flag_id}`\n{summary}"}},
        {"type": "actions",
         "block_id": "hitl_actions",
         "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "Approve"},
             "style": "primary", "action_id": "approve",
             "value": f"{workflow_id}|{flag_id}|APPROVED"},
            {"type": "button", "text": {"type": "plain_text", "text": "Reject"},
             "style": "danger", "action_id": "reject",
             "value": f"{workflow_id}|{flag_id}|REJECTED"},
            {"type": "button", "text": {"type": "plain_text", "text": "Request Info"},
             "action_id": "info",
             "value": f"{workflow_id}|{flag_id}|REQUESTED_INFO"},
         ]},
    ]


def send_hitl_message(*, channel: str, blocks: list[dict] | None = None,
                      flag_id: str | None = None,
                      workflow_id: str | None = None,
                      summary: str = "") -> dict[str, Any]:
    s = get_settings()
    payload_blocks = blocks or _hitl_blocks(flag_id or "", workflow_id or "", summary)
    if not s.slack_bot_token:
        logger.info("slack not configured; would post to %s: %s", channel, payload_blocks)
        return {"channel": channel, "message_ts": "stub-ts",
                "delivery_status": "PENDING"}
    try:
        from slack_sdk import WebClient
    except ImportError:                                    # pragma: no cover
        logger.warning("slack_sdk not installed")
        return {"channel": channel, "message_ts": None,
                "delivery_status": "FAILED", "error": "slack_sdk missing"}
    client = WebClient(token=s.slack_bot_token)
    try:
        resp = client.chat_postMessage(channel=channel, blocks=payload_blocks,
                                       text=f"HITL review: {flag_id}")
        return {"channel": channel, "message_ts": resp["ts"],
                "delivery_status": "SENT"}
    except Exception as e:                                  # pragma: no cover
        logger.exception("slack post failed: %s", e)
        return {"channel": channel, "message_ts": None,
                "delivery_status": "FAILED", "error": str(e)}
