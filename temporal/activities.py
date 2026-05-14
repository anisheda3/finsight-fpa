"""
Temporal activities — the I/O units called from the sagas.

Workflows must remain deterministic; activities can do anything (DB calls,
LLM calls, network).
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any
from uuid import UUID

from temporalio import activity

from agents.tools.db_tools import (
    fetch_budget_vs_actual, fetch_kpi_definitions, fetch_metric_history,
    upsert_actuals, upsert_company,
    write_anomaly_flags, write_forecast_records, write_variance_records,
)
from agents.tools.forecasting_tools import fit_and_forecast
from agents.tools.ingestion_tools import parse_and_validate_actuals
from agents.tools.variance_tools import (
    KpiDef, assign_waterfall_ranks, compute_ebitda_waterfall,
    compute_variance_records,
)
from agents.tools.anomaly_tools import detect_anomalies
from agents.tools.scenario_tools import propagate_scenario_pl, SCENARIO_PRESETS
from agents.schemas import (
    AnomalyFlag, ForecastPoint, ForecastResult, IngestionResult,
    MonthEndAnalysisResult, ScenarioAssumptions, ScenarioPlan, ScenarioQuarterlyPL,
    VarianceRecord, VarianceReport, WaterfallItem,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def _pool():
    from app.core.db import get_pool
    return get_pool()


# ─────────────────────────────────────────────────────────────
# 1) Ingest actuals
# ─────────────────────────────────────────────────────────────
@activity.defn(name="ingest_actuals_activity")
async def ingest_actuals_activity(payload: dict[str, Any]) -> dict[str, Any]:
    """payload: {company_id, content (str), file_format}"""
    company_id = UUID(payload["company_id"])
    parsed = parse_and_validate_actuals(
        payload["content"], company_id, payload.get("file_format", "csv"),
    )
    pool = _pool()
    inserted, duplicates = 0, 0
    if pool is not None and parsed["rows"]:
        rows_dict = [r.model_dump() for r in parsed["rows"]]
        inserted, duplicates = await upsert_actuals(
            pool, rows_dict, source_file_hash=parsed["source_file_hash"],
        )
    result = IngestionResult(
        company_id=company_id,
        accepted_rows=inserted,
        rejected_rows=parsed["rejected"],
        duplicate_rows=duplicates,
        errors=parsed["errors"],
        period_min=parsed["period_min"], period_max=parsed["period_max"],
        source_file_hash=parsed["source_file_hash"],
    )
    return result.model_dump(mode="json")


# ─────────────────────────────────────────────────────────────
# 2) Forecast a single metric (called once per metric in parallel)
# ─────────────────────────────────────────────────────────────
@activity.defn(name="forecast_metric_activity")
async def forecast_metric_activity(payload: dict[str, Any]) -> dict[str, Any] | None:
    company_id = UUID(payload["company_id"])
    metric = payload["metric_name"]
    pool = _pool()
    if pool is None:
        return None
    history = await fetch_metric_history(pool, company_id=company_id, metric_name=metric)
    if not history:
        return None
    raw = fit_and_forecast(history,
                           horizon_months=payload.get("horizon_months", 6),
                           holdout_months=payload.get("holdout_months", 3))
    await write_forecast_records(pool, company_id=company_id, metric_name=metric,
                                 forecast=raw["forecast"], model_meta=raw)
    fr = ForecastResult(
        company_id=company_id, metric_name=metric,
        forecast=[ForecastPoint(**p) for p in raw["forecast"]],
        **{k: v for k, v in raw.items() if k != "forecast"},
    )
    return fr.model_dump(mode="json")


# ─────────────────────────────────────────────────────────────
# 3) Variance + waterfall
# ─────────────────────────────────────────────────────────────
@activity.defn(name="run_variance_activity")
async def run_variance_activity(payload: dict[str, Any]) -> dict[str, Any]:
    company_id = UUID(payload["company_id"])
    period = date.fromisoformat(payload["period"])
    pool = _pool()
    if pool is None:
        return VarianceReport(company_id=company_id, period=period,
                              records=[], waterfall=[]).model_dump(mode="json")
    rows = await fetch_budget_vs_actual(pool, company_id=company_id, period=period)
    kpi_raw = await fetch_kpi_definitions(pool)
    kpi_defs = {k: KpiDef(**v) for k, v in kpi_raw.items()}
    records = compute_variance_records(rows, kpi_defs)
    waterfall, totals = compute_ebitda_waterfall(records)
    records = assign_waterfall_ranks(records, waterfall)
    await write_variance_records(pool, records)
    report = VarianceReport(
        company_id=company_id, period=period,
        records=[VarianceRecord(**r) for r in records],
        waterfall=[WaterfallItem(**w) for w in waterfall],
        total_ebitda_actual=totals["ebitda_actual"],
        total_ebitda_budget=totals["ebitda_budget"],
        total_ebitda_variance=totals["ebitda_variance"],
    )
    return report.model_dump(mode="json")


# ─────────────────────────────────────────────────────────────
# 4) Anomaly detection
# ─────────────────────────────────────────────────────────────
@activity.defn(name="run_anomaly_activity")
async def run_anomaly_activity(payload: dict[str, Any]) -> list[dict[str, Any]]:
    company_id = UUID(payload["company_id"])
    period = date.fromisoformat(payload["period"])
    pool = _pool()
    if pool is None:
        return []
    out: list[dict[str, Any]] = []
    for metric in payload.get("metrics", ["revenue", "cogs", "ebitda"]):
        history = await fetch_metric_history(pool, company_id=company_id, metric_name=metric)
        flags = detect_anomalies(history, period_to_check=period, method="both")
        if flags:
            await write_anomaly_flags(pool, company_id=company_id,
                                      metric_name=metric, flags=flags)
        for f in flags:
            out.append(AnomalyFlag(
                company_id=company_id, period=f["period"], metric_name=metric,
                expected_value=f["expected_value"], actual_value=f["actual_value"],
                z_score=f["z_score"], detection_method=f["detection_method"],
                severity=f["severity"],
            ).model_dump(mode="json"))
    return out


# ─────────────────────────────────────────────────────────────
# 5) Wrapper: run AnalysisTeam (calls 2/3/4 in parallel internally)
# ─────────────────────────────────────────────────────────────
@activity.defn(name="run_analysis_workflow_activity")
async def run_analysis_workflow_activity(payload: dict[str, Any]) -> dict[str, Any]:
    """Imports the workflow lazily so Temporal worker bootstrap stays light."""
    import asyncio
    from teams.analysis_team import _classify_period_health
    company_id = UUID(payload["company_id"])
    period = date.fromisoformat(payload["period"])

    forecasts_task = asyncio.gather(*[
        forecast_metric_activity({"company_id": str(company_id), "metric_name": m})
        for m in payload.get("forecast_metrics", ["revenue", "gross_profit", "ebitda"])
    ])
    variance_task = run_variance_activity({"company_id": str(company_id),
                                           "period": period.isoformat()})
    anomaly_task = run_anomaly_activity({"company_id": str(company_id),
                                         "period": period.isoformat()})
    forecasts, variance, anomalies = await asyncio.gather(
        forecasts_task, variance_task, anomaly_task,
    )
    forecasts = [f for f in forecasts if f is not None]
    vr_model = VarianceReport(**variance) if variance else None
    ph = _classify_period_health(vr_model) if vr_model else "ON_TRACK"

    return MonthEndAnalysisResult(
        company_id=company_id, period=period,
        ingestion=IngestionResult(**payload["ingestion_result"]),
        forecasts=[ForecastResult(**f) for f in forecasts],
        variance_report=vr_model,
        anomalies=[AnomalyFlag(**a) for a in anomalies],
        period_health=ph,
    ).model_dump(mode="json")


# ─────────────────────────────────────────────────────────────
# 6) Insights workflow (stubbed; real impl wraps InsightsTeam)
# ─────────────────────────────────────────────────────────────
@activity.defn(name="run_insights_workflow_activity")
async def run_insights_workflow_activity(payload: dict[str, Any]) -> dict[str, Any]:
    from teams.insights_team import InsightsTeam
    team = InsightsTeam()
    company_id = UUID(payload["company_id"])
    period = date.fromisoformat(payload["period"])
    res = await team.arun(
        company_id=company_id, period=period,
        analysis_result=payload["analysis_result"],
        scenario_assumptions=payload.get("scenario_assumptions"),
    )
    return res.model_dump(mode="json")


# ─────────────────────────────────────────────────────────────
# 7) Scenario activity (used by ScenarioAnalysisSaga)
# ─────────────────────────────────────────────────────────────
@activity.defn(name="run_scenario_activity")
async def run_scenario_activity(payload: dict[str, Any]) -> dict[str, Any]:
    company_id = UUID(payload["company_id"])
    scenario_type = payload["scenario_type"].upper()
    anchor_revenue = float(payload["anchor_quarter_revenue"])
    assumptions = {**SCENARIO_PRESETS.get(scenario_type, {}), **payload.get("assumptions", {})}
    quarters = propagate_scenario_pl(
        anchor_quarter_revenue=anchor_revenue, assumptions=assumptions,
        n_quarters=payload.get("n_quarters", 4),
        start_period=date.fromisoformat(payload["start_period"]) if payload.get("start_period") else None,
    )
    plan = ScenarioPlan(
        company_id=company_id, scenario_type=scenario_type, label=f"{scenario_type}-{date.today().isoformat()}",
        assumptions=ScenarioAssumptions(**assumptions),
        quarters=[ScenarioQuarterlyPL(**q) for q in quarters],
        projection_start=date.fromisoformat(quarters[0]["quarter_label"].split()[1] + "-01-01")
            if quarters else date.today(),
        projection_end=date.fromisoformat(quarters[-1]["quarter_label"].split()[1] + "-12-31")
            if quarters else date.today(),
        projected_revenue=sum(q["revenue"] for q in quarters),
        projected_gross_profit=sum(q["gross_profit"] for q in quarters),
        projected_ebitda=sum(q["ebitda"] for q in quarters),
    )
    return plan.model_dump(mode="json")


# ─────────────────────────────────────────────────────────────
# 8) Slack HITL message
# ─────────────────────────────────────────────────────────────
@activity.defn(name="send_hitl_slack_activity")
async def send_hitl_slack_activity(payload: dict[str, Any]) -> dict[str, Any]:
    from app.services.slack_service import send_hitl_message
    return send_hitl_message(
        channel=payload.get("channel", "#fpa-hitl"),
        blocks=payload.get("blocks", []),
        flag_id=payload.get("flag_id"),
        workflow_id=payload.get("workflow_id"),
    )


# ─────────────────────────────────────────────────────────────
# 9) Final status
# ─────────────────────────────────────────────────────────────
@activity.defn(name="write_final_status_activity")
async def write_final_status_activity(payload: dict[str, Any]) -> None:
    pool = _pool()
    if pool is None:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO workflow_states
              (temporal_workflow_id, agno_workflow_name, status, state_data, completed_at)
            VALUES ($1, $2, $3, $4::jsonb, $5)
            ON CONFLICT (temporal_workflow_id) DO UPDATE SET
              status = EXCLUDED.status,
              state_data = EXCLUDED.state_data,
              completed_at = EXCLUDED.completed_at
            """,
            payload["workflow_id"], payload["workflow_name"], payload["status"],
            json.dumps(payload.get("state", {}), default=str),
            datetime.utcnow(),
        )
