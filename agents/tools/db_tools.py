"""
DB-backed tools used by agents.

Every function here:
    • takes the asyncpg pool (or fetches it from app.core.db) — no globals
    • is fully async
    • uses parameterized SQL ($1, $2, ...) — no string interpolation of user input
    • is idempotent where applicable (ON CONFLICT DO NOTHING / DO UPDATE)
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Companies
# ─────────────────────────────────────────────────────────────
async def upsert_company(pool: Any, *, name: str, erp_code: str,
                         industry: str | None = None) -> UUID:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO companies (name, erp_code, industry)
            VALUES ($1, $2, $3)
            ON CONFLICT (erp_code) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
            name, erp_code, industry,
        )
    return row["id"]


# ─────────────────────────────────────────────────────────────
# Actuals  (idempotent)
# ─────────────────────────────────────────────────────────────
async def upsert_actuals(pool: Any, rows: list[dict[str, Any]],
                         source_file_hash: str | None = None) -> tuple[int, int]:
    """Returns (inserted, duplicates_skipped)."""
    if not rows:
        return 0, 0
    inserted = 0
    duplicates = 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            for r in rows:
                res = await conn.execute(
                    """
                    INSERT INTO financial_actuals
                        (company_id, period, department, metric_name, amount,
                         currency, source, source_file_hash)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (company_id, period, department, metric_name)
                    DO NOTHING
                    """,
                    r["company_id"], r["period"], r.get("department"),
                    r["metric_name"], r["amount"],
                    r.get("currency", "INR"), r.get("source", "ERP"),
                    source_file_hash,
                )
                # res is "INSERT 0 1" or "INSERT 0 0"
                if res.endswith(" 1"):
                    inserted += 1
                else:
                    duplicates += 1
    return inserted, duplicates


async def fetch_metric_history(pool: Any, *, company_id: UUID, metric_name: str,
                               department: str | None = None,
                               months: int = 48) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT period, SUM(amount)::float8 AS value
            FROM financial_actuals
            WHERE company_id = $1 AND metric_name = $2
              AND ($3::text IS NULL OR department = $3)
            GROUP BY period
            ORDER BY period DESC
            LIMIT $4
            """,
            company_id, metric_name, department, months,
        )
    return [{"period": r["period"], "value": float(r["value"])}
            for r in reversed(rows)]


