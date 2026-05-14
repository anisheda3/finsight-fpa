"""End-to-end pipeline test using only in-memory components.

Verifies:
    1. ingestion → variance → waterfall → grounding eval
    2. analysis_data passed to commentary survives a guardrail run
    3. forecast result schema validates after fitting
"""
from __future__ import annotations

from datetime import date
from uuid import uuid4

import numpy as np
import pytest

from agents.evals import CommentaryGroundingEval, ForecastAccuracyEval
from agents.guardrails import (
    CommentaryGroundingGuardrail, DataSanityGuardrail,
    ForecastReasonablenessGuardrail,
)
from agents.schemas import (
    ForecastPoint, ForecastResult, VarianceRecord, VarianceReport, WaterfallItem,
)
from agents.tools.forecasting_tools import fit_and_forecast, trailing_average
from agents.tools.ingestion_tools import parse_and_validate_actuals
from agents.tools.variance_tools import (
    compute_ebitda_waterfall, compute_variance_records,
)


COMPANY = uuid4()


def _make_history(n=36, base=8_000_000):
    return [
        {"period": date(2022, 1, 1) if i == 0
                  else date(2022 + (i // 12), ((i % 12) + 1), 1),
         "value": float(base + 100_000 * i + 200_000 * np.sin(2 * np.pi * (i % 12) / 12))}
        for i in range(n)
    ]


def test_ingestion_to_grounding_eval_roundtrip():
    # 1) Ingest a small CSV
    csv = (
        "period,department,metric_name,amount\n"
        "2024-09-01,consolidated,revenue,9100000\n"
        "2024-09-01,consolidated,cogs,3700000\n"
        "2024-09-01,consolidated,rd,950000\n"
    )
    parsed = parse_and_validate_actuals(csv, COMPANY, file_format="csv")
    assert parsed["accepted"] == 3
    assert parsed["rejected"] == 0
    assert parsed["source_file_hash"]

    # 2) DataSanityGuardrail passes on clean input
    sanity = DataSanityGuardrail().check({"rows": [r.model_dump() for r in parsed["rows"]]})
    assert sanity.passed, sanity.reason

    # 3) Variance + waterfall
    rows = [
        {"company_id": COMPANY, "period": date(2024, 9, 1), "department": None,
         "metric_name": "revenue", "actual_amount": 9_100_000, "budget_amount": 8_500_000},
        {"company_id": COMPANY, "period": date(2024, 9, 1), "department": None,
         "metric_name": "cogs",    "actual_amount": 3_700_000, "budget_amount": 3_400_000},
    ]
    vr = compute_variance_records(rows)
    waterfall, totals = compute_ebitda_waterfall(vr)
    report = VarianceReport(
        company_id=COMPANY, period=date(2024, 9, 1),
        records=[VarianceRecord(**r) for r in vr],
        waterfall=[WaterfallItem(**w) for w in waterfall],
        total_ebitda_actual=totals["ebitda_actual"],
        total_ebitda_budget=totals["ebitda_budget"],
        total_ebitda_variance=totals["ebitda_variance"],
    )
    assert report.waterfall[0].metric_name == "revenue"

    # 4) Commentary grounding works against analysis_data
    analysis_data = report.model_dump()
    g = CommentaryGroundingGuardrail()
    res = g.check({
        "narrative": "Revenue came in at ₹91 lakh against ₹85 lakh budget.",
        "figures_cited": [
            {"raw_text": "₹91 lakh", "normalized_value": 9_100_000.0},
            {"raw_text": "₹85 lakh", "normalized_value": 8_500_000.0},
        ],
        "analysis_data": analysis_data,
    })
    assert res.passed, res.reason

    # 5) CommentaryGroundingEval (regex pass) scores high
    e = CommentaryGroundingEval()
    score = e.run(
        {"narrative": "Revenue came in at ₹91 lakh against ₹85 lakh budget."},
        analysis_data=analysis_data,
    )
    assert score.passed
    assert score.details["regex_coverage"] == 1.0


def test_forecast_pipeline_produces_valid_schema():
    history = _make_history(36)
    raw = fit_and_forecast(history, horizon_months=6, holdout_months=3)
    fr = ForecastResult(
        company_id=COMPANY, metric_name="revenue",
        forecast=[ForecastPoint(**p) for p in raw["forecast"]],
        **{k: v for k, v in raw.items() if k != "forecast"},
    )
    assert fr.model_name in ("prophet", "sarima", "linear")
    assert len(fr.forecast) == 6
    # ForecastReasonablenessGuardrail
    g = ForecastReasonablenessGuardrail()
    avg = trailing_average(history, n=3)
    res = g.check({
        "trailing_3m_avg": avg,
        "forecast": raw["forecast"],
    })
    assert res.passed, res.reason


def test_forecast_accuracy_eval_against_simulated_actuals():
    history = _make_history(40)
    raw = fit_and_forecast(history, horizon_months=4, holdout_months=3)
    # Simulate "actuals" close to forecast (within 3% noise) → should pass
    actuals = []
    for p in raw["forecast"]:
        actuals.append({"period": p["period"],
                        "value": p["point_forecast"] * (1 + np.random.default_rng(7).normal(0, 0.02))})
    e = ForecastAccuracyEval()
    res = e.run({"forecast": raw["forecast"]}, actuals=actuals)
    assert res.passed, res.details
    assert res.details["mape_pct"] < 20
