"""
Pydantic schemas for FinSight FP&A AI.

Every agent's `output_schema` is one of these models.
All financial I/O is typed; no untyped dicts cross agent boundaries.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


# ─────────────────────────────────────────────────────────────
# Shared primitives
# ─────────────────────────────────────────────────────────────
class TimeSeriesPoint(BaseModel):
    period: date = Field(..., description="First day of month")
    value: float = Field(..., description="Metric value for the period")


# ─────────────────────────────────────────────────────────────
# 1) Ingestion
# ─────────────────────────────────────────────────────────────
class FinancialActualRow(BaseModel):
    company_id: UUID
    period: date
    department: str | None = None
    metric_name: str = Field(..., description="Canonical metric (revenue, cogs, ...)")
    amount: float
    currency: str = "INR"
    source: str = "ERP"

    @field_validator("period")
    @classmethod
    def _no_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError(f"period {v} is in the future")
        return v

    @field_validator("metric_name")
    @classmethod
    def _canonical(cls, v: str) -> str:
        return v.strip().lower()


class FinancialActualsInput(BaseModel):
    company_id: UUID
    rows: list[FinancialActualRow]
    source_file_name: str | None = None
    source_file_hash: str | None = None


class IngestionResult(BaseModel):
    company_id: UUID
    accepted_rows: int
    rejected_rows: int
    duplicate_rows: int
    errors: list[str] = Field(default_factory=list)
    period_min: date | None = None
    period_max: date | None = None
    source_file_hash: str | None = None
    ingested_at: datetime = Field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────────────────────
# 2) Forecasting
# ─────────────────────────────────────────────────────────────
class ForecastPoint(BaseModel):
    period: date
    point_forecast: float
    lower_bound_80: float
    upper_bound_80: float
    lower_bound_95: float
    upper_bound_95: float


class ForecastResult(BaseModel):
    company_id: UUID
    metric_name: str
    forecast: list[ForecastPoint]
    model_name: Literal["prophet", "sarima", "linear"]
    model_version: str = "1.0.0"
    model_params: dict[str, Any] = Field(default_factory=dict)
    in_sample_mape: float | None = Field(
        None, description="MAPE on holdout (last N months)"
    )
    holdout_months: int = 3
    horizon_months: int = 6
    training_start_period: date | None = None
    training_end_period: date | None = None
    run_id: str
    selected_reason: str | None = None
    fallback_reason: str | None = None
    prior_model_used: str | None = None
    prior_mape: float | None = None
    explanation: str | None = Field(
        None, description="LLM-written interpretation of the forecast"
    )

    @model_validator(mode="after")
    def _bounds_ordered(self) -> "ForecastResult":
        for p in self.forecast:
            if not (p.lower_bound_95 <= p.lower_bound_80 <= p.point_forecast
                    <= p.upper_bound_80 <= p.upper_bound_95):
                raise ValueError(
                    f"forecast bounds out of order at {p.period}: "
                    f"95L={p.lower_bound_95} 80L={p.lower_bound_80} "
                    f"pt={p.point_forecast} 80U={p.upper_bound_80} 95U={p.upper_bound_95}"
                )
        return self


# ─────────────────────────────────────────────────────────────
# 3) Variance analysis
# ─────────────────────────────────────────────────────────────
Materiality = Literal["IMMATERIAL", "NOTABLE", "MATERIAL", "CRITICAL"]


class VarianceRecord(BaseModel):
    company_id: UUID
    period: date
    department: str | None = None
    metric_name: str
    actual_amount: float
    budget_amount: float
    variance_amount: float
    variance_pct: float
    is_favorable: bool
    materiality: Materiality
    waterfall_rank: int | None = None
    actual_id: UUID | None = None
    budget_id: UUID | None = None

    @model_validator(mode="after")
    def _check_variance_math(self) -> "VarianceRecord":
        expected = self.actual_amount - self.budget_amount
        if abs(expected - self.variance_amount) > 1e-6:
            raise ValueError(
                f"variance_amount mismatch: got {self.variance_amount}, expected {expected}"
            )
        if self.budget_amount != 0:
            expected_pct = (expected / abs(self.budget_amount)) * 100.0
            if abs(expected_pct - self.variance_pct) > 1e-4:
                raise ValueError(
                    f"variance_pct mismatch: got {self.variance_pct}, expected {expected_pct}"
                )
        return self


class WaterfallItem(BaseModel):
    metric_name: str
    contribution: float = Field(..., description="Signed Δ to EBITDA (₹)")
    rank: int


class VarianceReport(BaseModel):
    company_id: UUID
    period: date
    records: list[VarianceRecord]
    waterfall: list[WaterfallItem]
    total_ebitda_actual: float | None = None
    total_ebitda_budget: float | None = None
    total_ebitda_variance: float | None = None
    flagged_for_hitl: list[UUID] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# 4) Anomaly
# ─────────────────────────────────────────────────────────────
Severity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


class AnomalyFlag(BaseModel):
    company_id: UUID
    period: date
    metric_name: str
    expected_value: float
    actual_value: float
    z_score: float
    detection_method: Literal["zscore", "iqr"]
    severity: Severity
    actual_id: UUID | None = None


# ─────────────────────────────────────────────────────────────
# 5) Scenario
# ─────────────────────────────────────────────────────────────
ScenarioType = Literal["BASE", "BULL", "BEAR"]


class ScenarioAssumptions(BaseModel):
    revenue_growth_qoq: float = Field(..., description="Quarter-over-quarter revenue growth %")
    cogs_ratio: float = Field(..., description="COGS as % of revenue")
    rd_ratio: float = Field(..., description="R&D as % of revenue")
    sm_ratio: float = Field(..., description="S&M as % of revenue")
    ga_ratio: float = Field(..., description="G&A as % of revenue")
    macro_adjustment_pct: float = 0.0


class ScenarioQuarterlyPL(BaseModel):
    quarter_label: str
    revenue: float
    cogs: float
    gross_profit: float
    rd: float
    sm: float
    ga: float
    ebitda: float
    ebitda_margin: float


class ScenarioPlan(BaseModel):
    company_id: UUID
    scenario_type: ScenarioType
    label: str
    assumptions: ScenarioAssumptions
    quarters: list[ScenarioQuarterlyPL]
    projection_start: date
    projection_end: date
    projected_revenue: float
    projected_gross_profit: float
    projected_ebitda: float
    based_on_forecast_run_id: str | None = None


# ─────────────────────────────────────────────────────────────
# 6) Commentary  (with rich citation lineage)
# ─────────────────────────────────────────────────────────────
class CitedFigure(BaseModel):
    raw_text: str = Field(..., description="As written in narrative, e.g. '₹12.4Cr'")
    normalized_value: float | None = None
    source_path: str | None = Field(
        None, description="Where in analysis_data the figure came from, e.g. 'variance_records[0].actual'"
    )
    source_metric: str | None = None
    source_period: date | None = None
    is_derived: bool = False
    derivation_note: str | None = None


class FinancialCommentary(BaseModel):
    company_id: UUID
    period: date
    commentary_type: Literal["MONTHLY", "QUARTERLY", "ANNUAL", "SCENARIO"] = "MONTHLY"
    narrative: str = Field(..., min_length=100, max_length=4000)
    key_insights: list[str] = Field(..., min_length=3, max_length=8)
    figures_cited: list[CitedFigure] = Field(default_factory=list)
    grounding_score: float | None = None
    model_version: str = "1.0.0"


# ─────────────────────────────────────────────────────────────
# 7) Notification + 8) Audit
# ─────────────────────────────────────────────────────────────
class NotificationResult(BaseModel):
    channel: Literal["slack", "email", "redis", "websocket"]
    target: str
    message_ts: str | None = None
    delivery_status: Literal["SENT", "FAILED", "PENDING"]
    error: str | None = None


class AuditEntry(BaseModel):
    workflow_run_id: str
    agent_name: str
    action: str
    input_summary: str | None = None
    output_summary: str | None = None
    model_name: str | None = None
    eval_score: float | None = None
    duration_ms: int | None = None


# ─────────────────────────────────────────────────────────────
# Team-level outputs
# ─────────────────────────────────────────────────────────────
class MonthEndAnalysisResult(BaseModel):
    company_id: UUID
    period: date
    ingestion: IngestionResult
    forecasts: list[ForecastResult]
    variance_report: VarianceReport
    anomalies: list[AnomalyFlag]
    period_health: Literal["STRONG", "ON_TRACK", "AT_RISK", "CRITICAL_MISS"]


class InsightsTeamResult(BaseModel):
    company_id: UUID
    period: date
    scenarios: list[ScenarioPlan]
    commentary: FinancialCommentary
    notifications: list[NotificationResult]
    audit_entries: list[AuditEntry]
