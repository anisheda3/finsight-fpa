"""HITL endpoints — receive Slack interactive payloads + manual override + list pending."""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.dependencies import db_pool
from app.services.temporal_client import signal_workflow

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/hitl", tags=["hitl"])


class HitlResponse(BaseModel):
    workflow_id: str
    flag_id: str
    decision: str            # APPROVED | REJECTED | ADJUSTED | REQUESTED_INFO
    reviewer_id: str | None = None
    notes: str | None = None


@router.post("/respond")
async def respond(req: HitlResponse) -> dict[str, str]:
    """Slack-button webhook OR direct API.  Signals the Temporal workflow."""
    await signal_workflow(req.workflow_id, "hitl_decision",
                          req.flag_id, req.decision, req.reviewer_id, req.notes)
    return {"status": "signaled", "workflow_id": req.workflow_id, "flag_id": req.flag_id}


@router.post("/{flag_id}/override")
async def override(flag_id: str, req: HitlResponse) -> dict[str, str]:
    """Manual override — same signal, used by the dashboard 'override' button."""
    if req.flag_id != flag_id:
        raise HTTPException(status_code=400, detail="flag_id mismatch")
    await signal_workflow(req.workflow_id, "hitl_decision",
                          flag_id, req.decision, req.reviewer_id, req.notes)
    return {"status": "override_signaled",
            "workflow_id": req.workflow_id, "flag_id": flag_id}


@router.get("/pending")
async def pending(
    company_id: UUID | None = None,
    pool=Depends(db_pool),
) -> list[dict[str, Any]]:
    """
    Returns everything currently awaiting human review:
      • rows in `hitl_approvals` with decision IS NULL or PENDING
      • MATERIAL/CRITICAL `variance_records` still in PENDING status
      • HIGH/CRITICAL `anomaly_flags` still in PENDING status

    Each item carries a `flag_id` shaped exactly like the saga generates it
    (`variance:<metric>:<period>` / `anomaly:<metric>:<period>`) so the UI
    can paste it straight into the override form.
    """
    if pool is None:
        return []

    out: list[dict[str, Any]] = []
    async with pool.acquire() as conn:

        # 1) Unresolved hitl_approvals
        rows = await conn.fetch(
            """
            SELECT id, flag_id, flag_type, temporal_workflow_id,
                   slack_message_ts, decision, created_at
            FROM hitl_approvals
            WHERE (decision IS NULL OR decision = 'PENDING')
              AND ($1::uuid IS NULL OR temporal_workflow_id LIKE
                   'month-end-' || $1::text || '%')
            ORDER BY created_at DESC
            LIMIT 200
            """,
            company_id,
        )
        for r in rows:
            out.append({
                "source":              "hitl_approvals",
                "flag_id":             str(r["flag_id"]) if r["flag_id"] else None,
                "flag_type":           r["flag_type"],
                "temporal_workflow_id": r["temporal_workflow_id"],
                "slack_message_ts":    r["slack_message_ts"],
                "created_at":          r["created_at"].isoformat() if r["created_at"] else None,
            })

        # 2) Material/critical variance records still pending
        v_rows = await conn.fetch(
            """
            SELECT company_id, period, metric_name, materiality,
                   variance_pct::float8, status, created_at
            FROM variance_records
            WHERE materiality IN ('MATERIAL', 'CRITICAL')
              AND status = 'PENDING'
              AND ($1::uuid IS NULL OR company_id = $1)
            ORDER BY created_at DESC
            LIMIT 200
            """,
            company_id,
        )
        for r in v_rows:
            out.append({
                "source":      "variance_records",
                "flag_id":     f"variance:{r['metric_name']}:{r['period'].isoformat()}",
                "flag_type":   "variance",
                "company_id":  str(r["company_id"]),
                "period":      r["period"].isoformat(),
                "metric_name": r["metric_name"],
                "materiality": r["materiality"],
                "variance_pct": r["variance_pct"],
                "created_at":  r["created_at"].isoformat() if r["created_at"] else None,
            })

        # 3) High/critical anomaly flags still pending
        a_rows = await conn.fetch(
            """
            SELECT company_id, period, metric_name, severity,
                   z_score::float8, status, created_at
            FROM anomaly_flags
            WHERE severity IN ('HIGH', 'CRITICAL')
              AND status = 'PENDING'
              AND ($1::uuid IS NULL OR company_id = $1)
            ORDER BY created_at DESC
            LIMIT 200
            """,
            company_id,
        )
        for r in a_rows:
            out.append({
                "source":      "anomaly_flags",
                "flag_id":     f"anomaly:{r['metric_name']}:{r['period'].isoformat()}",
                "flag_type":   "anomaly",
                "company_id":  str(r["company_id"]),
                "period":      r["period"].isoformat(),
                "metric_name": r["metric_name"],
                "severity":    r["severity"],
                "z_score":     r["z_score"],
                "created_at":  r["created_at"].isoformat() if r["created_at"] else None,
            })

    return out
