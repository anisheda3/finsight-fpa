"""
ForecastRerunSaga — single-metric forecast refresh.

Triggered by POST /api/v1/forecasts/rerun.  Runs `forecast_metric_activity`
once and writes a final status row.  No HITL, no analysis-team coupling.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn(name="ForecastRerunSaga")
class ForecastRerunSaga:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        retry = RetryPolicy(maximum_attempts=3,
                            initial_interval=timedelta(seconds=2))

        forecast = await workflow.execute_activity(
            "forecast_metric_activity",
            {"company_id":     payload["company_id"],
             "metric_name":    payload["metric_name"],
             "horizon_months": payload.get("horizon_months", 6),
             "holdout_months": payload.get("holdout_months", 3)},
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=retry,
        )

        await workflow.execute_activity(
            "write_final_status_activity",
            {"workflow_id": workflow.info().workflow_id,
             "workflow_name": "ForecastRerunSaga",
             "status": "COMPLETED" if forecast else "NO_DATA",
             "state": {"metric": payload["metric_name"],
                       "model_name": (forecast or {}).get("model_name"),
                       "in_sample_mape": (forecast or {}).get("in_sample_mape")}},
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry,
        )

        return {
            "status": "COMPLETED" if forecast else "NO_DATA",
            "forecast": forecast,
        }
