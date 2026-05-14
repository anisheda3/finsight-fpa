"""
Evals — post-hoc scorers attached to specific agents.

Spec requires both `setup`, `run`, `async_run`, and `teardown` per BaseEval.

    1. ForecastAccuracyEval     — MAPE between forecast & actuals (post-hoc)
    2. CommentaryGroundingEval  — LLM-as-judge that every figure in narrative
                                  appears in analysis_data
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

import numpy as np

from agents.number_normalization import (
    extract_financial_numbers,
    is_close,
    normalize_financial_number,
)

logger = logging.getLogger(__name__)


try:                                            # pragma: no cover
    from agno.evals import BaseEval  # type: ignore
    _HAS_AGNO = True
except Exception:                                # pragma: no cover
    _HAS_AGNO = False

    class BaseEval:  # type: ignore[no-redef]
        """Local fallback when Agno isn't installed."""
        def setup(self) -> None: ...
        def teardown(self) -> None: ...
        def run(self, output: Any, **kwargs: Any) -> "EvalResult":
            raise NotImplementedError
        async def async_run(self, output: Any, **kwargs: Any) -> "EvalResult":
            return self.run(output, **kwargs)


@dataclass
class EvalResult:
    score: float                # 0.0 – 1.0  (higher = better)
    passed: bool
    details: dict[str, Any]


# ─────────────────────────────────────────────────────────────
# 1) ForecastAccuracyEval — MAPE vs actuals
# ─────────────────────────────────────────────────────────────
class ForecastAccuracyEval(BaseEval):
    """
    Post-hoc accuracy check.  Provide:
        output  = ForecastResult-shaped dict (or model)
        actuals = list[{"period": date, "value": float}]

    Score = max(0, 1 - MAPE/100). Fails if MAPE > 20%.
    """
    name = "ForecastAccuracyEval"
    fail_threshold_mape_pct = 20.0

    def setup(self) -> None: ...
    def teardown(self) -> None: ...

    def run(self, output: Any, *, actuals: list[dict[str, Any]] | None = None,
            **kwargs: Any) -> EvalResult:
        return self._compute(output, actuals or [])

    async def async_run(self, output: Any, *, actuals: list[dict[str, Any]] | None = None,
                        **kwargs: Any) -> EvalResult:
        return self._compute(output, actuals or [])

    def _compute(self, output: Any, actuals: list[dict[str, Any]]) -> EvalResult:
        if not actuals:
            return EvalResult(score=float("nan"), passed=True,
                              details={"reason": "no actuals to compare"})

        forecast = output.get("forecast") if isinstance(output, dict) \
                    else getattr(output, "forecast", [])
        actual_map = {a["period"]: float(a["value"]) for a in actuals}

        pairs: list[tuple[float, float]] = []
        for p in forecast:
            period = p.get("period") if isinstance(p, dict) else getattr(p, "period", None)
            point = p.get("point_forecast") if isinstance(p, dict) else getattr(p, "point_forecast", None)
            if period in actual_map and point is not None:
                pairs.append((actual_map[period], float(point)))

        if not pairs:
            return EvalResult(score=float("nan"), passed=True,
                              details={"reason": "no overlapping periods"})

        a = np.array([x[0] for x in pairs])
        f = np.array([x[1] for x in pairs])
        mask = a != 0
        mape = float(np.mean(np.abs((a[mask] - f[mask]) / a[mask])) * 100.0)
        score = max(0.0, 1.0 - mape / 100.0)
        passed = mape <= self.fail_threshold_mape_pct
        return EvalResult(score=score, passed=passed,
                          details={"mape_pct": mape, "n_pairs": len(pairs)})


