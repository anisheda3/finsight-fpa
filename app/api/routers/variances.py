"""Variance endpoints."""
from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import db_pool

router = APIRouter(prefix="/api/v1/variances", tags=["variances"])


@router.get("/{company_id}")
async def list_variances(company_id: UUID, period: date | None = None,
                         materiality: str | None = None,
                         pool=Depends(db_pool)) -> list[dict[str, Any]]:
    if pool is None: return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT period, department, metric_name,
                   actual_amount::float8, budget_amount::float8,
                   variance_amount::float8, variance_pct::float8,
                   is_favorable, materiality, waterfall_rank, status
            FROM variance_records
            WHERE company_id = $1
              AND ($2::date IS NULL OR period = $2)
              AND ($3::text IS NULL OR materiality = $3)
            ORDER BY period DESC, COALESCE(waterfall_rank, 9999), metric_name
            """,
            company_id, period, materiality,
        )
    return [dict(r) for r in rows]
