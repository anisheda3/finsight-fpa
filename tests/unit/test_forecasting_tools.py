"""Unit tests for the statistical forecasting tools."""
from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from agents.tools.forecasting_tools import (
    fit_and_forecast,
    trailing_average,
)


def _gen_history(n_months: int, start: date = date(2021, 1, 1),
                 base: float = 1_000_000.0,
                 trend: float = 25_000.0,
                 seasonal_amp: float = 80_000.0,
                 noise: float = 10_000.0,
                 seed: int = 42):
    rng = np.random.default_rng(seed)
    out = []
    cur = start
    for i in range(n_months):
        seasonal = seasonal_amp * np.sin(2 * np.pi * (cur.month - 1) / 12.0)
        v = base + trend * i + seasonal + rng.normal(0, noise)
        out.append({"period": cur, "value": float(v)})
        # advance one month
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return out


def test_linear_fallback_runs_on_short_history():
    hist = _gen_history(6)
    res = fit_and_forecast(hist, horizon_months=3, holdout_months=2)
    assert res["model_name"] == "linear"
    assert len(res["forecast"]) == 3


def test_forecast_bounds_ordered():
    hist = _gen_history(36)
    res = fit_and_forecast(hist, horizon_months=6, holdout_months=3)
    for p in res["forecast"]:
        assert p["lower_bound_95"] <= p["lower_bound_80"] <= p["point_forecast"]
        assert p["point_forecast"] <= p["upper_bound_80"] <= p["upper_bound_95"]


def test_holdout_mape_reasonable_on_clean_signal():
    """A clean trend+seasonal series with low noise should yield MAPE < 25%."""
    hist = _gen_history(48, noise=5_000.0)
    res = fit_and_forecast(hist, horizon_months=3, holdout_months=3)
    assert res["in_sample_mape"] is not None
    assert res["in_sample_mape"] < 25.0, (
        f"MAPE {res['in_sample_mape']:.2f}% too high for clean data; "
        f"model={res['model_name']}"
    )


def test_run_id_present():
    hist = _gen_history(20)
    res = fit_and_forecast(hist, horizon_months=3, holdout_months=3)
    assert "run_id" in res and res["run_id"]


def test_forecast_periods_are_consecutive_months():
    hist = _gen_history(20, start=date(2022, 1, 1))
    res = fit_and_forecast(hist, horizon_months=4, holdout_months=3)
    periods = [p["period"] for p in res["forecast"]]
    # last hist period was (2022-01) + 19 months = 2023-08; next is 2023-09
    assert periods[0] == date(2023, 9, 1)
    assert periods[1] == date(2023, 10, 1)
    assert periods[2] == date(2023, 11, 1)
    assert periods[3] == date(2023, 12, 1)


def test_trailing_average():
    hist = [{"period": date(2024, i, 1), "value": float(i * 10)} for i in range(1, 6)]
    avg = trailing_average(hist, n=3)
    assert avg == pytest.approx((30 + 40 + 50) / 3)


def test_prefer_model_linear():
    hist = _gen_history(36)
    res = fit_and_forecast(hist, prefer_model="linear", horizon_months=3, holdout_months=3)
    assert res["model_name"] == "linear"
