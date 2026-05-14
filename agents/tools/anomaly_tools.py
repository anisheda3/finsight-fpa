"""
Anomaly detection tools — z-score and IQR over the metric history.

Severity is assigned based on either the z-score magnitude (z-score method)
or the IQR multiple (IQR method).
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Severity buckets
# ─────────────────────────────────────────────────────────────
def _severity_from_z(z: float) -> str:
    az = abs(z)
    if az >= 4.0:
        return "CRITICAL"
    if az >= 3.0:
        return "HIGH"
    if az >= 2.0:
        return "MEDIUM"
    return "LOW"


def _severity_from_iqr_mult(mult: float) -> str:
    am = abs(mult)
    if am >= 4.0:
        return "CRITICAL"
    if am >= 3.0:
        return "HIGH"
    if am >= 2.0:
        return "MEDIUM"
    return "LOW"


# ─────────────────────────────────────────────────────────────
# Detectors
# ─────────────────────────────────────────────────────────────
def detect_zscore_anomalies(
    history: list[dict[str, Any]],
    period_to_check: date | None = None,
    z_threshold: float = 2.0,
    min_history: int = 6,
) -> list[dict[str, Any]]:
    """
    Flag periods whose value is `z_threshold` standard deviations from the mean
    of all OTHER periods.

    If `period_to_check` is given, only that period is evaluated; otherwise all.
    """
    if len(history) < min_history:
        return []

    df = sorted(history, key=lambda r: r["period"])
    values = np.array([float(r["value"]) for r in df])
    periods = [r["period"] for r in df]

    out: list[dict[str, Any]] = []
    for i, p in enumerate(periods):
        if period_to_check is not None and p != period_to_check:
            continue
        # Leave-one-out mean/std to avoid the test point biasing its own score
        others = np.delete(values, i)
        mu = float(np.mean(others))
        sigma = float(np.std(others, ddof=1)) if len(others) > 1 else 0.0
        # If the rest of the series is perfectly flat, leave-one-out std=0 would
        # mask the outlier.  Fall back to full-series std in that case.
        if sigma == 0:
            sigma = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
        if sigma == 0:
            continue
        z = (values[i] - mu) / sigma
        if abs(z) >= z_threshold:
            out.append({
                "period":           p,
                "expected_value":   mu,
                "actual_value":     float(values[i]),
                "z_score":          float(z),
                "detection_method": "zscore",
                "severity":         _severity_from_z(z),
            })
    return out


def detect_iqr_anomalies(
    history: list[dict[str, Any]],
    period_to_check: date | None = None,
    iqr_multiplier: float = 1.5,
    min_history: int = 6,
) -> list[dict[str, Any]]:
    """
    Flag periods outside [Q1 - k*IQR, Q3 + k*IQR].  The reported `z_score`
    field carries the IQR multiple for downstream display.
    """
    if len(history) < min_history:
        return []

    df = sorted(history, key=lambda r: r["period"])
    values = np.array([float(r["value"]) for r in df])
    periods = [r["period"] for r in df]

    q1, q3 = np.percentile(values, [25, 75])
    iqr = q3 - q1
    if iqr == 0:
        return []

    lo = q1 - iqr_multiplier * iqr
    hi = q3 + iqr_multiplier * iqr
    median = float(np.median(values))

    out: list[dict[str, Any]] = []
    for i, p in enumerate(periods):
        if period_to_check is not None and p != period_to_check:
            continue
        v = float(values[i])
        if v < lo or v > hi:
            mult = (v - median) / (iqr / 1.349)   # ~ robust z
            out.append({
                "period":           p,
                "expected_value":   median,
                "actual_value":     v,
                "z_score":          float(mult),
                "detection_method": "iqr",
                "severity":         _severity_from_iqr_mult(mult),
            })
    return out


def detect_anomalies(
    history: list[dict[str, Any]],
    period_to_check: date | None = None,
    method: str = "both",
) -> list[dict[str, Any]]:
    """Run z-score, IQR, or both.  Returns a deduped list (period+method key)."""
    out: list[dict[str, Any]] = []
    if method in ("zscore", "both"):
        out.extend(detect_zscore_anomalies(history, period_to_check))
    if method in ("iqr", "both"):
        out.extend(detect_iqr_anomalies(history, period_to_check))
    return out