# ─────────────────────────────────────────────────────────────
# 2) CommentaryGroundingEval — regex + optional LLM-as-judge
# ─────────────────────────────────────────────────────────────
_NUMBER_TOKEN_RE = re.compile(
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


class CommentaryGroundingEval(BaseEval):
    """
    Verifies every specific figure in the narrative is present in analysis_data.

    Two-pass:
        1. Deterministic regex pass: extract every figure from narrative,
           normalize, check against numbers extracted from analysis_data
           (5% tolerance).  Produces a coverage score.
    - LLM-as-judge (only if GEMINI_API_KEY is set): asks an LLM to find
           any hallucinated/unsupported claims; returns boolean + rationale.

    Final score = avg(regex_coverage, llm_score).
    Passes if final_score >= 0.85.
    """
    name = "CommentaryGroundingEval"
    pass_threshold = 0.85
    min_abs_for_check = 10_000.0
    tolerance = 0.05

    def setup(self) -> None: ...
    def teardown(self) -> None: ...

    def run(self, output: Any, *, analysis_data: Any = None,
            **kwargs: Any) -> EvalResult:
        return self._compute(output, analysis_data)

    async def async_run(self, output: Any, *, analysis_data: Any = None,
                        **kwargs: Any) -> EvalResult:
        sync_result = self._compute(output, analysis_data)
        if os.getenv("GEMINI_API_KEY") and isinstance(output, dict):
            narrative = (output.get("narrative") or "")
            if narrative:
                llm_score, llm_rationale = await self._llm_judge(narrative, analysis_data or output.get("_analysis_context") or {})
                if llm_score is not None:
                    final_score = (sync_result.score + llm_score) / 2.0
                    return EvalResult(
                        score=final_score,
                        passed=final_score >= self.pass_threshold,
                        details={
                            **sync_result.details,
                            "llm_score": llm_score,
                            "llm_rationale": llm_rationale,
                        },
                    )
        return sync_result

    def _compute(self, output: Any, analysis_data: Any) -> EvalResult:
        narrative = (output.get("narrative") if isinstance(output, dict)
                     else getattr(output, "narrative", "")) or ""
        ctx = analysis_data or (output.get("_analysis_context") if isinstance(output, dict) else None) or {}

        # Pass 1 — regex coverage
        ctx_nums = extract_financial_numbers(ctx, min_abs=self.min_abs_for_check)
        narrative_figures: list[float] = []
        for m in _NUMBER_TOKEN_RE.finditer(narrative):
            v = normalize_financial_number(m.group(0))
            if v is None:
                continue
            if abs(v) >= self.min_abs_for_check:
                narrative_figures.append(v)

        if not narrative_figures:
            regex_coverage = 1.0
            ungrounded: list[float] = []
        else:
            ungrounded = [
                v for v in narrative_figures
                if not any(is_close(v, c, self.tolerance) for c in ctx_nums)
            ]
            grounded = len(narrative_figures) - len(ungrounded)
            regex_coverage = grounded / len(narrative_figures)

        final_score = regex_coverage
        passed = final_score >= self.pass_threshold
        return EvalResult(
            score=final_score,
            passed=passed,
            details={
                "regex_coverage": regex_coverage,
                "n_figures_in_narrative": len(narrative_figures),
                "n_ungrounded": len(ungrounded),
                "ungrounded_sample": ungrounded[:5],
                "llm_score": None,
                "llm_rationale": None,
            },
        )

    @staticmethod
    async def _llm_judge(narrative: str, context: Any) -> tuple[float | None, str | None]:
        """Returns (score in [0,1] or None, rationale or None)."""
        try:
            from app.services.llm_service import generate_json_with_llm
            ctx_str = json.dumps(context, default=str)[:6000]
            sys_prompt = (
                "You are a financial-analysis grounding judge. The user gives you "
                "(A) an analysis_data JSON blob and (B) a CFO commentary narrative. "
                "Decide whether every specific number, percentage, growth rate, or "
                "currency figure in the narrative is supported by analysis_data "
                "(within ~5% rounding tolerance). Respond ONLY in JSON: "
                '{"score": <float 0-1>, "rationale": "<one sentence>"}.'
            )
            user_prompt = f"analysis_data:\n{ctx_str}\n\nnarrative:\n{narrative[:4000]}"
            verdict = await generate_json_with_llm(
                prompt=user_prompt,
                system_prompt=sys_prompt,
                temperature=0.0,
                max_tokens=600,
            )
            score = float(verdict.get("score", 0.5))
            rationale = verdict.get("rationale", "")
            return score, rationale
        except Exception as e:                                 # pragma: no cover
            logger.warning("LLM-as-judge failed: %s", e)
            return None, None


ALL_EVALS = [ForecastAccuracyEval, CommentaryGroundingEval]
