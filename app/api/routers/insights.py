"""Insights endpoints — commentary + scenarios (paths match spec exactly)."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.dependencies import db_pool
from app.services.temporal_client import start_workflow

router = APIRouter(prefix="/api/v1/insights", tags=["insights"])


class ScenarioRunRequest(BaseModel):
    company_id: UUID
    anchor_quarter_revenue: float
    assumptions: dict[str, dict[str, float]] | None = None
    n_quarters: int = 4
    start_period: date | None = None


@router.post("/scenarios/run")
async def run_scenarios(req: ScenarioRunRequest) -> dict[str, str]:
    workflow_id = f"scenario-{req.company_id}-{uuid.uuid4().hex[:8]}"
    payload = req.model_dump(mode="json")
    started = await start_workflow("ScenarioAnalysisSaga", payload, workflow_id)
    return {"workflow_id": started or workflow_id}


@router.get("/scenarios/{company_id}")
async def list_scenarios(company_id: UUID, pool=Depends(db_pool)) -> list[dict[str, Any]]:
    if pool is None: return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT scenario_type, label, assumptions,
                   projected_revenue::float8, projected_gross_profit::float8,
                   projected_ebitda::float8, projected_pl,
                   projection_start, projection_end, created_at
            FROM scenario_plans
            WHERE company_id = $1
            ORDER BY created_at DESC LIMIT 50
            """,
            company_id,
        )
    return [dict(r) for r in rows]


@router.get("/commentary/{company_id}/{period}")
async def get_commentary(company_id: UUID, period: date,
                         pool=Depends(db_pool)) -> dict[str, Any]:
    if pool is None:
        raise HTTPException(status_code=503, detail="db not configured")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT narrative, key_insights, figures_cited, grounding_score,
                   model_version, created_at
            FROM financial_commentary
            WHERE company_id = $1 AND period = $2
            ORDER BY created_at DESC LIMIT 1
            """,
            company_id, period,
        )
    if not row:
        raise HTTPException(status_code=404, detail="no commentary for that period")
    return dict(row)
