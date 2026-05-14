"""HITL signal mechanics — verifies the saga's signal handler updates state.

Does not need a Temporal server: instantiates the workflow class directly
and calls its signal method, then asserts the internal state.
"""
from __future__ import annotations

import pytest

pytest.importorskip("temporalio")
from temporal.month_end_saga import MonthEndAnalysisSaga


def test_hitl_signal_records_decision_and_clears_pending():
    saga = MonthEndAnalysisSaga()
    saga._pending_flag_ids = {"variance:revenue:2024-09-01",
                              "anomaly:rd:2024-09-01"}

    saga.hitl_decision("variance:revenue:2024-09-01", "APPROVED",
                       reviewer_id="cfo@example.com", notes="ok")
    assert "variance:revenue:2024-09-01" in saga._hitl_decisions
    assert saga._hitl_decisions["variance:revenue:2024-09-01"]["decision"] == "APPROVED"
    assert "variance:revenue:2024-09-01" not in saga._pending_flag_ids

    saga.hitl_decision("anomaly:rd:2024-09-01", "REJECTED")
    assert len(saga._pending_flag_ids) == 0  # all resolved


def test_abort_signal_sets_flag():
    saga = MonthEndAnalysisSaga()
    assert saga._aborted is False
    saga.abort("operator cancelled")
    assert saga._aborted is True
