"""Unit tests for anomaly detection."""
from __future__ import annotations

from datetime import date

from agents.tools.anomaly_tools import (
    detect_anomalies,
    detect_iqr_anomalies,
    detect_zscore_anomalies,
)


def _series(values, start=date(2023, 1, 1)):
    out = []
    cur = start
    for v in values:
        out.append({"period": cur, "value": float(v)})
        cur = date(cur.year + (1 if cur.month == 12 else 0),
                   1 if cur.month == 12 else cur.month + 1, 1)
    return out


def test_zscore_flags_clear_outlier():
    # 11 stable months around 100, then a spike to 500
    history = _series([100, 102, 98, 101, 99, 100, 103, 97, 100, 102, 99, 500])
    flags = detect_zscore_anomalies(history)
    assert len(flags) == 1
    assert flags[0]["actual_value"] == 500.0
    assert flags[0]["severity"] in ("HIGH", "CRITICAL")


def test_zscore_no_flag_on_stable_series():
    history = _series([100, 100.5, 99.5, 100, 100.3, 99.7, 100, 100.4, 99.6, 100])
    flags = detect_zscore_anomalies(history)
    assert flags == []


def test_iqr_flags_outlier():
    history = _series([100, 102, 98, 101, 99, 100, 103, 97, 100, 102, 99, 500])
    flags = detect_iqr_anomalies(history)
    assert any(f["actual_value"] == 500.0 for f in flags)


def test_period_filter():
    history = _series([100, 200, 100, 100, 100, 100, 100, 100, 100, 100])
    target = history[1]["period"]   # the 200 spike
    flags = detect_zscore_anomalies(history, period_to_check=target)
    assert len(flags) == 1
    assert flags[0]["period"] == target


def test_min_history_guard():
    history = _series([100, 200])  # too short
    assert detect_zscore_anomalies(history) == []
    assert detect_iqr_anomalies(history) == []


def test_detect_anomalies_both_methods():
    history = _series([100, 102, 98, 101, 99, 100, 103, 97, 100, 102, 99, 500])
    flags = detect_anomalies(history, method="both")
    methods = {f["detection_method"] for f in flags}
    assert methods == {"zscore", "iqr"}
