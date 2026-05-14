"""Unit tests for the 2 spec-required evals."""
from __future__ import annotations

from datetime import date

from agents.evals import CommentaryGroundingEval, ForecastAccuracyEval


def test_forecast_accuracy_high_score_on_perfect_match():
    e = ForecastAccuracyEval()
    output = {"forecast": [
        {"period": date(2024, 9, 1), "point_forecast": 100.0},
        {"period": date(2024, 10, 1), "point_forecast": 110.0},
    ]}
    actuals = [
        {"period": date(2024, 9, 1), "value": 100.0},
        {"period": date(2024, 10, 1), "value": 110.0},
    ]
    res = e.run(output, actuals=actuals)
    assert res.passed
    assert res.score == 1.0
    assert res.details["mape_pct"] == 0.0


def test_forecast_accuracy_fails_on_high_mape():
    e = ForecastAccuracyEval()
    output = {"forecast": [{"period": date(2024, 9, 1), "point_forecast": 50.0}]}
    actuals = [{"period": date(2024, 9, 1), "value": 100.0}]
    res = e.run(output, actuals=actuals)
    assert not res.passed
    assert res.details["mape_pct"] == 50.0


def test_forecast_accuracy_no_actuals_passes_neutrally():
    e = ForecastAccuracyEval()
    res = e.run({"forecast": [{"period": date(2024, 9, 1), "point_forecast": 100.0}]},
                actuals=[])
    assert res.passed       # nothing to compare → not a failure


def test_commentary_grounding_full_match():
    e = CommentaryGroundingEval()
    output = {"narrative": "Revenue was ₹15 lakh, vs ₹10 lakh budget."}
    ctx = {"actuals": 1_500_000.0, "budget": 1_000_000.0}
    res = e.run(output, analysis_data=ctx)
    assert res.passed
    assert res.details["regex_coverage"] == 1.0


def test_commentary_grounding_partial_hallucination():
    e = CommentaryGroundingEval()
    output = {"narrative": "Revenue was ₹15 lakh, but EBITDA hit ₹50 crore."}
    ctx = {"actuals": 1_500_000.0}
    res = e.run(output, analysis_data=ctx)
    # 1 of 2 figures grounded → 0.5 < 0.85 threshold
    assert not res.passed
    assert res.details["n_ungrounded"] >= 1
