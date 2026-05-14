"""
Variance analysis tools.

Implements FP&A conventions:
    - absolute variance     = actual - budget
    - percentage variance   = (actual - budget) / |budget| * 100
    - materiality           = bucketed by `kpi_definitions.materiality_threshold_pct`
                              IMMATERIAL (<thr/2.5)
                              NOTABLE     (<thr)
                              MATERIAL    (<3*thr)
                              CRITICAL    (>=3*thr)
                              (default thr=5% → 2/5/15 bands per spec)
    - favorable/unfavorable based on `kpi_definitions.favorable_direction`
    - EBITDA waterfall      = signed contribution of each metric variance
                              to total EBITDA delta (revenue & gross_profit are
                              positive contributors; cost lines invert)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# Default materiality bands (used if KPI definition is missing).
_DEFAULT_THRESHOLD_PCT = 5.0


# Sign of metric in EBITDA = gross_profit - rd - sm - ga
#                          = revenue - cogs - rd - sm - ga
_EBITDA_SIGN: dict[str, int] = {
    "revenue":      +1,
    "cogs":         -1,
    "gross_profit": +1,   # alternative formulation
    "rd":           -1,
    "sm":           -1,
    "ga":           -1,
    "ebitda":       +1,   # included for completeness; usually skipped from waterfall
}


@dataclass
class KpiDef:
    metric_name: str
    favorable_direction: str = "UP"   # "UP" or "DOWN"
    materiality_threshold_pct: float = _DEFAULT_THRESHOLD_PCT


def _classify_materiality(abs_pct: float, threshold_pct: float) -> str:
    """Bucket a |variance%| into IMMATERIAL/NOTABLE/MATERIAL/CRITICAL.
    threshold_pct can be a Decimal from DB; convert to float."""
    thr = float(threshold_pct)
    if abs_pct < thr * 0.4:
        return "IMMATERIAL"
    if abs_pct < thr:
        return "NOTABLE"
    if abs_pct < thr * 3.0:
        return "MATERIAL"
    return "CRITICAL"


def _is_favorable(variance_amount: float, favorable_direction: str) -> bool:
    """Revenue-up-good vs cost-up-bad logic."""
    if favorable_direction == "UP":
        return variance_amount > 0
    return variance_amount < 0


def compute_variance_records(
    rows: list[dict[str, Any]],
    kpi_defs: dict[str, KpiDef] | None = None,
) -> list[dict[str, Any]]:
    """
    rows : iterable of dicts with keys
        company_id, period, department, metric_name,
        actual_amount, budget_amount, actual_id?, budget_id?
    kpi_defs : metric_name -> KpiDef.  Missing metrics use defaults.
    """
    kpi_defs = kpi_defs or {}
    out: list[dict[str, Any]] = []

    for r in rows:
        actual = float(r["actual_amount"])
        budget = float(r["budget_amount"])
        variance_amount = actual - budget

        if budget == 0:
            variance_pct = 0.0 if variance_amount == 0 else float("inf")
        else:
            variance_pct = (variance_amount / abs(budget)) * 100.0

        kpi = kpi_defs.get(r["metric_name"], KpiDef(metric_name=r["metric_name"]))
        materiality = _classify_materiality(abs(variance_pct), kpi.materiality_threshold_pct)
        is_favorable = _is_favorable(variance_amount, kpi.favorable_direction)

        out.append({
            "company_id":      r["company_id"],
            "period":          r["period"],
            "department":      r.get("department"),
            "metric_name":     r["metric_name"],
            "actual_amount":   actual,
            "budget_amount":   budget,
            "variance_amount": variance_amount,
            "variance_pct":    variance_pct,
            "is_favorable":    is_favorable,
            "materiality":     materiality,
            "actual_id":       r.get("actual_id"),
            "budget_id":       r.get("budget_id"),
        })
    return out


def compute_ebitda_waterfall(
    variance_records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    """
    Decompose total EBITDA Δ into per-metric contributions, ranked by |impact|.

    EBITDA = revenue - cogs - rd - sm - ga
           (gross_profit is derived; we use the line items)

    For waterfall purposes we use the LINE-ITEM variances (revenue, cogs, rd,
    sm, ga) so contributions sum to total EBITDA Δ (avoiding double-count
    with gross_profit).

    Returns
    -------
    (waterfall_items, totals)
        waterfall_items: list[{metric_name, contribution, rank}]
        totals: {ebitda_actual, ebitda_budget, ebitda_variance}
    """
    line_items = {"revenue", "cogs", "rd", "sm", "ga"}

    # Aggregate by metric across departments
    agg: dict[str, dict[str, float]] = {}
    for r in variance_records:
        m = r["metric_name"]
        if m not in line_items and m != "ebitda":
            continue
        bucket = agg.setdefault(m, {"actual": 0.0, "budget": 0.0, "variance": 0.0})
        bucket["actual"]   += float(r["actual_amount"])
        bucket["budget"]   += float(r["budget_amount"])
        bucket["variance"] += float(r["variance_amount"])

    # Compute contributions to EBITDA Δ
    contribs: list[tuple[str, float]] = []
    for m in line_items:
        if m not in agg:
            continue
        sign = _EBITDA_SIGN.get(m, +1)
        contribs.append((m, sign * agg[m]["variance"]))

    # Rank by absolute impact (largest first)
    contribs.sort(key=lambda x: abs(x[1]), reverse=True)
    waterfall = [
        {"metric_name": m, "contribution": c, "rank": i + 1}
        for i, (m, c) in enumerate(contribs)
    ]

    # Totals — prefer reported EBITDA if present, else derive
    if "ebitda" in agg:
        ebitda_actual = agg["ebitda"]["actual"]
        ebitda_budget = agg["ebitda"]["budget"]
    else:
        ebitda_actual = sum(_EBITDA_SIGN[m] * agg[m]["actual"] for m in line_items if m in agg)
        ebitda_budget = sum(_EBITDA_SIGN[m] * agg[m]["budget"] for m in line_items if m in agg)
    ebitda_variance = ebitda_actual - ebitda_budget

    totals = {
        "ebitda_actual":   ebitda_actual,
        "ebitda_budget":   ebitda_budget,
        "ebitda_variance": ebitda_variance,
    }
    return waterfall, totals


def assign_waterfall_ranks(
    variance_records: list[dict[str, Any]],
    waterfall: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Stamp waterfall_rank onto each variance record (matched on metric_name)."""
    rank_map = {w["metric_name"]: w["rank"] for w in waterfall}
    for r in variance_records:
        r["waterfall_rank"] = rank_map.get(r["metric_name"])
    return variance_records


def flag_for_hitl(
    variance_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return only MATERIAL or CRITICAL records (the HITL queue)."""
    return [r for r in variance_records if r["materiality"] in ("MATERIAL", "CRITICAL")]
