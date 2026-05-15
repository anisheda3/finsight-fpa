"""ForecastingAgent factory."""
from __future__ import annotations

from agents._agno_compat import make_agent, tool
from agents.evals import ForecastAccuracyEval
from agents.guardrails import ForecastReasonablenessGuardrail
from agents.hooks import session_start_hook, tool_post_exec_hook
from agents.instructions import FORECASTING_AGENT_INSTRUCTIONS_V1
from agents.memory import get_memory
from agents.schemas import ForecastResult
from agents.tools.forecasting_tools import fit_and_forecast, trailing_average


@tool
def fit_and_forecast_tool(history: list, horizon_months: int = 6,
                          holdout_months: int = 3,
                          prefer_model: str | None = None) -> dict:
    """Fit Prophet/SARIMA/linear and return forecast + 80/95 CIs + holdout MAPE."""
    return fit_and_forecast(history, horizon_months, holdout_months, prefer_model)


@tool
def get_trailing_average_tool(history: list, n: int = 3) -> float | None:
    """Trailing N-month average — used by the reasonableness guardrail."""
    return trailing_average(history, n)


@tool
async def search_forecast_memory_tool(company_id: str, metric_name: str) -> dict | None:
    """Recall last run's model + accuracy for this company+metric."""
    return await get_memory().get(
        agent_name="ForecastingAgent",
        memory_key=f"{metric_name}:last_run",
        company_id=company_id,
    )


@tool
async def save_forecast_memory_tool(company_id: str, metric_name: str,
                                    model_name: str, mape: float | None) -> None:
    """Persist this run's model decision for next time."""
    await get_memory().put(
        agent_name="ForecastingAgent",
        memory_key=f"{metric_name}:last_run",
        memory_value={"model_name": model_name, "mape": mape},
        company_id=company_id,
    )


from agents.model_factory import get_agno_model


def create_forecasting_agent():
    return make_agent(
        name="ForecastingAgent",
        model=get_agno_model(),
        instructions=FORECASTING_AGENT_INSTRUCTIONS_V1,
        tools=[
            fit_and_forecast_tool,
            get_trailing_average_tool,
            search_forecast_memory_tool,
            save_forecast_memory_tool,
        ],
        output_schema=ForecastResult,
        memory=None,
        guardrails=[ForecastReasonablenessGuardrail()],
        evals=[ForecastAccuracyEval()],
        hooks={"session_start": session_start_hook,
               "tool_post_exec": tool_post_exec_hook},
    )
