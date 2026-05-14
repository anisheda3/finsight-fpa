"""ScenarioPlanningAgent factory."""
from __future__ import annotations

from agents._agno_compat import make_agent, tool
from agents.hooks import session_start_hook, tool_post_exec_hook
from agents.instructions import SCENARIO_AGENT_INSTRUCTIONS_V1
from agents.memory import get_memory
from agents.schemas import ScenarioPlan
from agents.tools.scenario_tools import (
    SCENARIO_PRESETS, derive_ratios_from_history, propagate_scenario_pl,
)


@tool
def propagate_scenario_pl_tool(anchor_quarter_revenue: float,
                               assumptions: dict, n_quarters: int = 4,
                               start_period=None) -> list:
    """Project quarterly P&L given anchor revenue + ratio/growth assumptions."""
    return propagate_scenario_pl(
        anchor_quarter_revenue=anchor_quarter_revenue,
        assumptions=assumptions, n_quarters=n_quarters, start_period=start_period,
    )


@tool
def derive_ratios_tool(revenue: float, cogs: float, rd: float,
                       sm: float, ga: float) -> dict:
    """Derive cost ratios from a recent period for the BASE anchor."""
    return derive_ratios_from_history(revenue, cogs, rd, sm, ga)


@tool
def get_scenario_preset_tool(scenario_type: str) -> dict:
    """Return BASE/BULL/BEAR growth+macro presets."""
    return SCENARIO_PRESETS.get(scenario_type.upper(), {})


from agents.model_factory import get_agno_model


def create_scenario_agent():
    return make_agent(
        name="ScenarioPlanningAgent",
        model=get_agno_model(),
        instructions=SCENARIO_AGENT_INSTRUCTIONS_V1,
        tools=[propagate_scenario_pl_tool, derive_ratios_tool, get_scenario_preset_tool],
        output_schema=ScenarioPlan,
        memory=get_memory(),
        guardrails=[],
        evals=[],
        hooks={"session_start": session_start_hook,
               "tool_post_exec": tool_post_exec_hook},
    )
