"""
Commentary helpers — formatters used by FinancialCommentaryAgent.

These do NOT call the LLM; they prepare structured inputs (the LLM still
writes prose, but this gives it a consistent, grounded scaffold).
"""
from __future__ import annotations

from typing import Any


def format_financial_summary(analysis_data: dict[str, Any]) -> dict[str, Any]:
    """
    Reduce a full MonthEndAnalysisResult-shaped dict to a compact summary
    that's easy for the LLM to ground against.
    """
    summary: dict[str, Any] = {"period": analysis_data.get("period")}

    # Forecasts
    forecasts = analysis_data.get("forecasts", []) or []
    summary["forecasts"] = [
        {
            "metric": f.get("metric_name"),
            "model": f.get("model_name"),
            "next_point": f["forecast"][0]["point_forecast"] if f.get("forecast") else None,
            "lower_95": f["forecast"][0]["lower_bound_95"] if f.get("forecast") else None,
            "upper_95": f["forecast"][0]["upper_bound_95"] if f.get("forecast") else None,
            "mape": f.get("in_sample_mape"),
        }
        for f in forecasts
    ]

    # Variance
    vr = analysis_data.get("variance_report") or {}
    summary["ebitda_actual"] = vr.get("total_ebitda_actual")
    summary["ebitda_budget"] = vr.get("total_ebitda_budget")
    summary["ebitda_variance"] = vr.get("total_ebitda_variance")
    summary["top_drivers"] = vr.get("waterfall", [])[:3]
    summary["material_variances"] = [
        {"metric": r["metric_name"], "actual": r["actual_amount"],
         "budget": r["budget_amount"], "pct": r["variance_pct"],
         "favorable": r["is_favorable"], "materiality": r["materiality"]}
        for r in (vr.get("records", []) or [])
        if r.get("materiality") in ("MATERIAL", "CRITICAL")
    ]

    # Anomalies
    summary["anomalies"] = [
        {"metric": a["metric_name"], "expected": a["expected_value"],
         "actual": a["actual_value"], "z": a["z_score"], "severity": a["severity"]}
        for a in (analysis_data.get("anomalies", []) or [])
    ]

    return summary


def retrieve_variance_patterns(history: list[dict[str, Any]]) -> list[str]:
    """Detect recurring variance patterns (e.g. consistent S&M overrun)."""
    by_metric: dict[str, list[float]] = {}
    for r in history:
        by_metric.setdefault(r.get("metric_name", ""), []).append(float(r.get("variance_pct", 0)))
    patterns: list[str] = []
    for metric, pcts in by_metric.items():
        if len(pcts) < 3:
            continue
        if all(p > 5 for p in pcts[-3:]):
            patterns.append(f"{metric}: 3 consecutive months of >5% over-budget")
        elif all(p < -5 for p in pcts[-3:]):
            patterns.append(f"{metric}: 3 consecutive months of >5% under-budget")
    return patterns
