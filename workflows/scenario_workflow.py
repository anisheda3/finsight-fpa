"""
ScenarioAnalysisWorkflow.

Required steps per spec:
    Loop over BASE/BULL/BEAR + Condition (forecast freshness check)
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from agents.commentary_agent import create_commentary_agent
from agents.forecasting_agent import create_forecasting_agent
from agents.notification_agent import create_notification_agent
from agents.scenario_agent import create_scenario_agent

logger = logging.getLogger(__name__)

FORECAST_FRESHNESS_DAYS = 30
SCENARIO_TYPES = ("BASE", "BULL", "BEAR")


class ScenarioAnalysisWorkflow:
    def __init__(self) -> None:
        self.scenario_agent = create_scenario_agent()
        self.forecast_agent = create_forecasting_agent()
        self.commentary_agent = create_commentary_agent()
        self.notification_agent = create_notification_agent()

    async def arun(
        self, *,
        company_id: UUID,
        anchor_period: date,
        latest_forecast_run_at: datetime | None = None,
        assumptions: dict[str, dict[str, float]] | None = None,
    ) -> dict[str, Any]:
        # --- Condition: forecast freshness check ---
        forecast_refreshed = False
        if latest_forecast_run_at is None or \
           datetime.utcnow() - latest_forecast_run_at > timedelta(days=FORECAST_FRESHNESS_DAYS):
            try:
                await self.forecast_agent.arun({
                    "company_id": str(company_id), "metric_name": "revenue",
                })
                forecast_refreshed = True
            except Exception as e:
                logger.warning("forecast refresh failed: %s", e)

        # --- Loop over BASE/BULL/BEAR ---
        scenarios = []
        for stype in SCENARIO_TYPES:
            try:
                plan = await self.scenario_agent.arun({
                    "company_id": str(company_id), "scenario_type": stype,
                    "anchor_period": anchor_period,
                    "assumptions": (assumptions or {}).get(stype, {}),
                })
                if plan is not None:
                    scenarios.append(plan if isinstance(plan, dict) else plan.model_dump())
            except Exception as e:
                logger.exception("scenario %s failed: %s", stype, e)

        # --- end_condition: all 3 scenarios produced ---
        if len(scenarios) != 3:
            logger.warning("expected 3 scenarios, got %d", len(scenarios))

        # --- Comparative commentary ---
        commentary = None
        try:
            commentary = await self.commentary_agent.arun({
                "company_id": str(company_id), "period": anchor_period,
                "commentary_type": "SCENARIO",
                "analysis_data": {"scenarios": scenarios},
                "_analysis_context": {"scenarios": scenarios},
            })
        except Exception as e:
            logger.warning("scenario commentary failed: %s", e)

        # --- Notify ---
        try:
            await self.notification_agent.arun({
                "company_id": str(company_id), "period": anchor_period,
                "scenarios": scenarios,
            })
        except Exception as e:
            logger.warning("scenario notification failed: %s", e)

        return {
            "stage": "complete",
            "forecast_refreshed": forecast_refreshed,
            "scenarios": scenarios,
            "commentary": commentary.model_dump() if hasattr(commentary, "model_dump") else commentary,
        }
