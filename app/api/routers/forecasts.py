"""Forecast endpoints."""
from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.dependencies import db_pool
from app.services.temporal_client import start_workflow

router = APIRouter(prefix="/api/v1/forecasts", tags=["forecasts"])


class ForecastRerunRequest(BaseModel):
    company_id: UUID
    metric_name: str = Field(..., description="e.g. revenue, gross_profit, ebitda")
    horizon_months: int = 6
    holdout_months: int = 3


@router.get("/{company_id}")
async def list_forecasts(company_id: UUID, pool=Depends(db_pool)) -> list[dict[str, Any]]:
    if pool is None:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            WITH latest AS (
              SELECT metric_name, MAX(run_at) AS run_at FROM forecast_records
              WHERE company_id = $1 GROUP BY metric_name
            )
            SELECT fr.metric_name, fr.forecast_period,
                   fr.point_forecast::float8, fr.lower_bound_80::float8,
                   fr.upper_bound_80::float8, fr.lower_bound_95::float8,
                   fr.upper_bound_95::float8, fr.model_name,
                   fr.in_sample_mape::float8, fr.run_at
            FROM forecast_records fr
            JOIN latest l USING (metric_name)
            WHERE fr.company_id = $1 AND fr.run_at = l.run_at
            ORDER BY fr.metric_name, fr.forecast_period
            """,
            company_id,
        )
    return [dict(r) for r in rows]


@router.post("/rerun")
async def rerun_forecast(req: ForecastRerunRequest) -> dict[str, str]:
    """
    Re-run forecasting for a SINGLE metric.

    Starts a `ForecastRerunSaga` (lightweight Temporal workflow) that runs the
    `forecast_metric_activity` for the requested metric and writes a final
    status row.  Does NOT re-run the full month-end pipeline.
    """
    workflow_id = f"forecast-rerun-{req.company_id}-{req.metric_name}-{uuid.uuid4().hex[:8]}"
    started = await start_workflow(
        "ForecastRerunSaga",
        {
            "company_id":     str(req.company_id),
            "metric_name":    req.metric_name,
            "horizon_months": req.horizon_months,
            "holdout_months": req.holdout_months,
        },
        workflow_id,
    )
    return {
        "workflow_id":   started or workflow_id,
        "metric_name":   req.metric_name,
        "saga":          "ForecastRerunSaga",
    }
