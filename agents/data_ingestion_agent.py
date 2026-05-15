"""DataIngestionAgent factory."""
from __future__ import annotations

from agents._agno_compat import make_agent, tool
from agents.guardrails import DataSanityGuardrail
from agents.hooks import session_start_hook, tool_post_exec_hook
from agents.instructions import DATA_INGESTION_AGENT_INSTRUCTIONS_V1
from agents.memory import get_memory
from agents.schemas import IngestionResult
from agents.tools.ingestion_tools import parse_and_validate_actuals


@tool
def parse_and_validate_actuals_tool(content: str, company_id: str,
                                    file_format: str = "csv") -> dict:
    """Parse + validate + hash an actuals CSV/JSON for the given company."""
    from uuid import UUID
    return parse_and_validate_actuals(content, UUID(company_id), file_format)


from agents.model_factory import get_agno_model


def create_data_ingestion_agent():
    return make_agent(
        name="DataIngestionAgent",
        model=get_agno_model(),
        instructions=DATA_INGESTION_AGENT_INSTRUCTIONS_V1,
        tools=[parse_and_validate_actuals_tool],
        output_schema=IngestionResult,
        memory=None,
        guardrails=[DataSanityGuardrail()],
        evals=[],
        hooks={"session_start": session_start_hook,
               "tool_post_exec": tool_post_exec_hook},
    )
