"""
Agno-style MonthEndAnalysisWorkflow.

Required steps per spec:
    Parallel + Condition + Loop + Router + HumanReview

This is the *Agno workflow* layer — pure orchestration of Analysis Team and
Insights Team.  The DURABLE outer loop (with HITL signal-and-wait) lives in
temporal/month_end_saga.py and CALLS this workflow as an activity.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any
from uuid import UUID

from teams.analysis_team import AnalysisTeam
from teams.insights_team import InsightsTeam

logger = logging.getLogger(__name__)


class MonthEndAnalysisWorkflow:
    """
    Logical flow:
        1) Run AnalysisTeam (forecasting/variance/anomaly in parallel)
        2) Condition: any MATERIAL/CRITICAL flags?
              → if YES, return early with hitl_required=True (Temporal saga
                handles the Slack signal/wait loop)
              → if NO, proceed
        3) Run InsightsTeam (scenarios/commentary/notification/audit)
        4) Router: distribute by period_health (STRONG/ON_TRACK/AT_RISK/CRITICAL)
    """
    def __init__(self) -> None:
        self.analysis = AnalysisTeam()
        self.insights = InsightsTeam()

    async def arun(
        self, *,
        company_id: UUID,
        period: date,
        ingestion_result: dict[str, Any],
        skip_hitl: bool = False,
        hitl_decisions: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        # --- Step 1: Analysis Team (parallel inside) ---------------------
        analysis = await self.analysis.arun(
            company_id=company_id, period=period,
            ingestion_result=ingestion_result,
        )

        # --- Step 2: Condition / HITL gate -------------------------------
        material_flag_ids: list[str] = []
        for r in analysis.variance_report.records if analysis.variance_report else []:
            if r.materiality in ("MATERIAL", "CRITICAL"):
                material_flag_ids.append(f"variance:{r.metric_name}:{period.isoformat()}")
        for a in analysis.anomalies or []:
            if a.severity in ("HIGH", "CRITICAL"):
                material_flag_ids.append(f"anomaly:{a.metric_name}:{period.isoformat()}")

        if material_flag_ids and not skip_hitl and not hitl_decisions:
            return {
                "stage": "hitl_required",
                "analysis": analysis.model_dump(),
                "pending_flags": material_flag_ids,
                "period_health": analysis.period_health,
            }

        # --- Step 3: Insights Team --------------------------------------
        insights = await self.insights.arun(
            company_id=company_id, period=period,
            analysis_result=analysis.model_dump(),
        )

        # --- Step 4: Router by period_health ----------------------------
        distribution = self._route(analysis.period_health)

        return {
            "stage": "complete",
            "analysis": analysis.model_dump(),
            "insights": insights.model_dump(),
            "period_health": analysis.period_health,
            "distribution": distribution,
            "hitl_decisions": hitl_decisions or {},
        }

    @staticmethod
    def _route(period_health: str) -> dict[str, list[str]]:
        """Decide who gets notified based on period health."""
        base = ["#fpa-team"]
        if period_health == "STRONG":
            return {"slack": base, "email": ["cfo@example.com"]}
        if period_health == "ON_TRACK":
            return {"slack": base, "email": ["cfo@example.com"]}
        if period_health == "AT_RISK":
            return {"slack": base + ["#fpa-leadership"],
                    "email": ["cfo@example.com", "ceo@example.com"]}
        # CRITICAL_MISS
        return {"slack": base + ["#fpa-leadership", "#exec-team"],
                "email": ["cfo@example.com", "ceo@example.com", "board@example.com"]}
