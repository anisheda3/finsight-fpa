"""VarianceAnalysisAgent factory."""
from __future__ import annotations

from agents._agno_compat import make_agent, tool
from agents.hooks import session_start_hook, tool_post_exec_hook
from agents.instructions import VARIANCE_AGENT_INSTRUCTIONS_V1
from agents.memory import get_memory
from agents.schemas import VarianceReport
from agents.tools.variance_tools import (
    KpiDef, assign_waterfall_ranks, compute_ebitda_waterfall,
    compute_variance_records, flag_for_hitl,
)


@tool
def compute_variance_tool(rows: list, kpi_defs: dict | None = None) -> list:
    """Compute variance records w/ materiality + favorable/unfavorable."""
    typed = {k: KpiDef(**v) for k, v in (kpi_defs or {}).items()}
    return compute_variance_records(rows, typed)


@tool
def compute_waterfall_tool(variance_records: list) -> dict:
    """Decompose ΔEBITDA into ranked driver contributions."""
    waterfall, totals = compute_ebitda_waterfall(variance_records)
    return {"waterfall": waterfall, "totals": totals}


@tool
def assign_ranks_tool(records: list, waterfall: list) -> list:
    return assign_waterfall_ranks(records, waterfall)


@tool
def flag_for_hitl_tool(records: list) -> list:
    return flag_for_hitl(records)


from agents.model_factory import get_agno_model


def create_variance_agent():
    return make_agent(
        name="VarianceAnalysisAgent",
        model=get_agno_model(),
        instructions=VARIANCE_AGENT_INSTRUCTIONS_V1,
        tools=[compute_variance_tool, compute_waterfall_tool,
               assign_ranks_tool, flag_for_hitl_tool],
        output_schema=VarianceReport,
        memory=get_memory(),
        guardrails=[],
        evals=[],
        hooks={"session_start": session_start_hook,
               "tool_post_exec": tool_post_exec_hook},
    )
