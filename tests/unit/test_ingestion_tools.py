"""Unit tests for ingestion: parse / validate / normalize / hash."""
from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest

from agents.tools.ingestion_tools import (
    compute_source_hash,
    normalize_metric_name,
    parse_actuals_csv,
    parse_and_validate_actuals,
    validate_and_normalize_rows,
)


def test_metric_normalization():
    assert normalize_metric_name("Revenue from Operations") == "revenue"
    assert normalize_metric_name("R&D") == "rd"
    assert normalize_metric_name("Sales & Marketing") == "sm"
    assert normalize_metric_name("EBITDA") == "ebitda"
    assert normalize_metric_name("Custom Bucket") == "custom_bucket"


def test_csv_parse_and_validate():
    csv_text = (
        "period,department,metric_name,amount\n"
        "2024-09-01,sales,Revenue from Operations,1500000\n"
        "2024-09-01,sales,COGS,600000\n"
    )
    res = parse_and_validate_actuals(csv_text, uuid4(), file_format="csv")
    assert res["accepted"] == 2
    assert res["rejected"] == 0
    assert res["rows"][0].metric_name == "revenue"
    assert res["period_min"] == date(2024, 9, 1)


def test_csv_missing_columns_rejected():
    csv_text = "period,amount\n2024-09-01,1000\n"
    with pytest.raises(ValueError, match="missing required columns"):
        parse_actuals_csv(csv_text)


def test_negative_revenue_rejected():
    cid = uuid4()
    raw = [{"period": "2024-09-01", "metric_name": "revenue", "amount": "-100"}]
    rows, errors = validate_and_normalize_rows(raw, cid)
    assert rows == []
    assert len(errors) == 1
    assert "negative revenue" in errors[0]


def test_future_period_rejected():
    cid = uuid4()
    raw = [{"period": "2099-01-01", "metric_name": "revenue", "amount": "100"}]
    rows, errors = validate_and_normalize_rows(raw, cid)
    assert rows == []
    assert "future" in errors[0].lower()


def test_source_hash_deterministic():
    h1 = compute_source_hash("hello")
    h2 = compute_source_hash("hello")
    h3 = compute_source_hash("world")
    assert h1 == h2 != h3
    assert len(h1) == 64  # sha256
