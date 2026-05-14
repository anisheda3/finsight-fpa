"""ScenarioAnalysisSaga — runs BASE/BULL/BEAR + comparative commentary."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn(name="ScenarioAnalysisSaga")
class ScenarioAnalysisSaga:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        retry = RetryPolicy(maximum_attempts=3,
                            initial_interval=timedelta(seconds=2))

        # --- Loop over BASE/BULL/BEAR ---
        scenarios: list[dict[str, Any]] = []
        for stype in ("BASE", "BULL", "BEAR"):
            plan = await workflow.execute_activity(
                "run_scenario_activity",
                {"company_id": payload["company_id"],
                 "scenario_type": stype,
                 "anchor_quarter_revenue": payload["anchor_quarter_revenue"],
                 "assumptions": (payload.get("assumptions") or {}).get(stype, {}),
                 "n_quarters": payload.get("n_quarters", 4),
                 "start_period": payload.get("start_period")},
                start_to_close_timeout=timedelta(minutes=2), retry_policy=retry,
            )
            scenarios.append(plan)

        # --- end_condition: all 3 produced ---
        if len(scenarios) != 3:
            return {"status": "INCOMPLETE", "produced": len(scenarios)}

        # --- Final status ---
        await workflow.execute_activity(
            "write_final_status_activity",
            {"workflow_id": workflow.info().workflow_id,
             "workflow_name": "ScenarioAnalysisSaga",
             "status": "COMPLETED",
             "state": {"n_scenarios": len(scenarios)}},
            start_to_close_timeout=timedelta(seconds=30), retry_policy=retry,
        )
        return {"status": "COMPLETED", "scenarios": scenarios}
