"""FinancialCommentaryAgent factory."""
from __future__ import annotations

from agents._agno_compat import make_agent, tool
from agents.evals import CommentaryGroundingEval
from agents.guardrails import CommentaryGroundingGuardrail
from agents.hooks import session_start_hook, tool_post_exec_hook
from agents.instructions import COMMENTARY_AGENT_INSTRUCTIONS_V1
from agents.memory import get_memory
from agents.schemas import FinancialCommentary
from agents.tools.commentary_tools import (
    format_financial_summary, retrieve_variance_patterns,
)


@tool
def format_financial_summary_tool(analysis_data: dict) -> dict:
    """Compact analysis_data into a summary block for the LLM to ground against."""
    return format_financial_summary(analysis_data)


@tool
def retrieve_variance_patterns_tool(history: list) -> list:
    """Spot recurring multi-month variance patterns."""
    return retrieve_variance_patterns(history)


from agents.model_factory import get_agno_model


def create_commentary_agent():
    return make_agent(
        name="FinancialCommentaryAgent",
        model=get_agno_model(),
        instructions=COMMENTARY_AGENT_INSTRUCTIONS_V1,
        tools=[format_financial_summary_tool, retrieve_variance_patterns_tool],
        output_schema=FinancialCommentary,
        memory=get_memory(),
        guardrails=[CommentaryGroundingGuardrail()],
        evals=[CommentaryGroundingEval()],
        hooks={"session_start": session_start_hook,
               "tool_post_exec": tool_post_exec_hook},
    )
