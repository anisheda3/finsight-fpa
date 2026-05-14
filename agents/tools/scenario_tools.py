"""
Scenario propagation tools.

Given an anchor revenue forecast and a set of ratio assumptions, project a
quarterly P&L for BASE/BULL/BEAR over the next 4 quarters.
"""
from __future__ import annotations

from datetime import date
from typing import Any


def _add_months(d: date, months: int) -> date:
    m = d.month + months
    y = d.year + (m - 1) // 12
    m = ((m - 1) % 12) + 1
    return date(y, m, 1)


def _quarter_label(d: date) -> str:
    q = (d.month - 1) // 3 + 1
    return f"Q{q} {d.year}"


def propagate_scenario_pl(
    *,
    anchor_quarter_revenue: float,
    assumptions: dict[str, float],
    n_quarters: int = 4,
    start_period: date | None = None,
) -> list[dict[str, Any]]:
    """
    Project P&L for `n_quarters` starting at `start_period` (first day of quarter).

    Compounds revenue with `revenue_growth_qoq` (decimal, e.g. 0.05 for +5%) plus
    `macro_adjustment_pct`.  Cost lines are ratios applied to revenue.
    """
    g = float(assumptions.get("revenue_growth_qoq", 0.0))
    macro = float(assumptions.get("macro_adjustment_pct", 0.0))
    cogs_r = float(assumptions["cogs_ratio"])
    rd_r = float(assumptions["rd_ratio"])
    sm_r = float(assumptions["sm_ratio"])
    ga_r = float(assumptions["ga_ratio"])

    start = start_period or date.today().replace(day=1)
    out: list[dict[str, Any]] = []
    rev = float(anchor_quarter_revenue)
    for i in range(n_quarters):
        if i > 0:
            rev *= (1 + g + macro)
        cogs = rev * cogs_r
        gp = rev - cogs
        rd = rev * rd_r
        sm = rev * sm_r
        ga = rev * ga_r
        ebitda = gp - rd - sm - ga
        margin = ebitda / rev if rev else 0.0
        q_start = _add_months(start, i * 3)
        out.append({
            "quarter_label": _quarter_label(q_start),
            "revenue": rev,
            "cogs": cogs,
            "gross_profit": gp,
            "rd": rd,
            "sm": sm,
            "ga": ga,
            "ebitda": ebitda,
            "ebitda_margin": margin,
        })
    return out


def derive_ratios_from_history(
    revenue: float, cogs: float, rd: float, sm: float, ga: float
) -> dict[str, float]:
    """Compute COGS%, R&D%, S&M%, G&A% from a recent period (for BASE anchor)."""
    if revenue == 0:
        return {"cogs_ratio": 0, "rd_ratio": 0, "sm_ratio": 0, "ga_ratio": 0}
    return {
        "cogs_ratio": cogs / revenue,
        "rd_ratio":   rd   / revenue,
        "sm_ratio":   sm   / revenue,
        "ga_ratio":   ga   / revenue,
    }


# Default assumption presets for BASE / BULL / BEAR
SCENARIO_PRESETS = {
    "BASE": {"revenue_growth_qoq": 0.04, "macro_adjustment_pct": 0.00},
    "BULL": {"revenue_growth_qoq": 0.08, "macro_adjustment_pct": 0.02},
    "BEAR": {"revenue_growth_qoq": -0.02, "macro_adjustment_pct": -0.03},
}
