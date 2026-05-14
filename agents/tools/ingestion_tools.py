"""
Ingestion tools — parse / validate / normalize / hash actuals files.

Responsibilities:
    - parse CSV or JSON
    - validate via Pydantic (no future periods, no negative revenue, etc.)
    - normalize metric names to canonical schema
    - compute deterministic source-file hash (lineage)
    - return rows ready for idempotent upsert via the DB layer
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import re
from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from agents.schemas import FinancialActualRow

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Metric-name normalization
# ─────────────────────────────────────────────────────────────
_METRIC_ALIASES: dict[str, str] = {
    # revenue
    "revenue": "revenue", "revenue from ops": "revenue",
    "revenue from operations": "revenue", "total revenue": "revenue",
    "net revenue": "revenue", "sales": "revenue", "net sales": "revenue",
    # cogs
    "cogs": "cogs", "cost of goods sold": "cogs", "cost of revenue": "cogs",
    "cost of sales": "cogs",
    # gross profit
    "gross profit": "gross_profit", "gp": "gross_profit",
    # opex
    "rd": "rd", "r&d": "rd", "research and development": "rd",
    "research & development": "rd",
    "sm": "sm", "s&m": "sm", "sales and marketing": "sm",
    "sales & marketing": "sm", "marketing": "sm",
    "ga": "ga", "g&a": "ga", "general and administrative": "ga",
    "general & administrative": "ga", "g and a": "ga",
    # ebitda
    "ebitda": "ebitda",
}


def normalize_metric_name(raw: str) -> str:
    """Map free-text metric labels to the canonical schema.  Falls back to snake_case."""
    if raw is None:
        return ""
    key = raw.strip().lower()
    if key in _METRIC_ALIASES:
        return _METRIC_ALIASES[key]
    # default: snake_case
    return re.sub(r"[^a-z0-9]+", "_", key).strip("_")


# ─────────────────────────────────────────────────────────────
# Parsing
# ─────────────────────────────────────────────────────────────
_REQUIRED_COLUMNS = {"period", "metric_name", "amount"}


def _parse_period(raw: str) -> date:
    raw = (raw or "").strip()
    for fmt in ("%Y-%m-%d", "%Y-%m", "%d-%m-%Y", "%d/%m/%Y", "%m/%Y"):
        try:
            d = datetime.strptime(raw, fmt).date()
            # Snap to first of month
            return date(d.year, d.month, 1)
        except ValueError:
            continue
    raise ValueError(f"unrecognized period format: {raw!r}")


def parse_actuals_csv(content: str | bytes) -> list[dict[str, Any]]:
    """Parse a CSV string/bytes into a list of raw row dicts."""
    if isinstance(content, bytes):
        content = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise ValueError("CSV has no header row")
    cols = {c.strip().lower() for c in reader.fieldnames}
    missing = _REQUIRED_COLUMNS - cols
    if missing:
        raise ValueError(f"CSV missing required columns: {sorted(missing)}")

    rows: list[dict[str, Any]] = []
    for raw in reader:
        # case-insensitive key access
        norm = {k.strip().lower(): (v.strip() if isinstance(v, str) else v) for k, v in raw.items()}
        rows.append(norm)
    return rows


def parse_actuals_json(content: str | bytes) -> list[dict[str, Any]]:
    if isinstance(content, bytes):
        content = content.decode("utf-8")
    data = json.loads(content)
    if isinstance(data, dict) and "rows" in data:
        data = data["rows"]
    if not isinstance(data, list):
        raise ValueError("JSON must be a list of rows or {'rows': [...]}")
    return data


# ─────────────────────────────────────────────────────────────
# Validation + normalization
# ─────────────────────────────────────────────────────────────
def validate_and_normalize_rows(
    raw_rows: list[dict[str, Any]],
    company_id: UUID,
) -> tuple[list[FinancialActualRow], list[str]]:
    """
    Convert raw row dicts to FinancialActualRow models.
    Returns (validated_rows, error_messages).
    """
    out: list[FinancialActualRow] = []
    errors: list[str] = []

    for i, r in enumerate(raw_rows, start=1):
        try:
            metric = normalize_metric_name(str(r.get("metric_name", "")))
            if not metric:
                raise ValueError("missing or empty metric_name")
            try:
                period = _parse_period(str(r.get("period", "")))
            except ValueError as e:
                raise ValueError(f"period: {e}")

            amount_raw = r.get("amount")
            if amount_raw in (None, ""):
                raise ValueError("missing amount")
            try:
                amount = float(amount_raw)
            except (TypeError, ValueError):
                raise ValueError(f"amount not numeric: {amount_raw!r}")

            # Business rule: revenue must not be negative
            if metric == "revenue" and amount < 0:
                raise ValueError(f"negative revenue not allowed: {amount}")

            row = FinancialActualRow(
                company_id=company_id,
                period=period,
                department=(r.get("department") or None),
                metric_name=metric,
                amount=amount,
                currency=(r.get("currency") or "INR"),
                source=(r.get("source") or "ERP"),
            )
            out.append(row)
        except (ValidationError, ValueError) as e:
            errors.append(f"row {i}: {e}")

    return out, errors


# ─────────────────────────────────────────────────────────────
# Source hash (lineage)
# ─────────────────────────────────────────────────────────────
def compute_source_hash(content: str | bytes) -> str:
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


# ─────────────────────────────────────────────────────────────
# Public tool entrypoint
# ─────────────────────────────────────────────────────────────
def parse_and_validate_actuals(
    content: str | bytes,
    company_id: UUID,
    file_format: str = "csv",
) -> dict[str, Any]:
    """
    Returns dict with keys:
        rows (list[FinancialActualRow]),
        errors (list[str]),
        source_file_hash,
        period_min, period_max, accepted, rejected
    """
    if file_format.lower() == "csv":
        raw = parse_actuals_csv(content)
    elif file_format.lower() == "json":
        raw = parse_actuals_json(content)
    else:
        raise ValueError(f"unsupported file_format: {file_format}")

    valid, errors = validate_and_normalize_rows(raw, company_id)
    return {
        "rows": valid,
        "errors": errors,
        "source_file_hash": compute_source_hash(content),
        "period_min": min((r.period for r in valid), default=None),
        "period_max": max((r.period for r in valid), default=None),
        "accepted": len(valid),
        "rejected": len(errors),
    }