# ─────────────────────────────────────────────────────────────
# Budgets
# ─────────────────────────────────────────────────────────────
async def fetch_budget_vs_actual(pool: Any, *, company_id: UUID,
                                 period: date) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            WITH active_budget AS (
              SELECT * FROM budget_data
              WHERE company_id = $1 AND period = $2 AND is_active = TRUE
            )
            SELECT
              fa.id          AS actual_id,
              ab.id          AS budget_id,
              fa.company_id, fa.period, fa.department, fa.metric_name,
              fa.amount      AS actual_amount,
              ab.budgeted_amount AS budget_amount
            FROM financial_actuals fa
            LEFT JOIN active_budget ab
              ON ab.company_id = fa.company_id
             AND ab.period = fa.period
             AND COALESCE(ab.department, '') = COALESCE(fa.department, '')
             AND ab.metric_name = fa.metric_name
            WHERE fa.company_id = $1 AND fa.period = $2
              AND ab.id IS NOT NULL
            """,
            company_id, period,
        )
    return [dict(r) for r in rows]


async def fetch_kpi_definitions(pool: Any) -> dict[str, dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT metric_name, favorable_direction, materiality_threshold_pct FROM kpi_definitions"
        )
    return {r["metric_name"]: dict(r) for r in rows}


# ─────────────────────────────────────────────────────────────
# Variance records
# ─────────────────────────────────────────────────────────────
async def write_variance_records(pool: Any, records: list[dict[str, Any]]) -> int:
    if not records:
        return 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            for r in records:
                await conn.execute(
                    """
                    INSERT INTO variance_records
                        (company_id, period, department, metric_name,
                         actual_amount, budget_amount, variance_amount,
                         variance_pct, is_favorable, materiality, waterfall_rank,
                         actual_id, budget_id)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                    ON CONFLICT (company_id, period, department, metric_name)
                    DO UPDATE SET
                      actual_amount = EXCLUDED.actual_amount,
                      budget_amount = EXCLUDED.budget_amount,
                      variance_amount = EXCLUDED.variance_amount,
                      variance_pct = EXCLUDED.variance_pct,
                      is_favorable = EXCLUDED.is_favorable,
                      materiality = EXCLUDED.materiality,
                      waterfall_rank = EXCLUDED.waterfall_rank
                    """,
                    r["company_id"], r["period"], r.get("department"),
                    r["metric_name"],
                    r["actual_amount"], r["budget_amount"], r["variance_amount"],
                    r["variance_pct"], r["is_favorable"], r["materiality"],
                    r.get("waterfall_rank"),
                    r.get("actual_id"), r.get("budget_id"),
                )
    return len(records)


# ─────────────────────────────────────────────────────────────
# Forecast records
# ─────────────────────────────────────────────────────────────
async def write_forecast_records(pool: Any, *, company_id: UUID, metric_name: str,
                                 forecast: list[dict[str, Any]],
                                 model_meta: dict[str, Any]) -> int:
    if not forecast:
        return 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            for p in forecast:
                await conn.execute(
                    """
                    INSERT INTO forecast_records
                        (company_id, metric_name, forecast_period,
                         point_forecast, lower_bound_80, upper_bound_80,
                         lower_bound_95, upper_bound_95,
                         model_name, model_version, model_params,
                         in_sample_mape, holdout_months, horizon_months,
                         training_start_period, training_end_period,
                         run_id, selected_reason, fallback_reason,
                         prior_model_used, prior_mape)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,
                            $9,$10,$11::jsonb,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21)
                    ON CONFLICT (company_id, metric_name, forecast_period, model_name, run_id)
                    DO UPDATE SET
                      point_forecast = EXCLUDED.point_forecast,
                      lower_bound_80 = EXCLUDED.lower_bound_80,
                      upper_bound_80 = EXCLUDED.upper_bound_80,
                      lower_bound_95 = EXCLUDED.lower_bound_95,
                      upper_bound_95 = EXCLUDED.upper_bound_95
                    """,
                    company_id, metric_name, p["period"],
                    p["point_forecast"], p["lower_bound_80"], p["upper_bound_80"],
                    p["lower_bound_95"], p["upper_bound_95"],
                    model_meta.get("model_name"), model_meta.get("model_version", "1.0.0"),
                    json.dumps(model_meta.get("model_params", {})),
                    model_meta.get("in_sample_mape"),
                    model_meta.get("holdout_months"),
                    model_meta.get("horizon_months"),
                    model_meta.get("training_start_period"),
                    model_meta.get("training_end_period"),
                    model_meta.get("run_id"),
                    model_meta.get("selected_reason"),
                    model_meta.get("fallback_reason"),
                    model_meta.get("prior_model_used"),
                    model_meta.get("prior_mape"),
                )
    return len(forecast)


async def get_latest_forecast(pool: Any, *, company_id: UUID,
                              metric_name: str) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        latest_run = await conn.fetchval(
            """
            SELECT run_id FROM forecast_records
            WHERE company_id = $1 AND metric_name = $2
            ORDER BY run_at DESC LIMIT 1
            """,
            company_id, metric_name,
        )
        if not latest_run:
            return []
        rows = await conn.fetch(
            """
            SELECT forecast_period AS period, point_forecast,
                   lower_bound_80, upper_bound_80,
                   lower_bound_95, upper_bound_95
            FROM forecast_records
            WHERE company_id = $1 AND metric_name = $2 AND run_id = $3
            ORDER BY forecast_period
            """,
            company_id, metric_name, latest_run,
        )
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────
# Anomaly flags
# ─────────────────────────────────────────────────────────────
async def write_anomaly_flags(pool: Any, *, company_id: UUID, metric_name: str,
                              flags: list[dict[str, Any]]) -> int:
    if not flags:
        return 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            for f in flags:
                await conn.execute(
                    """
                    INSERT INTO anomaly_flags
                        (company_id, period, metric_name, expected_value,
                         actual_value, z_score, detection_method, severity)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                    ON CONFLICT (company_id, period, metric_name, detection_method)
                    DO UPDATE SET
                      expected_value = EXCLUDED.expected_value,
                      actual_value   = EXCLUDED.actual_value,
                      z_score        = EXCLUDED.z_score,
                      severity       = EXCLUDED.severity
                    """,
                    company_id, f["period"], metric_name,
                    f["expected_value"], f["actual_value"], f["z_score"],
                    f["detection_method"], f["severity"],
                )
    return len(flags)


# ─────────────────────────────────────────────────────────────
# Scenario plans
# ─────────────────────────────────────────────────────────────
async def store_scenario_plan(pool: Any, plan: dict[str, Any]) -> UUID:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO scenario_plans
              (company_id, scenario_type, label, assumptions,
               projected_revenue, projected_gross_profit, projected_ebitda,
               projected_pl, projection_start, projection_end,
               based_on_forecast_run_id)
            VALUES ($1,$2,$3,$4::jsonb,$5,$6,$7,$8::jsonb,$9,$10,$11)
            ON CONFLICT (company_id, scenario_type, label, projection_start, projection_end)
            DO UPDATE SET
              assumptions = EXCLUDED.assumptions,
              projected_revenue = EXCLUDED.projected_revenue,
              projected_gross_profit = EXCLUDED.projected_gross_profit,
              projected_ebitda = EXCLUDED.projected_ebitda,
              projected_pl = EXCLUDED.projected_pl
            RETURNING id
            """,
            plan["company_id"], plan["scenario_type"], plan["label"],
            json.dumps(plan["assumptions"]),
            plan["projected_revenue"], plan["projected_gross_profit"],
            plan["projected_ebitda"],
            json.dumps(plan.get("quarters", [])),
            plan["projection_start"], plan["projection_end"],
            plan.get("based_on_forecast_run_id"),
        )
    return row["id"]


