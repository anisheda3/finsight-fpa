"""Actuals upload + listing."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.dependencies import db_pool
from app.services.temporal_client import start_workflow

router = APIRouter(prefix="/api/v1/actuals", tags=["actuals"])


@router.post("/upload")
async def upload_actuals(
    company_id: UUID = Form(...),
    file: UploadFile = File(...),
    file_format: str = Form("csv"),
    pool=Depends(db_pool),
) -> dict[str, Any]:
    content_bytes = await file.read()
    workflow_id = f"month-end-{company_id}-{uuid.uuid4().hex[:8]}"
    payload = {
        "company_id": str(company_id),
        "content": content_bytes.decode("utf-8", errors="replace"),
        "file_format": file_format,
    }
    started = await start_workflow("MonthEndAnalysisSaga", payload, workflow_id)
    return {"workflow_id": started or workflow_id,
            "filename": file.filename, "size": len(content_bytes)}


@router.get("/{company_id}")
async def list_actuals(
    company_id: UUID,
    period: date | None = None, metric: str | None = None,
    pool=Depends(db_pool),
) -> list[dict[str, Any]]:
    if pool is None:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT period, department, metric_name, amount::float8 AS amount, currency
            FROM financial_actuals
            WHERE company_id = $1
              AND ($2::date IS NULL OR period = $2)
              AND ($3::text IS NULL OR metric_name = $3)
            ORDER BY period DESC, metric_name
            """,
            company_id, period, metric,
        )
    return [dict(r) for r in rows]
