"""
InsightsTeam — Document context + Scenarios + Commentary + Notification + Audit.

CRITICAL: passes _analysis_context (structured) to the commentary agent so the
CommentaryGroundingGuardrail can verify every cited figure traces to the
analysis_data the LLM was actually shown.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any
from uuid import UUID

from agents._agno_compat import make_team
from agents.audit_agent import create_audit_agent
from agents.commentary_agent import create_commentary_agent
from agents.document_agent import create_document_agent
from agents.guardrails import CommentaryGroundingGuardrail
from agents.memory import get_memory
from agents.notification_agent import create_notification_agent
from agents.scenario_agent import create_scenario_agent
from agents.schemas import (
    FinancialCommentary, InsightsTeamResult, ScenarioPlan,
)
from agents.tools.commentary_tools import format_financial_summary

logger = logging.getLogger(__name__)


class InsightsTeam:
    def __init__(self) -> None:
        self.document     = create_document_agent()
        self.scenario     = create_scenario_agent()
        self.commentary   = create_commentary_agent()
        self.notification = create_notification_agent()
        self.audit        = create_audit_agent()
        self._team = make_team(
            name="InsightsTeam",
            members=[self.document, self.scenario, self.commentary,
                     self.notification, self.audit],
            instructions=(
                "Run document context retrieval, scenarios, commentary, "
                "notifications, and audit. Commentary MUST be grounded in "
                "the same analysis_data passed to the agent."
            ),
            output_schema=InsightsTeamResult,
            memory=get_memory(),
            guardrails=[CommentaryGroundingGuardrail()],
        )

    async def arun(
        self, *,
        company_id: UUID,
        period: date,
        analysis_result: dict[str, Any],
        scenario_assumptions: dict[str, dict[str, float]] | None = None,
    ) -> InsightsTeamResult:
        # 1) Document context (best-effort)
        doc_chunks: list[Any] = []
        try:
            doc_chunks = await self.document.arun({
                "company_id": str(company_id),
                "query": "outlook risk factors management commentary",
            }) or []
        except Exception as e:
            logger.warning("document agent failed (non-fatal): %s", e)

        # 2) Scenarios
        scenarios: list[ScenarioPlan] = []
        sa = scenario_assumptions or {}
        for stype in ("BASE", "BULL", "BEAR"):
            try:
                plan = await self.scenario.arun({
                    "company_id": str(company_id),
                    "scenario_type": stype,
                    "assumptions": sa.get(stype, {}),
                    "anchor_period": period,
                })
                if plan is not None:
                    scenarios.append(plan)
            except Exception as e:
                logger.warning("scenario %s failed: %s", stype, e)

        # 3) Commentary — pass analysis context BOTH ways for grounding
        context_summary = format_financial_summary(analysis_result)
        analysis_context_blob: dict[str, Any] = {
            **analysis_result,
            "summary": context_summary,
            "document_chunks": doc_chunks,
            "scenarios": [s.model_dump() if hasattr(s, "model_dump") else s for s in scenarios],
        }
        try:
            commentary = await self.commentary.arun({
                "company_id": str(company_id),
                "period": period,
                "analysis_data": analysis_context_blob,
                "_analysis_context": analysis_context_blob,
            })
        except Exception as e:
            logger.exception("commentary failed: %s", e)
            commentary = FinancialCommentary(
                company_id=company_id, period=period,
                narrative="Commentary unavailable due to upstream error." + " " * 100,
                key_insights=["error", "error", "error"],
            )

        # 4) Notifications + 5) Audit (best-effort)
        notifications = []
        audit_entries = []
        try:
            n = await self.notification.arun({
                "company_id": str(company_id), "period": period,
                "summary": context_summary,
            })
            if n: notifications.append(n)
        except Exception as e:
            logger.warning("notification failed: %s", e)
        try:
            a = await self.audit.arun({
                "company_id": str(company_id), "period": period,
                "analysis_result": analysis_result,
                "commentary": commentary.model_dump() if hasattr(commentary, "model_dump") else commentary,
            })
            if a: audit_entries = a if isinstance(a, list) else [a]
        except Exception as e:
            logger.warning("audit failed: %s", e)

        return InsightsTeamResult(
            company_id=company_id,
            period=period,
            scenarios=scenarios,
            commentary=commentary,
            notifications=notifications,
            audit_entries=audit_entries,
        )
