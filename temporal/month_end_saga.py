"""
MonthEndAnalysisSaga — Temporal workflow.

Durable HITL pattern:
    - workflow.signal handler captures Slack/UI decisions
    - workflow.wait_condition parks until all flags resolved or 24h timeout
    - all I/O is in activities (deterministic workflow code)
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    pass  # imports below are safe (no random/datetime side-effects)


@workflow.defn(name="MonthEndAnalysisSaga")
class MonthEndAnalysisSaga:
    def __init__(self) -> None:
        self._hitl_decisions: dict[str, dict[str, Any]] = {}
        self._pending_flag_ids: set[str] = set()
        self._aborted = False

    # ─── Signals ────────────────────────────────────────────
    @workflow.signal(name="hitl_decision")
    def hitl_decision(self, flag_id: str, decision: str,
                      reviewer_id: str | None = None,
                      notes: str | None = None) -> None:
        """Called by FastAPI when a Slack button or override is clicked."""
        self._hitl_decisions[flag_id] = {
            "decision": decision, "reviewer_id": reviewer_id, "notes": notes,
        }
        self._pending_flag_ids.discard(flag_id)

    @workflow.signal(name="abort")
    def abort(self, reason: str = "") -> None:
        self._aborted = True

    # ─── Run ────────────────────────────────────────────────
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        retry = RetryPolicy(maximum_attempts=3,
                            initial_interval=timedelta(seconds=2))

        # 1) Ingest
        ingestion = await workflow.execute_activity(
            "ingest_actuals_activity", payload,
            start_to_close_timeout=timedelta(minutes=5), retry_policy=retry,
        )
        if ingestion["accepted_rows"] == 0 and ingestion["rejected_rows"] > 0:
            return {"status": "INGESTION_FAILED", "ingestion": ingestion}

        # 2) Analysis (parallel inside the activity)
        analysis = await workflow.execute_activity(
            "run_analysis_workflow_activity",
            {"company_id": payload["company_id"],
             "period": ingestion["period_max"] or ingestion["period_min"],
             "ingestion_result": ingestion},
            start_to_close_timeout=timedelta(minutes=15), retry_policy=retry,
        )

        # 3) Determine HITL flags
        flag_ids: list[str] = []
        period_iso = analysis["period"]
        for r in (analysis.get("variance_report") or {}).get("records", []):
            if r["materiality"] in ("MATERIAL", "CRITICAL"):
                flag_ids.append(f"variance:{r['metric_name']}:{period_iso}")
        for a in analysis.get("anomalies", []):
            if a["severity"] in ("HIGH", "CRITICAL"):
                flag_ids.append(f"anomaly:{a['metric_name']}:{period_iso}")
        self._pending_flag_ids = set(flag_ids)

        # 4) HITL loop with Slack + signal/wait
        if flag_ids:
            for fid in flag_ids:
                await workflow.execute_activity(
                    "send_hitl_slack_activity",
                    {"flag_id": fid, "workflow_id": workflow.info().workflow_id,
                     "channel": payload.get("hitl_channel", "#fpa-hitl"),
                     "blocks": [{"type": "section",
                                 "text": {"type": "mrkdwn",
                                          "text": f"*HITL review needed*: `{fid}`"}}]},
                    start_to_close_timeout=timedelta(seconds=30), retry_policy=retry,
                )
            # Park until all decisions or 24h
            try:
                await workflow.wait_condition(
                    lambda: len(self._pending_flag_ids) == 0 or self._aborted,
                    timeout=timedelta(hours=24),
                )
            except TimeoutError:
                return {"status": "HITL_TIMEOUT",
                        "pending": list(self._pending_flag_ids),
                        "analysis": analysis}
            if self._aborted:
                return {"status": "ABORTED", "analysis": analysis}

        # 5) Insights
        insights = await workflow.execute_activity(
            "run_insights_workflow_activity",
            {"company_id": payload["company_id"],
             "period": period_iso, "analysis_result": analysis},
            start_to_close_timeout=timedelta(minutes=10), retry_policy=retry,
        )

        # 6) Final status
        await workflow.execute_activity(
            "write_final_status_activity",
            {"workflow_id": workflow.info().workflow_id,
             "workflow_name": "MonthEndAnalysisSaga",
             "status": "COMPLETED",
             "state": {"period_health": analysis.get("period_health")}},
            start_to_close_timeout=timedelta(seconds=30), retry_policy=retry,
        )

        return {
            "status": "COMPLETED",
            "analysis": analysis,
            "insights": insights,
            "hitl_decisions": self._hitl_decisions,
        }
