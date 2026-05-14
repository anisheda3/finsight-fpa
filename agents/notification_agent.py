"""NotificationAgent factory + tool stubs (real impls in app/services/)."""
from __future__ import annotations

import json
import logging

from agents._agno_compat import make_agent, tool
from agents.hooks import session_start_hook, tool_post_exec_hook
from agents.instructions import NOTIFICATION_AGENT_INSTRUCTIONS_V1
from agents.memory import get_memory
from agents.schemas import NotificationResult

logger = logging.getLogger(__name__)


@tool
def send_slack_message_tool(channel: str, blocks: list, flag_id: str | None = None,
                            workflow_id: str | None = None) -> dict:
    """Post an interactive Slack HITL message. Returns {message_ts, status}."""
    from app.services.slack_service import send_hitl_message
    return send_hitl_message(channel=channel, blocks=blocks,
                             flag_id=flag_id, workflow_id=workflow_id)


@tool
def send_email_tool(to: str, subject: str, html_body: str,
                    pdf_attachment_b64: str | None = None) -> dict:
    """Send an HTML email with optional PDF attachment."""
    from app.services.email_service import send_email
    return send_email(to=to, subject=subject, html_body=html_body,
                      pdf_attachment_b64=pdf_attachment_b64)


@tool
def publish_redis_update_tool(channel: str, payload: dict) -> dict:
    """Push a structured event to a Redis pub/sub channel for the dashboard WS."""
    from app.core.redis import get_client
    client = get_client()
    if client is None:
        logger.warning("redis client not initialised; dropping payload")
        return {"delivery_status": "FAILED", "error": "redis not configured"}
    try:
        client.publish(channel, json.dumps(payload, default=str))
        return {"delivery_status": "SENT"}
    except Exception as e:
        return {"delivery_status": "FAILED", "error": str(e)}


from agents.model_factory import get_agno_model


def create_notification_agent():
    return make_agent(
        name="NotificationAgent",
        model=get_agno_model(),
        instructions=NOTIFICATION_AGENT_INSTRUCTIONS_V1,
        tools=[send_slack_message_tool, send_email_tool, publish_redis_update_tool],
        output_schema=NotificationResult,
        memory=get_memory(),
        guardrails=[],
        evals=[],
        hooks={"session_start": session_start_hook,
               "tool_post_exec": tool_post_exec_hook},
    )
