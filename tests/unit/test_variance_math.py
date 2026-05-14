"""Unit tests for variance computation, materiality, and EBITDA waterfall."""
from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest

from agents.tools.variance_tools import (
    KpiDef,
    assign_waterfall_ranks,
    compute_ebitda_waterfall,
    compute_variance_records,
    flag_for_hitl,
)


COMPANY = uuid4()
PERIOD = date(2024, 9, 1)


def _row(metric, actual, budget, dept=None):
    return {
        "company_id": COMPANY,
        "period": PERIOD,
        "department": dept,
        "metric_name": metric,
        "actual_amount": actual,
        "budget_amount": budget,
    }


def test_basic_variance_arithmetic():
    rows = [_row("revenue", 110.0, 100.0)]
    out = compute_variance_records(rows)
    assert out[0]["variance_amount"] == pytest.approx(10.0)
    assert out[0]["variance_pct"] == pytest.approx(10.0)


def test_negative_budget_uses_absolute_in_pct():
    """A negative budget shouldn't make the % flip sign."""
    rows = [_row("rd", -90.0, -100.0)]
    out = compute_variance_records(rows)
    # actual - budget = -90 - (-100) = +10  → 10%
    assert out[0]["variance_amount"] == pytest.approx(10.0)
    assert out[0]["variance_pct"] == pytest.approx(10.0)


def test_zero_budget_handled():
    rows = [_row("revenue", 50.0, 0.0)]
    out = compute_variance_records(rows)
    assert out[0]["variance_pct"] == float("inf")


def test_materiality_default_bands():
    """Default threshold 5% → bands at 2/5/15."""
    rows = [
        _row("revenue", 101.0, 100.0),   # +1%   → IMMATERIAL
        _row("revenue", 103.0, 100.0),   # +3%   → NOTABLE
        _row("revenue", 110.0, 100.0),   # +10%  → MATERIAL
        _row("revenue", 120.0, 100.0),   # +20%  → CRITICAL
    ]
    out = compute_variance_records(rows)
    assert [r["materiality"] for r in out] == [
        "IMMATERIAL", "NOTABLE", "MATERIAL", "CRITICAL",
    ]


def test_materiality_threshold_from_kpi_def():
    """A higher threshold (7.5%) shifts the bands."""
    rows = [_row("rd", 106.0, 100.0)]    # +6% — would be MATERIAL at 5%, but…
    kpi = {"rd": KpiDef("rd", favorable_direction="DOWN", materiality_threshold_pct=7.5)}
    out = compute_variance_records(rows, kpi_defs=kpi)
    # 6% < 7.5% but > 7.5*0.4=3% → NOTABLE
    assert out[0]["materiality"] == "NOTABLE"


def test_favorable_unfavorable_revenue():
    """Revenue UP is favorable; revenue DOWN is unfavorable."""
    rows = [
        _row("revenue", 110.0, 100.0),    # over budget → favorable (UP)
        _row("revenue",  90.0, 100.0),    # under budget → unfavorable
    ]
    out = compute_variance_records(rows)
    assert out[0]["is_favorable"] is True
    assert out[1]["is_favorable"] is False


def test_favorable_unfavorable_cost():
    """Cost UP is unfavorable; cost DOWN is favorable."""
    kpi = {"cogs": KpiDef("cogs", favorable_direction="DOWN")}
    rows = [
        _row("cogs", 110.0, 100.0),       # over budget on cost → unfavorable
        _row("cogs",  90.0, 100.0),       # under budget on cost → favorable
    ]
    out = compute_variance_records(rows, kpi_defs=kpi)
    assert out[0]["is_favorable"] is False
    assert out[1]["is_favorable"] is True


def test_ebitda_waterfall_signs_and_sums():
    """Contributions should sum to total EBITDA Δ."""
    rows = [
        _row("revenue", 1100.0, 1000.0),   # +100 to EBITDA
        _row("cogs",     520.0,  500.0),   # +20 cost  → -20 to EBITDA
        _row("rd",        90.0,  100.0),   # -10 cost  → +10 to EBITDA
        _row("sm",       210.0,  200.0),   # +10 cost  → -10 to EBITDA
        _row("ga",       100.0,  100.0),   # 0
    ]
    vr = compute_variance_records(rows)
    waterfall, totals = compute_ebitda_waterfall(vr)

    # Largest absolute contribution first → revenue (+100)
    assert waterfall[0]["metric_name"] == "revenue"
    assert waterfall[0]["contribution"] == pytest.approx(100.0)

    # Sum of contributions == total EBITDA variance
    total_contrib = sum(w["contribution"] for w in waterfall)
    assert total_contrib == pytest.approx(totals["ebitda_variance"])
    assert totals["ebitda_variance"] == pytest.approx(100 - 20 + 10 - 10 + 0)  # 80


def test_waterfall_rank_stamped_on_records():
    rows = [
        _row("revenue", 1100.0, 1000.0),
        _row("cogs",     520.0,  500.0),
    ]
    vr = compute_variance_records(rows)
    waterfall, _ = compute_ebitda_waterfall(vr)
    vr = assign_waterfall_ranks(vr, waterfall)
    rev_rec = next(r for r in vr if r["metric_name"] == "revenue")
    assert rev_rec["waterfall_rank"] == 1


def test_flag_for_hitl_only_material_or_critical():
    rows = [
        _row("revenue", 101.0, 100.0),     # IMMATERIAL
        _row("revenue", 110.0, 100.0),     # MATERIAL
        _row("revenue", 120.0, 100.0),     # CRITICAL
    ]
    vr = compute_variance_records(rows)
    flagged = flag_for_hitl(vr)
    assert len(flagged) == 2
    assert {r["materiality"] for r in flagged} == {"MATERIAL", "CRITICAL"}
