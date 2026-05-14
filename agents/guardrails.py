"""
Guardrails — pre/post output validators for agent runs.

The 3 spec-required guardrails:

    DataSanityGuardrail              → on Data Ingestion Agent
    ForecastReasonablenessGuardrail  → on Forecasting Agent
    CommentaryGroundingGuardrail     → on Financial Commentary Agent

We define a minimal BaseGuardrail compatible with Agno's interface:
    .check(data)        sync
    .async_check(data)  async
    ._validate(data)    internal

If the installed Agno version provides BaseGuardrail, we subclass it; otherwise
we expose our own protocol so the agents file can be imported standalone (and
unit-tested without Agno present).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from agents.number_normalization import (
    extract_financial_numbers,
    is_close,
    normalize_financial_number,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Local BaseGuardrail (Agno-compatible signature)
# ─────────────────────────────────────────────────────────────
try:                                              # pragma: no cover
    from agno.guardrails import BaseGuardrail  # type: ignore
    _HAS_AGNO = True
except Exception:                                  # pragma: no cover
    _HAS_AGNO = False

    class BaseGuardrail:  # type: ignore[no-redef]
        """Local fallback when Agno isn't installed."""
        def check(self, data: Any) -> "GuardrailResult":  # noqa: D401
            raise NotImplementedError

        async def async_check(self, data: Any) -> "GuardrailResult":
            return self.check(data)


@dataclass
class GuardrailResult:
    passed: bool
    reason: str | None = None
    details: dict[str, Any] | None = None


# ─────────────────────────────────────────────────────────────
# 1) DataSanityGuardrail  — Ingestion
# ─────────────────────────────────────────────────────────────
class DataSanityGuardrail(BaseGuardrail):
    """
    Reject ingestion inputs that:
        - have non-positive revenue
        - have a future-dated period
    """
    name = "DataSanityGuardrail"

    def check(self, data: Any) -> GuardrailResult:
        return self._validate(data)

    async def async_check(self, data: Any) -> GuardrailResult:
        return self._validate(data)

    def _validate(self, data: Any) -> GuardrailResult:
        rows = data.get("rows") if isinstance(data, dict) else getattr(data, "rows", None)
        if not rows:
            return GuardrailResult(True)
        today = date.today()
        for r in rows:
            metric = r.get("metric_name") if isinstance(r, dict) else getattr(r, "metric_name", "")
            amount = r.get("amount")     if isinstance(r, dict) else getattr(r, "amount", 0)
            period = r.get("period")     if isinstance(r, dict) else getattr(r, "period", None)
            if metric == "revenue" and amount is not None and float(amount) <= 0:
                return GuardrailResult(False, f"Non-positive revenue: {amount}")
            if isinstance(period, date) and period > today:
                return GuardrailResult(False, f"Future-dated period: {period}")
        return GuardrailResult(True)


# ─────────────────────────────────────────────────────────────
# 2) ForecastReasonablenessGuardrail  — Forecasting
# ─────────────────────────────────────────────────────────────
class ForecastReasonablenessGuardrail(BaseGuardrail):
    """
    Reject forecasts whose first point deviates >50% from the trailing 3-month
    average.  Acts as a circuit-breaker against runaway model output.
    """
    name = "ForecastReasonablenessGuardrail"
    threshold = 0.50

    def check(self, data: Any) -> GuardrailResult:
        return self._validate(data)

    async def async_check(self, data: Any) -> GuardrailResult:
        return self._validate(data)

    def _validate(self, data: Any) -> GuardrailResult:
        if not isinstance(data, dict):
            return GuardrailResult(True)

        forecast = data.get("forecast") or []
        trailing_avg = data.get("trailing_3m_avg")
        if not forecast or trailing_avg is None or trailing_avg == 0:
            return GuardrailResult(True)

        first = forecast[0]
        point = first.get("point_forecast") if isinstance(first, dict) else getattr(first, "point_forecast", None)
        if point is None:
            return GuardrailResult(True)

        deviation = abs(point - trailing_avg) / abs(trailing_avg)
        if deviation > self.threshold:
            return GuardrailResult(
                False,
                f"Forecast {point:.0f} deviates {deviation*100:.1f}% from trailing avg "
                f"{trailing_avg:.0f} (threshold {self.threshold*100:.0f}%)",
            )
        return GuardrailResult(True)


# ─────────────────────────────────────────────────────────────
# 3) CommentaryGroundingGuardrail  — Commentary
# ─────────────────────────────────────────────────────────────
class CommentaryGroundingGuardrail(BaseGuardrail):
    """
    The CORRECTED grounding check.  We derive allowed numbers from the actual
    `analysis_data` context that was passed into the commentary agent, NOT from
    a separate `allowed_figures` key.

    Pulls the context from (in order):
        data["_analysis_context"]   ← preferred, structured
        data["analysis_data"]       ← fallback
    """
    name = "CommentaryGroundingGuardrail"
    min_abs_for_check = 10_000.0       # ignore tiny numbers (percentages, multipliers, etc.)
    tolerance = 0.05                   # 5% relative tolerance
    max_ungrounded = 3

    def check(self, data: Any) -> GuardrailResult:
        return self._validate(data)

    async def async_check(self, data: Any) -> GuardrailResult:
        return self._validate(data)

    def _validate(self, data: Any) -> GuardrailResult:
        if not isinstance(data, dict):
            return GuardrailResult(True)

        narrative = data.get("narrative", "") or ""
        figures_cited = data.get("figures_cited", []) or []
        analysis_context = (
            data.get("_analysis_context")
            or data.get("analysis_data")
            or {}
        )

        if not analysis_context:
            # Cannot ground without context — let the eval downstream catch it.
            return GuardrailResult(True)

        context_numbers = extract_financial_numbers(
            analysis_context, min_abs=self.min_abs_for_check
        )

        # Case A — narrative cites no figures, but contains many large numbers
        if not figures_cited:
            large_in_narrative = extract_financial_numbers(narrative, min_abs=self.min_abs_for_check)
            if len(large_in_narrative) > 5 and context_numbers:
                # Verify each large number traces to context
                ungrounded = [
                    n for n in large_in_narrative
                    if not any(is_close(n, c, self.tolerance) for c in context_numbers)
                ]
                if len(ungrounded) > self.max_ungrounded:
                    return GuardrailResult(
                        False,
                        f"{len(ungrounded)} large numbers in narrative not in analysis_data; "
                        f"sample={ungrounded[:3]}",
                    )
            return GuardrailResult(True)

        if not context_numbers:
            return GuardrailResult(True)

        # Case B — figures explicitly cited; verify each one
        ungrounded: list[str] = []
        for fig in figures_cited:
            raw = fig.get("raw_text") if isinstance(fig, dict) else str(fig)
            fig_val = (
                fig.get("normalized_value") if isinstance(fig, dict) else None
            )
            if fig_val is None:
                fig_val = normalize_financial_number(raw)
            if fig_val is None or abs(fig_val) < self.min_abs_for_check:
                continue
            if fig.get("is_derived") if isinstance(fig, dict) else False:
                continue                              # derived figures get a pass
            if not any(is_close(fig_val, c, self.tolerance) for c in context_numbers):
                ungrounded.append(str(raw))

        if len(ungrounded) > self.max_ungrounded:
            return GuardrailResult(
                False,
                f"{len(ungrounded)} cited figures not traceable to analysis data; "
                f"sample={ungrounded[:3]}",
            )
        return GuardrailResult(True)


# Convenience export
ALL_GUARDRAILS = [
    DataSanityGuardrail,
    ForecastReasonablenessGuardrail,
    CommentaryGroundingGuardrail,
]
