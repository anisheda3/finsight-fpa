"""Unit tests for financial number normalization."""
from __future__ import annotations

import pytest

from agents.number_normalization import (
    extract_financial_numbers,
    is_close,
    normalize_financial_number,
)


@pytest.mark.parametrize("text,expected", [
    ("₹12.4Cr",        124_000_000.0),
    ("12.4 crore",     124_000_000.0),
    ("INR 4.2 million", 4_200_000.0),
    ("$1.5B",          1_500_000_000.0),
    ("350 bps",        3.5),
    ("15.2%",          15.2),
    ("2.3x",           2.3),
    ("1,234,567",      1_234_567.0),
    ("-₹50 lakh",      -5_000_000.0),
])
def test_normalize_basic_formats(text, expected):
    assert normalize_financial_number(text) == pytest.approx(expected)


def test_normalize_returns_none_on_garbage():
    assert normalize_financial_number("hello world") is None
    assert normalize_financial_number("") is None
    assert normalize_financial_number(None) is None


def test_extract_from_narrative():
    text = (
        "Revenue grew to ₹15.2Cr (up 18% YoY), while EBITDA margin expanded "
        "by 350 bps to 22.4%. Cost of goods sold was INR 6.5 million."
    )
    nums = extract_financial_numbers(text)
    # Should capture: 15.2Cr, 18%, 350bps, 22.4%, 6.5M
    assert any(is_close(n, 152_000_000) for n in nums)
    assert any(is_close(n, 18.0) for n in nums)
    assert any(is_close(n, 3.5) for n in nums)
    assert any(is_close(n, 22.4) for n in nums)
    assert any(is_close(n, 6_500_000) for n in nums)


def test_extract_from_nested_dict():
    blob = {
        "variance_records": [
            {"actual_amount": 1_500_000.0, "budget_amount": 1_000_000},
        ],
        "narrative_snippet": "We hit ₹1.5Cr in revenue this month.",
    }
    nums = extract_financial_numbers(blob, min_abs=10_000)
    assert any(is_close(n, 1_500_000) for n in nums)
    assert any(is_close(n, 1_000_000) for n in nums)
    assert any(is_close(n, 15_000_000) for n in nums)  # ₹1.5Cr from the string


def test_is_close_within_tolerance():
    assert is_close(100.0, 105.0, tolerance=0.05)
    assert not is_close(100.0, 110.0, tolerance=0.05)
    assert is_close(0.0, 0.0)
