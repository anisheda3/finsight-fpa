"""AuditTrailAgent factory."""
from __future__ import annotations

from agents._agno_compat import make_agent, tool
from agents.hooks import session_start_hook, tool_post_exec_hook
from agents.instructions import AUDIT_AGENT_INSTRUCTIONS_V1
from agents.memory import get_memory
from agents.schemas import AuditEntry


@tool
async def write_audit_log_tool(entry: dict) -> str | None:
    from app.core.db import get_pool
    from agents.tools.db_tools import write_audit_log
    pool = get_pool()
    if pool is None:
        return None
    return str(await write_audit_log(pool, entry))


@tool
async def write_agent_run_tool(entry: dict) -> str | None:
    from app.core.db import get_pool
    from agents.tools.db_tools import write_agent_run
    pool = get_pool()
    if pool is None:
        return None
    return str(await write_agent_run(pool, entry))


@tool
def summarize_workflow_tool(entries: list) -> str:
    """One-line summary of a workflow run."""
    n = len(entries)
    failed = sum(1 for e in entries if (e.get("status") or "").upper() == "FAILED")
    return f"workflow_run summary: {n} agent runs, {failed} failed"


from agents.model_factory import get_agno_model


def create_audit_agent():
    return make_agent(
        name="AuditTrailAgent",
        model=get_agno_model(),
        instructions=AUDIT_AGENT_INSTRUCTIONS_V1,
        tools=[write_audit_log_tool, write_agent_run_tool, summarize_workflow_tool],
        output_schema=list[AuditEntry],
        memory=None,
        guardrails=[],
        evals=[],
        hooks={"session_start": session_start_hook,
               "tool_post_exec": tool_post_exec_hook},
    )
