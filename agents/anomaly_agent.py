"""AnomalyDetectionAgent factory."""
from __future__ import annotations

from agents._agno_compat import make_agent, tool
from agents.hooks import session_start_hook, tool_post_exec_hook
from agents.instructions import ANOMALY_AGENT_INSTRUCTIONS_V1
from agents.memory import get_memory
from agents.schemas import AnomalyFlag
from agents.tools.anomaly_tools import detect_anomalies


@tool
def detect_anomalies_tool(history: list, period_to_check=None,
                          method: str = "both") -> list:
    """z-score and/or IQR anomaly detection over a metric history."""
    return detect_anomalies(history, period_to_check, method)


from agents.model_factory import get_agno_model


def create_anomaly_agent():
    return make_agent(
        name="AnomalyDetectionAgent",
        model=get_agno_model(),
        instructions=ANOMALY_AGENT_INSTRUCTIONS_V1,
        tools=[detect_anomalies_tool],
        output_schema=list[AnomalyFlag],
        memory=get_memory(),
        guardrails=[],
        evals=[],
        hooks={"session_start": session_start_hook,
               "tool_post_exec": tool_post_exec_hook},
    )