# ─────────────────────────────────────────────────────────────
# Documents (parameterized full-text search)
# ─────────────────────────────────────────────────────────────
async def search_documents(pool: Any, *, company_id: UUID, query: str,
                           limit: int = 5) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT dc.id, dc.document_id, dc.chunk_index, dc.content,
                   ts_rank(dc.tsv, plainto_tsquery('english', $2)) AS rank
            FROM document_chunks dc
            JOIN financial_documents fd ON fd.id = dc.document_id
            WHERE fd.company_id = $1
              AND dc.tsv @@ plainto_tsquery('english', $2)
            ORDER BY rank DESC
            LIMIT $3
            """,
            company_id, query, limit,
        )
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────
# Audit / agent_runs
# ─────────────────────────────────────────────────────────────
async def write_audit_log(pool: Any, entry: dict[str, Any]) -> UUID:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO audit_logs (workflow_run_id, agent_name, action,
                                    input_summary, output_summary, model_name,
                                    eval_score, duration_ms)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id
            """,
            entry.get("workflow_run_id"), entry["agent_name"], entry["action"],
            entry.get("input_summary"), entry.get("output_summary"),
            entry.get("model_name"), entry.get("eval_score"),
            entry.get("duration_ms"),
        )
    return row["id"]


async def write_agent_run(pool: Any, entry: dict[str, Any]) -> UUID:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO agent_runs (workflow_run_id, session_id, agent_name,
                                    input, output, guardrail_results, eval_results,
                                    started_at, completed_at, status, duration_ms)
            VALUES ($1,$2,$3,$4::jsonb,$5::jsonb,$6::jsonb,$7::jsonb,
                    $8,$9,$10,$11)
            RETURNING id
            """,
            entry.get("workflow_run_id"), entry.get("session_id"),
            entry["agent_name"],
            json.dumps(entry.get("input")), json.dumps(entry.get("output")),
            json.dumps(entry.get("guardrail_results")),
            json.dumps(entry.get("eval_results")),
            entry.get("started_at", datetime.utcnow()),
            entry.get("completed_at"),
            entry.get("status", "COMPLETED"),
            entry.get("duration_ms"),
        )
    return row["id"]
