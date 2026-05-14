"""
Financial number normalization.

Handles formats common in Indian + global FP&A reports:
    ₹12.4Cr        → 124_000_000
    12.4 crore     → 124_000_000
    INR 4.2 million → 4_200_000
    $1.5B          → 1_500_000_000
    350 bps        → 3.5      (in %)
    15.2%          → 15.2     (in %)
    2.3x           → 2.3      (multiplier)
    1,234,567      → 1_234_567

Used by CommentaryGroundingGuardrail and CommentaryGroundingEval.
"""
from __future__ import annotations

import re
from typing import Any

# Multipliers for unit suffixes
_UNIT_MULT: dict[str, float] = {
    "k": 1e3, "thousand": 1e3,
    "lakh": 1e5, "lac": 1e5,
    "m": 1e6, "mn": 1e6, "million": 1e6,
    "cr": 1e7, "crore": 1e7, "crores": 1e7,
    "b": 1e9, "bn": 1e9, "billion": 1e9,
    "t": 1e12, "tn": 1e12, "trillion": 1e12,
}

_NUM_RE = re.compile(
    r"""
    (?P<sign>[-+]?)\s*                    # optional sign
    (?:[₹$€£])?\s*                         # optional currency symbol
    (?:(?:INR|USD|EUR|GBP)\s*)?           # optional currency code
    (?P<num>\d{1,3}(?:,\d{2,3})*(?:\.\d+)?|\d+(?:\.\d+)?)
    \s*
    (?P<unit>thousand|trillion|billion|million|crores|crore|lakh|lac|bps|tn|mn|bn|cr|k|m|b|t|%|x)?
    """,
    re.IGNORECASE | re.VERBOSE,
)


def normalize_financial_number(text: str) -> float | None:
    """Parse a single financial figure to a float.  Returns None on no match."""
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None
    m = _NUM_RE.search(s)
    if not m:
        return None
    raw_num = m.group("num").replace(",", "")
    try:
        val = float(raw_num)
    except ValueError:
        return None
    if m.group("sign") == "-":
        val = -val
    unit = (m.group("unit") or "").lower()
    if unit == "bps":
        # 100 bps = 1% → return value in percentage points
        return val / 100.0
    if unit == "%":
        return val
    if unit == "x":
        return val
    if unit in _UNIT_MULT:
        return val * _UNIT_MULT[unit]
    return val


_FIGURE_FINDALL_RE = re.compile(
    r"""
    (?<![A-Za-z0-9_])
    [-+]?(?:[₹$€£]\s*)?(?:(?:INR|USD|EUR|GBP)\s*)?
    \d{1,3}(?:,\d{2,3})*(?:\.\d+)?
    \s*
    (?:thousand|trillion|billion|million|crores|crore|lakh|lac|bps|tn|mn|bn|cr|k|m|b|t|%|x)?
    (?![A-Za-z0-9_])
    """,
    re.IGNORECASE | re.VERBOSE,
)


def extract_financial_numbers(
    blob: Any,
    min_abs: float = 0.0,
) -> list[float]:
    """
    Extract every recognizable financial number from a string OR a nested
    dict/list (recursively).  Useful for harvesting all numbers from
    `analysis_data` to build the grounding allow-list.
    """
    seen: list[float] = []

    def _visit(x: Any) -> None:
        if x is None:
            return
        if isinstance(x, bool):
            return
        if isinstance(x, (int, float)):
            seen.append(float(x))
            return
        if isinstance(x, str):
            for m in _FIGURE_FINDALL_RE.finditer(x):
                v = normalize_financial_number(m.group(0))
                if v is not None:
                    seen.append(v)
            return
        if isinstance(x, dict):
            for k, v in x.items():
                _visit(k)
                _visit(v)
            return
        if isinstance(x, (list, tuple, set)):
            for v in x:
                _visit(v)
            return
        # Fallback: stringify
        _visit(str(x))

    _visit(blob)
    return [v for v in seen if abs(v) >= min_abs]


def is_close(a: float, b: float, tolerance: float = 0.05) -> bool:
    """Relative tolerance for grounding comparisons (default 5%)."""
    if a == b:
        return True
    if a == 0 or b == 0:
        return abs(a - b) < 1e-6
    return abs(a - b) / max(abs(a), abs(b)) <= tolerance
