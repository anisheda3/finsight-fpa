"""DocumentContextAgent factory."""
from __future__ import annotations

from agents._agno_compat import make_agent, tool
from agents.hooks import session_start_hook, tool_post_exec_hook
from agents.instructions import DOCUMENT_AGENT_INSTRUCTIONS_V1
from agents.memory import get_memory


@tool
async def search_documents_tool(company_id: str, query: str, limit: int = 5) -> list:
    """Postgres FTS over financial_documents/document_chunks. Parameterized."""
    from uuid import UUID
    from app.core.db import get_pool
    from agents.tools.db_tools import search_documents
    pool = get_pool()
    if pool is None:
        return []
    return await search_documents(pool, company_id=UUID(company_id),
                                  query=query, limit=limit)


from agents.model_factory import get_agno_model


def create_document_agent():
    return make_agent(
        name="DocumentContextAgent",
        model=get_agno_model(),
        instructions=DOCUMENT_AGENT_INSTRUCTIONS_V1,
        tools=[search_documents_tool],
        output_schema=list,
        memory=get_memory(),
        guardrails=[],
        evals=[],
        hooks={"session_start": session_start_hook,
               "tool_post_exec": tool_post_exec_hook},
    )
