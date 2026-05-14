"""
AnalysisTeam — Forecasting + Variance + Anomaly running in parallel after
ingestion is confirmed clean.

Output: MonthEndAnalysisResult.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any
from uuid import UUID

from agents._agno_compat import make_team
from agents.anomaly_agent import create_anomaly_agent
from agents.forecasting_agent import create_forecasting_agent
from agents.guardrails import DataSanityGuardrail
from agents.memory import get_memory
from agents.schemas import (
    AnomalyFlag, ForecastResult, MonthEndAnalysisResult, VarianceReport,
)
from agents.variance_agent import create_variance_agent

logger = logging.getLogger(__name__)


def _classify_period_health(variance_report: VarianceReport) -> str:
    """STRONG/ON_TRACK/AT_RISK/CRITICAL_MISS based on EBITDA variance + drivers."""
    delta = variance_report.total_ebitda_variance or 0
    budget = variance_report.total_ebitda_budget or 0
    if budget == 0:
        return "ON_TRACK"
    pct = (delta / abs(budget)) * 100.0
    has_critical = any(r.materiality == "CRITICAL" for r in variance_report.records)
    if has_critical or pct < -15:
        return "CRITICAL_MISS"
    if pct < -5:
        return "AT_RISK"
    if pct >= 5:
        return "STRONG"
    return "ON_TRACK"


class AnalysisTeam:
    """
    Wraps the underlying Agno team so we can expose a typed `arun(...)` that
    runs forecasting/variance/anomaly concurrently.
    """
    def __init__(self) -> None:
        self.forecasting = create_forecasting_agent()
        self.variance   = create_variance_agent()
        self.anomaly    = create_anomaly_agent()
        self._team = make_team(
            name="AnalysisTeam",
            members=[self.forecasting, self.variance, self.anomaly],
            instructions=(
                "Run forecasting, variance, and anomaly detection in parallel "
                "and aggregate into a MonthEndAnalysisResult."
            ),
            output_schema=MonthEndAnalysisResult,
            memory=get_memory(),
            guardrails=[DataSanityGuardrail()],
        )

    async def arun(
        self, *,
        company_id: UUID,
        period: date,
        ingestion_result: dict[str, Any],
        forecast_metrics: list[str] | None = None,
    ) -> MonthEndAnalysisResult:
        forecast_metrics = forecast_metrics or ["revenue", "gross_profit", "ebitda"]

        async def _forecast(metric: str) -> ForecastResult | None:
            payload = {"company_id": str(company_id), "metric_name": metric,
                       "period": period}
            try:
                return await self.forecasting.arun(payload)
            except Exception as e:
                logger.exception("forecasting failed for %s: %s", metric, e)
                return None

        async def _variance() -> VarianceReport | None:
            try:
                return await self.variance.arun({
                    "company_id": str(company_id), "period": period,
                })
            except Exception as e:
                logger.exception("variance failed: %s", e)
                return None

        async def _anomaly() -> list[AnomalyFlag]:
            try:
                return await self.anomaly.arun({
                    "company_id": str(company_id), "period": period,
                }) or []
            except Exception as e:
                logger.exception("anomaly failed: %s", e)
                return []

        # Run all in parallel
        fc_results, vr_result, an_results = await asyncio.gather(
            asyncio.gather(*[_forecast(m) for m in forecast_metrics]),
            _variance(),
            _anomaly(),
        )
        forecasts = [f for f in fc_results if f is not None]
        variance_report = vr_result

        period_health = _classify_period_health(variance_report) if variance_report else "ON_TRACK"

        return MonthEndAnalysisResult(
            company_id=company_id,
            period=period,
            ingestion=ingestion_result,
            forecasts=forecasts,
            variance_report=variance_report,
            anomalies=an_results,
            period_health=period_health,
        )
