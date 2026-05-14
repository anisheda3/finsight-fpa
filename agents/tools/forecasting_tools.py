"""
Forecasting tools — REAL statistical/ML models, not LLM guesses.

Strategy:
    1. If history >= 24 months and prophet is installed → Prophet (yearly seasonality).
    2. Else if history >= 12 months and statsmodels installed → SARIMA(1,1,1)(1,1,0,12).
    3. Else → linear extrapolation.

Every model:
    - holds out the last `holdout_months` for in-sample MAPE
    - returns point forecast + 80% and 95% confidence intervals
    - reports model_name, model_params, run_id
"""
from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Internal data structure (not a Pydantic schema — that lives in
# ForecastResult; this is the raw tool output the agent consumes).
# ─────────────────────────────────────────────────────────────
@dataclass
class _ForecastOutput:
    periods: list[date]
    point: list[float]
    lo80: list[float]
    hi80: list[float]
    lo95: list[float]
    hi95: list[float]
    model_name: str
    model_params: dict[str, Any]
    in_sample_mape: float | None
    holdout_months: int
    horizon_months: int
    training_start: date | None
    training_end: date | None
    selected_reason: str
    fallback_reason: str | None


# ─────────────────────────────────────────────────────────────
# Math helpers
# ─────────────────────────────────────────────────────────────
def _mape(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Mean Absolute Percentage Error.  Skips zero actuals."""
    mask = actual != 0
    if not mask.any():
        return float("nan")
    return float(np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100.0)


def _next_month_starts(last_period: date, n: int) -> list[date]:
    """Return the next n month-start dates after `last_period`."""
    out: list[date] = []
    cur = last_period
    for _ in range(n):
        # advance to next month's first day
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
        out.append(cur)
    return out


def _z_for_ci(level: float) -> float:
    """Two-sided z-score for the given confidence level."""
    # 80% -> 1.2816, 95% -> 1.9600
    if math.isclose(level, 0.80):
        return 1.2816
    if math.isclose(level, 0.95):
        return 1.9600
    # generic — use inverse normal approximation
    from statistics import NormalDist
    return NormalDist().inv_cdf(0.5 + level / 2.0)


# ─────────────────────────────────────────────────────────────
# Model 1 — Linear extrapolation (always-available fallback)
# ─────────────────────────────────────────────────────────────
def _fit_linear(
    history: pd.DataFrame,
    horizon: int,
    holdout: int,
) -> _ForecastOutput:
    """OLS y = a + b * t with residual-std-based CIs."""
    df = history.copy().sort_values("period").reset_index(drop=True)
    df["t"] = np.arange(len(df))

    if len(df) <= holdout + 2:
        # not enough data — fit on everything, no holdout MAPE
        train = df
        mape = None
    else:
        train = df.iloc[:-holdout]
        test = df.iloc[-holdout:]

    x = train["t"].to_numpy(dtype=float)
    y = train["value"].to_numpy(dtype=float)
    b, a = np.polyfit(x, y, 1) if len(x) >= 2 else (0.0, float(y.mean()))

    # In-sample residual std
    y_hat_train = a + b * x
    residuals = y - y_hat_train
    sigma = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else 0.0

    # Holdout MAPE
    if "test" in dir() and len(df) > holdout + 2:  # noqa: PLR0124
        test_pred = a + b * test["t"].to_numpy(dtype=float)
        mape = _mape(test["value"].to_numpy(dtype=float), test_pred)
        # refit on full history for production forecast
        x_full = df["t"].to_numpy(dtype=float)
        y_full = df["value"].to_numpy(dtype=float)
        b, a = np.polyfit(x_full, y_full, 1) if len(x_full) >= 2 else (0.0, float(y_full.mean()))
        # recompute sigma on full
        y_hat_full = a + b * x_full
        sigma = float(np.std(y_full - y_hat_full, ddof=1)) if len(x_full) > 1 else sigma
    else:
        mape = None

    # Forecast
    future_t = np.arange(len(df), len(df) + horizon, dtype=float)
    point = a + b * future_t
    z80, z95 = _z_for_ci(0.80), _z_for_ci(0.95)

    return _ForecastOutput(
        periods=_next_month_starts(df["period"].iloc[-1], horizon),
        point=point.tolist(),
        lo80=(point - z80 * sigma).tolist(),
        hi80=(point + z80 * sigma).tolist(),
        lo95=(point - z95 * sigma).tolist(),
        hi95=(point + z95 * sigma).tolist(),
        model_name="linear",
        model_params={"intercept": float(a), "slope": float(b), "residual_std": sigma},
        in_sample_mape=mape,
        holdout_months=holdout,
        horizon_months=horizon,
        training_start=df["period"].iloc[0],
        training_end=df["period"].iloc[-1],
        selected_reason="fallback: insufficient history or other models unavailable",
        fallback_reason=None,
    )


# ─────────────────────────────────────────────────────────────
# Model 2 — SARIMA (statsmodels)
# ─────────────────────────────────────────────────────────────
def _fit_sarima(
    history: pd.DataFrame,
    horizon: int,
    holdout: int,
) -> _ForecastOutput | None:
    try:
        from statsmodels.tsa.statespace.sarimax import SARIMAX
    except ImportError:
        return None

    df = history.copy().sort_values("period").reset_index(drop=True)
    if len(df) < 12 + holdout:
        return None

    train = df.iloc[:-holdout] if holdout > 0 else df
    test = df.iloc[-holdout:] if holdout > 0 else None

    order = (1, 1, 1)
    seasonal_order = (1, 1, 0, 12)
    try:
        model = SARIMAX(
            train["value"].to_numpy(dtype=float),
            order=order,
            seasonal_order=seasonal_order,
            enforce_stationarity=False,
            enforce_invertibility=False,
        )
        fit = model.fit(disp=False)
    except Exception as e:  # statsmodels can raise many things
        logger.warning("SARIMA fit failed: %s", e)
        return None

    # Holdout MAPE
    mape = None
    if test is not None and len(test) > 0:
        try:
            test_pred = fit.forecast(steps=len(test))
            mape = _mape(test["value"].to_numpy(dtype=float), np.asarray(test_pred))
        except Exception as e:
            logger.warning("SARIMA holdout forecast failed: %s", e)

        # Refit on full data for production forecast
        try:
            full_model = SARIMAX(
                df["value"].to_numpy(dtype=float),
                order=order,
                seasonal_order=seasonal_order,
                enforce_stationarity=False,
                enforce_invertibility=False,
            )
            fit = full_model.fit(disp=False)
        except Exception as e:
            logger.warning("SARIMA full refit failed, using train-only fit: %s", e)

    try:
        fc_res = fit.get_forecast(steps=horizon)
        point = np.asarray(fc_res.predicted_mean, dtype=float)
        ci80 = fc_res.conf_int(alpha=0.20)
        ci95 = fc_res.conf_int(alpha=0.05)
        # ci is a numpy array shape (horizon, 2)
        ci80_arr = np.asarray(ci80, dtype=float)
        ci95_arr = np.asarray(ci95, dtype=float)
    except Exception as e:
        logger.warning("SARIMA forecast extraction failed: %s", e)
        return None


    # Reject if any bounds are NaN/Inf (under-parameterized fit)
    arrs = [point, ci80_arr[:, 0], ci80_arr[:, 1], ci95_arr[:, 0], ci95_arr[:, 1]]
    if any(not np.all(np.isfinite(a)) for a in arrs):
        logger.warning("SARIMA produced non-finite forecast bounds; falling through")
        return None

    return _ForecastOutput(
        periods=_next_month_starts(df["period"].iloc[-1], horizon),
        point=point.tolist(),
        lo80=ci80_arr[:, 0].tolist(),
        hi80=ci80_arr[:, 1].tolist(),
        lo95=ci95_arr[:, 0].tolist(),
        hi95=ci95_arr[:, 1].tolist(),
        model_name="sarima",
        model_params={"order": order, "seasonal_order": seasonal_order},
        in_sample_mape=mape,
        holdout_months=holdout,
        horizon_months=horizon,
        training_start=df["period"].iloc[0],
        training_end=df["period"].iloc[-1],
        selected_reason="SARIMA selected: monthly history with seasonality",
        fallback_reason=None,
    )


# ─────────────────────────────────────────────────────────────
# Model 3 — Prophet
# ─────────────────────────────────────────────────────────────
def _fit_prophet(
    history: pd.DataFrame,
    horizon: int,
    holdout: int,
) -> _ForecastOutput | None:
    try:
        from prophet import Prophet
    except ImportError:
        return None

    df = history.copy().sort_values("period").reset_index(drop=True)
    if len(df) < 24 + holdout:
        return None

    prophet_df = pd.DataFrame({
        "ds": pd.to_datetime(df["period"]),
        "y": df["value"].astype(float),
    })

    if holdout > 0 and len(df) > holdout + 2:
        train = prophet_df.iloc[:-holdout]
        test = prophet_df.iloc[-holdout:]
    else:
        train = prophet_df
        test = None

    try:
        m = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=False,
            daily_seasonality=False,
            interval_width=0.80,  # we'll compute 95 manually below
        )
        m.fit(train)
    except Exception as e:
        logger.warning("Prophet fit failed: %s", e)
        return None

    mape = None
    if test is not None and len(test) > 0:
        try:
            test_pred = m.predict(test[["ds"]])
            mape = _mape(test["y"].to_numpy(dtype=float),
                         test_pred["yhat"].to_numpy(dtype=float))
        except Exception as e:
            logger.warning("Prophet holdout predict failed: %s", e)

        # Refit on full
        try:
            m = Prophet(
                yearly_seasonality=True,
                weekly_seasonality=False,
                daily_seasonality=False,
                interval_width=0.80,
            )
            m.fit(prophet_df)
        except Exception as e:
            logger.warning("Prophet full refit failed: %s", e)

    future = m.make_future_dataframe(periods=horizon, freq="MS")
    forecast = m.predict(future).tail(horizon)

    point = forecast["yhat"].to_numpy(dtype=float)
    lo80 = forecast["yhat_lower"].to_numpy(dtype=float)
    hi80 = forecast["yhat_upper"].to_numpy(dtype=float)

    # Approximate 95% CI from the 80% half-width (z95/z80 ratio)
    half80 = (hi80 - lo80) / 2.0
    half95 = half80 * (_z_for_ci(0.95) / _z_for_ci(0.80))
    lo95 = point - half95
    hi95 = point + half95


    if not (np.all(np.isfinite(point)) and np.all(np.isfinite(lo80)) and np.all(np.isfinite(hi80))):
        logger.warning("Prophet produced non-finite forecast bounds; falling through")
        return None

    return _ForecastOutput(
        periods=_next_month_starts(df["period"].iloc[-1], horizon),
        point=point.tolist(),
        lo80=lo80.tolist(),
        hi80=hi80.tolist(),
        lo95=lo95.tolist(),
        hi95=hi95.tolist(),
        model_name="prophet",
        model_params={"yearly_seasonality": True, "interval_width_native": 0.80},
        in_sample_mape=mape,
        holdout_months=holdout,
        horizon_months=horizon,
        training_start=df["period"].iloc[0],
        training_end=df["period"].iloc[-1],
        selected_reason="Prophet selected: ≥24mo of monthly data, native seasonality",
        fallback_reason=None,
    )


# ─────────────────────────────────────────────────────────────
# Public tool entrypoint (called by ForecastingAgent)
# ─────────────────────────────────────────────────────────────
def fit_and_forecast(
    history: list[dict[str, Any]] | pd.DataFrame,
    horizon_months: int = 6,
    holdout_months: int = 3,
    prefer_model: str | None = None,
) -> dict[str, Any]:
    """
    Fit the best available statistical model and produce a forecast.

    Parameters
    ----------
    history : list of {"period": date, "value": float} or DataFrame
    horizon_months : forecast horizon
    holdout_months : last N months held out for MAPE
    prefer_model : "prophet" | "sarima" | "linear" | None (auto)

    Returns
    -------
    dict with keys matching ForecastResult fields (excluding company_id, metric_name).
    """
    if isinstance(history, list):
        df = pd.DataFrame(history)
    else:
        df = history.copy()
    if df.empty:
        raise ValueError("history is empty")
    if "period" not in df.columns or "value" not in df.columns:
        raise ValueError("history must have 'period' and 'value' columns")

    df["period"] = pd.to_datetime(df["period"]).dt.date
    df = df.sort_values("period").reset_index(drop=True)

    run_id = str(uuid.uuid4())
    fallback_reason: str | None = None
    out: _ForecastOutput | None = None

    # Selection logic
    candidates: list[str]
    if prefer_model:
        candidates = [prefer_model]
    elif len(df) >= 24:
        candidates = ["prophet", "sarima", "linear"]
    elif len(df) >= 12:
        candidates = ["sarima", "linear"]
    else:
        candidates = ["linear"]

    for cand in candidates:
        if cand == "prophet":
            out = _fit_prophet(df, horizon_months, holdout_months)
            if out is None:
                fallback_reason = "Prophet unavailable or fit failed"
        elif cand == "sarima":
            out = _fit_sarima(df, horizon_months, holdout_months)
            if out is None:
                fallback_reason = (fallback_reason + "; " if fallback_reason else "") + \
                                  "SARIMA unavailable or fit failed"
        elif cand == "linear":
            out = _fit_linear(df, horizon_months, holdout_months)
        if out is not None:
            break

    assert out is not None, "linear fallback should always succeed"
    if fallback_reason and out.model_name != candidates[0]:
        out.fallback_reason = fallback_reason

    return {
        "run_id": run_id,
        "model_name": out.model_name,
        "model_params": out.model_params,
        "in_sample_mape": out.in_sample_mape,
        "holdout_months": out.holdout_months,
        "horizon_months": out.horizon_months,
        "training_start_period": out.training_start,
        "training_end_period": out.training_end,
        "selected_reason": out.selected_reason,
        "fallback_reason": out.fallback_reason,
        "forecast": [
            {
                "period": p,
                "point_forecast": pt,
                "lower_bound_80": lo80,
                "upper_bound_80": hi80,
                "lower_bound_95": lo95,
                "upper_bound_95": hi95,
            }
            for p, pt, lo80, hi80, lo95, hi95 in zip(
                out.periods, out.point, out.lo80, out.hi80, out.lo95, out.hi95
            )
        ],
    }


def trailing_average(history: list[dict[str, Any]], n: int = 3) -> float | None:
    """Used by ForecastReasonablenessGuardrail."""
    if not history:
        return None
    vals = [float(h["value"]) for h in history[-n:]]
    return sum(vals) / len(vals) if vals else None
