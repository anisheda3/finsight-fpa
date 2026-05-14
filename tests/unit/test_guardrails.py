"""Unit tests for the 3 spec-required guardrails."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from agents.guardrails import (
    CommentaryGroundingGuardrail,
    DataSanityGuardrail,
    ForecastReasonablenessGuardrail,
)


# ────────── DataSanityGuardrail ──────────
def test_data_sanity_passes_clean_input():
    g = DataSanityGuardrail()
    res = g.check({"rows": [
        {"metric_name": "revenue", "amount": 100.0, "period": date(2024, 9, 1)},
    ]})
    assert res.passed


def test_data_sanity_rejects_negative_revenue():
    g = DataSanityGuardrail()
    res = g.check({"rows": [
        {"metric_name": "revenue", "amount": -50.0, "period": date(2024, 9, 1)},
    ]})
    assert not res.passed
    assert "non-positive revenue" in res.reason.lower()


def test_data_sanity_rejects_future_period():
    g = DataSanityGuardrail()
    future = date.today() + timedelta(days=365)
    res = g.check({"rows": [
        {"metric_name": "revenue", "amount": 100.0, "period": future},
    ]})
    assert not res.passed
    assert "future" in res.reason.lower()


@pytest.mark.asyncio
async def test_data_sanity_async_check():
    g = DataSanityGuardrail()
    res = await g.async_check({"rows": [{"metric_name": "revenue", "amount": 100.0,
                                         "period": date(2024, 9, 1)}]})
    assert res.passed


# ────────── ForecastReasonablenessGuardrail ──────────
def test_forecast_reasonableness_passes_close_forecast():
    g = ForecastReasonablenessGuardrail()
    res = g.check({
        "trailing_3m_avg": 1_000_000.0,
        "forecast": [{"point_forecast": 1_050_000.0}],
    })
    assert res.passed


def test_forecast_reasonableness_rejects_runaway():
    g = ForecastReasonablenessGuardrail()
    res = g.check({
        "trailing_3m_avg": 1_000_000.0,
        "forecast": [{"point_forecast": 5_000_000.0}],     # 400% above
    })
    assert not res.passed
    assert "deviates" in res.reason.lower()


def test_forecast_reasonableness_no_baseline_passes():
    g = ForecastReasonablenessGuardrail()
    res = g.check({"forecast": [{"point_forecast": 999.0}]})
    assert res.passed


# ────────── CommentaryGroundingGuardrail (the corrected one) ──────────
def test_commentary_grounding_passes_when_all_figures_traceable():
    g = CommentaryGroundingGuardrail()
    analysis_ctx = {
        "variance_records": [
            {"metric_name": "revenue", "actual_amount": 1_500_000.0,
             "budget_amount": 1_000_000.0},
        ],
    }
    res = g.check({
        "narrative": "Revenue came in at ₹15 lakh, beating the ₹10 lakh budget.",
        "figures_cited": [
            {"raw_text": "₹15 lakh", "normalized_value": 1_500_000.0},
            {"raw_text": "₹10 lakh", "normalized_value": 1_000_000.0},
        ],
        "analysis_data": analysis_ctx,
    })
    assert res.passed


def test_commentary_grounding_rejects_hallucinated_figures():
    g = CommentaryGroundingGuardrail()
    analysis_ctx = {"variance_records": [{"actual_amount": 1_000_000.0}]}
    res = g.check({
        "narrative": "Revenue was ₹50 crore, miles above the ₹40 crore plan.",
        "figures_cited": [
            {"raw_text": "₹50 crore", "normalized_value": 500_000_000.0},
            {"raw_text": "₹40 crore", "normalized_value": 400_000_000.0},
            {"raw_text": "₹30 crore", "normalized_value": 300_000_000.0},
            {"raw_text": "₹20 crore", "normalized_value": 200_000_000.0},
        ],
        "analysis_data": analysis_ctx,
    })
    assert not res.passed
    assert "not traceable" in res.reason.lower()


def test_commentary_grounding_uses_underscore_analysis_context_first():
    """Demonstrates the fix: the guardrail reads from _analysis_context, not allowed_figures."""
    g = CommentaryGroundingGuardrail()
    res = g.check({
        "narrative": "Revenue was ₹15 lakh.",
        "figures_cited": [{"raw_text": "₹15 lakh", "normalized_value": 1_500_000.0}],
        "_analysis_context": {"top_metric": 1_500_000.0},
    })
    assert res.passed


def test_commentary_grounding_no_context_passes_through():
    """Without analysis context, guardrail can't ground; let downstream eval catch it."""
    g = CommentaryGroundingGuardrail()
    res = g.check({
        "narrative": "Revenue was ₹50 crore.",
        "figures_cited": [{"raw_text": "₹50 crore", "normalized_value": 500_000_000.0}],
    })
    assert res.passed
