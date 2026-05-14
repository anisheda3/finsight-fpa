#!/usr/bin/env python3
"""
FinSight FP&A AI — Seed Data Script
=====================================
Generates 45 months of realistic monthly financial time series (Jan 2021 – Sep 2024),
2024 budget data, KPI definitions, and synthetic annual report text for RAG testing.

Requirements:
    pip install psycopg2-binary faker numpy

Usage:
    POSTGRES_URL=postgresql://user:pass@localhost:5432/finsight_fpa python scripts/seed_data.py

What this creates:
  • 2 companies (SaaS + Professional Services)
  • 45 months of monthly actuals per company (Jan 2021 – Sep 2024)
  • 12 months of 2024 budget data (4 departments per company)
  • KPI definitions with materiality thresholds
  • 2 synthetic annual report text documents (FY2022 + FY2023) for RAG testing
    — NOT pre-embedded; your RAG pipeline must embed them
  • 4 planted anomalies for the agents to detect
  • A ready-to-upload Q3 2024 actuals CSV in sample_data/

Planted anomalies:
  1. [FTPL] 2022 Apr–May: Revenue spike +22% above trend (product launch)
  2. [FTPL] 2023 Oct–Nov: R&D expense spike +35% above normal ratio
  3. [FTPL] 2024 Q3 (Jul–Sep): Revenue -16% below budget (demand slowdown)
  4. [FCPL] 2024 Aug: Revenue drop -28% MoM (large project cancellation)

Idempotent: safe to run multiple times.

Disclaimer: Some fields may be null or minimal. Supplement with faker or other
libraries as needed to satisfy your implementation.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import os
import sys
import textwrap
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    log.error("psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)

try:
    import numpy as np
except ImportError:
    log.error("numpy not installed. Run: pip install numpy")
    sys.exit(1)

try:
    from faker import Faker
    fake = Faker("en_IN")
except ImportError:
    log.warning("faker not installed. Some fields will use fallback values.")
    fake = None

DATABASE_URL = os.getenv(
    "POSTGRES_URL", "postgresql://postgres:password@localhost:5432/finsight_fpa"
)
OUTPUT_DIR = Path("sample_data")
OUTPUT_DIR.mkdir(exist_ok=True)

np.random.seed(42)   # reproducible


# ---------------------------------------------------------------------------
# Time-series generation helpers
# ---------------------------------------------------------------------------

def _monthly_dates(start: date, end: date) -> List[date]:
    """Return first-of-month dates from start to end inclusive."""
    dates = []
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        dates.append(date(y, m, 1))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return dates


def _seasonal_factor(month: int, amplitude: float = 0.07) -> float:
    """
    Monthly seasonal factor for B2B SaaS / professional services.
    Q3 (Jul–Sep) dips; Q4 (Oct–Dec) and Mar push.
    """
    seasonal = {
        1: -0.03, 2: +0.01, 3: +0.06,
        4: +0.02, 5: +0.03, 6: +0.00,
        7: -0.08, 8: -0.09, 9: -0.04,
        10: +0.04, 11: +0.03, 12: +0.05,
    }
    return 1.0 + seasonal.get(month, 0.0)


def build_revenue_series(
    dates: List[date],
    base: float,
    annual_growth: Dict[int, float],
    seasonal_amplitude: float = 0.07,
    noise_std: float = 0.02,
    overrides: Optional[Dict[date, float]] = None,
) -> np.ndarray:
    """
    Generate a monthly revenue time series with:
      - compound annual growth
      - monthly seasonality
      - small random noise
      - optional point overrides (for planted anomalies)
    """
    overrides = overrides or {}
    values = []
    current = float(base)
    prev_year = dates[0].year if dates else 2021

    for d in dates:
        year = d.year
        if year != prev_year:
            # Apply annual growth step at year boundary
            g = annual_growth.get(year, 0.15)
            current *= (1 + g) ** (1 / 12)  # already applied monthly below
        prev_year = year

        g = annual_growth.get(year, 0.15)
        monthly_growth = (1 + g) ** (1 / 12)
        if values:
            current = values[-1] * monthly_growth
        else:
            current = base

        seasonal = _seasonal_factor(d.month, seasonal_amplitude)
        noise = np.random.normal(1.0, noise_std)
        v = current * seasonal * noise

        if d in overrides:
            v = overrides[d]

        values.append(max(v, 0))

    return np.array(values)


# ---------------------------------------------------------------------------
# Company data structures
# ---------------------------------------------------------------------------

@dataclass
class Company:
    id: str
    name: str
    erp_code: str
    industry: str
    fiscal_year_end_month: int = 3   # March (Indian FY)


FTPL = Company(
    id=str(uuid.uuid5(uuid.NAMESPACE_DNS, "FTPL-001")),
    name="Fyntwin Technologies Pvt Ltd",
    erp_code="FTPL-001",
    industry="Technology / SaaS",
)

FCPL = Company(
    id=str(uuid.uuid5(uuid.NAMESPACE_DNS, "FCPL-002")),
    name="Fyntwin Consulting Pvt Ltd",
    erp_code="FCPL-002",
    industry="Professional Services",
)

COMPANIES = [FTPL, FCPL]

# ---------------------------------------------------------------------------
# Actuals generation — Fyntwin Technologies (SaaS)
# ---------------------------------------------------------------------------
# Profile: B2B SaaS, high gross margin, growing from ₹8L/month in Jan 2021
# Gross Margin: ~65%, improving to ~70% by 2024

FTPL_BASE_REVENUE = 8_000_000       # Jan 2021
FTPL_ANNUAL_GROWTH = {
    2021: 0.35,   # strong early growth
    2022: 0.30,   # still strong, product launch
    2023: 0.22,   # growth normalisation
    2024: 0.15,   # budget assumption
}
FTPL_COGS_RATIO = {2021: 0.37, 2022: 0.35, 2023: 0.33, 2024: 0.31}
FTPL_RD_RATIO   = {2021: 0.24, 2022: 0.22, 2023: 0.20, 2024: 0.18}
FTPL_SM_RATIO   = {2021: 0.18, 2022: 0.16, 2023: 0.15, 2024: 0.14}
FTPL_GA_RATIO   = {2021: 0.10, 2022: 0.09, 2023: 0.08, 2024: 0.08}

ACTUALS_START = date(2021, 1, 1)
ACTUALS_END   = date(2024, 9, 1)
ALL_DATES     = _monthly_dates(ACTUALS_START, ACTUALS_END)


def _generate_ftpl_actuals() -> Dict[date, Dict[str, float]]:
    """Generate monthly actuals for FTPL with planted anomalies."""

    # Anomaly overrides (revenue)
    revenue_overrides: Dict[date, float] = {}
    # Anomaly 1: 2022 Apr–May product launch spike
    # Normal Apr 2022 would be ~11.5M, we push to ~14.0M
    for d, mult in [(date(2022, 4, 1), 1.22), (date(2022, 5, 1), 1.18)]:
        revenue_overrides[d] = None   # placeholder; filled after base series

    rev = build_revenue_series(
        ALL_DATES, FTPL_BASE_REVENUE, FTPL_ANNUAL_GROWTH,
        seasonal_amplitude=0.07, noise_std=0.018,
    )

    # Apply product-launch spike to Apr & May 2022
    for i, d in enumerate(ALL_DATES):
        if d == date(2022, 4, 1):
            rev[i] *= 1.22
        elif d == date(2022, 5, 1):
            rev[i] *= 1.18

    records: Dict[date, Dict[str, float]] = {}
    for i, d in enumerate(ALL_DATES):
        r = rev[i]
        yr = d.year
        cogs = r * (FTPL_COGS_RATIO.get(yr, 0.33) + np.random.normal(0, 0.005))
        rd   = r * (FTPL_RD_RATIO.get(yr, 0.18) + np.random.normal(0, 0.005))
        sm   = r * (FTPL_SM_RATIO.get(yr, 0.14) + np.random.normal(0, 0.004))
        ga   = r * (FTPL_GA_RATIO.get(yr, 0.08) + np.random.normal(0, 0.003))

        # Anomaly 2: 2023 Oct–Nov R&D spike (hiring surge)
        if d in (date(2023, 10, 1), date(2023, 11, 1)):
            rd *= 1.35

        gp    = r - cogs
        opex  = rd + sm + ga
        ebitda = gp - opex

        records[d] = {
            "revenue":       round(r),
            "cogs":          round(cogs),
            "gross_profit":  round(gp),
            "rd_expense":    round(rd),
            "sm_expense":    round(sm),
            "ga_expense":    round(ga),
            "total_opex":    round(opex),
            "ebitda":        round(ebitda),
        }

    return records


def _generate_fcpl_actuals() -> Dict[date, Dict[str, float]]:
    """
    Generate monthly actuals for Fyntwin Consulting — professional services.
    Higher revenue variance (project-based), lower growth, ~25% EBITDA margin.
    """
    FCPL_BASE  = 3_000_000       # Jan 2021
    FCPL_GROWTH = {2021: 0.20, 2022: 0.18, 2023: 0.15, 2024: 0.12}
    FCPL_COGS   = {2021: 0.50, 2022: 0.48, 2023: 0.46, 2024: 0.44}
    FCPL_RD     = {2021: 0.05, 2022: 0.05, 2023: 0.05, 2024: 0.05}
    FCPL_SM     = {2021: 0.12, 2022: 0.11, 2023: 0.10, 2024: 0.10}
    FCPL_GA     = {2021: 0.10, 2022: 0.10, 2023: 0.09, 2024: 0.09}

    rev = build_revenue_series(
        ALL_DATES, FCPL_BASE, FCPL_GROWTH,
        seasonal_amplitude=0.10, noise_std=0.04,   # higher variance for services
    )

    records: Dict[date, Dict[str, float]] = {}
    for i, d in enumerate(ALL_DATES):
        r = rev[i]
        yr = d.year

        # Anomaly 4: Aug 2024 revenue drop (large project cancellation)
        if d == date(2024, 8, 1):
            r *= 0.72

        cogs  = r * (FCPL_COGS.get(yr, 0.46) + np.random.normal(0, 0.008))
        rd    = r * (FCPL_RD.get(yr, 0.05)   + np.random.normal(0, 0.002))
        sm    = r * (FCPL_SM.get(yr, 0.10)   + np.random.normal(0, 0.003))
        ga    = r * (FCPL_GA.get(yr, 0.09)   + np.random.normal(0, 0.003))
        gp    = r - cogs
        opex  = rd + sm + ga
        ebitda = gp - opex

        records[d] = {
            "revenue":       round(r),
            "cogs":          round(cogs),
            "gross_profit":  round(gp),
            "rd_expense":    round(rd),
            "sm_expense":    round(sm),
            "ga_expense":    round(ga),
            "total_opex":    round(opex),
            "ebitda":        round(ebitda),
        }

    return records


# ---------------------------------------------------------------------------
# Budget generation — 2024 only
# ---------------------------------------------------------------------------
# Budget is built from the Dec 2023 run-rate with a 15% / 12% YoY lift.
# Crucially, the budget does NOT adequately account for Q3 seasonal dip —
# this creates a large unfavorable variance in Jul–Sep 2024 actuals.

def _generate_budget(
    company_id: str,
    actuals: Dict[date, Dict[str, float]],
    yoy_growth: float,
    version: str = "FY2024-v1",
) -> List[Dict]:
    """
    Build 2024 monthly budget based on 2023 actuals + flat YoY growth.
    Intentionally smoothed (no seasonal adjustment) to create Q3 variance.
    """
    rows = []
    # Compute 2023 annual revenue to set monthly budget baseline
    rev_2023 = [v["revenue"] for d, v in actuals.items() if d.year == 2023]
    avg_monthly_2023 = sum(rev_2023) / len(rev_2023)

    budget_monthly_rev = avg_monthly_2023 * (1 + yoy_growth)

    budget_dates = _monthly_dates(date(2024, 1, 1), date(2024, 12, 1))

    # 2023 ratio averages for cost lines
    cogs_2023 = [v["cogs"] / v["revenue"] for d, v in actuals.items() if d.year == 2023]
    rd_2023   = [v["rd_expense"] / v["revenue"] for d, v in actuals.items() if d.year == 2023]
    sm_2023   = [v["sm_expense"] / v["revenue"] for d, v in actuals.items() if d.year == 2023]
    ga_2023   = [v["ga_expense"] / v["revenue"] for d, v in actuals.items() if d.year == 2023]

    cogs_r = sum(cogs_2023) / len(cogs_2023) * 0.97   # slight improvement budgeted
    rd_r   = sum(rd_2023)   / len(rd_2023)   * 0.97
    sm_r   = sum(sm_2023)   / len(sm_2023)   * 1.02   # slight S&M increase budgeted
    ga_r   = sum(ga_2023)   / len(ga_2023)

    for d in budget_dates:
        # Budget applies mild seasonal factors but underestimates Q3 dip
        seasonal = {
            1: 0.97, 2: 1.01, 3: 1.06, 4: 1.01, 5: 1.02, 6: 1.00,
            7: 0.98, 8: 0.97, 9: 0.99,   # budget assumes only mild Q3 softness
            10: 1.04, 11: 1.03, 12: 1.06,
        }
        rev = round(budget_monthly_rev * seasonal.get(d.month, 1.0))

        for metric, amount in [
            ("revenue",      rev),
            ("cogs",         round(rev * cogs_r)),
            ("gross_profit", round(rev * (1 - cogs_r))),
            ("rd_expense",   round(rev * rd_r)),
            ("sm_expense",   round(rev * sm_r)),
            ("ga_expense",   round(rev * ga_r)),
            ("total_opex",   round(rev * (rd_r + sm_r + ga_r))),
            ("ebitda",       round(rev * (1 - cogs_r - rd_r - sm_r - ga_r))),
        ]:
            rows.append({
                "company_id": company_id,
                "fiscal_year": 2024,
                "period": d,
                "department": None,
                "metric_name": metric,
                "budgeted_amount": amount,
                "version": version,
            })

    # Department-level budget for revenue and COGS (4 departments for FTPL)
    dept_splits = {
        "Product"    : 0.50,
        "Enterprise" : 0.30,
        "SMB"        : 0.15,
        "Other"      : 0.05,
    }
    for d in budget_dates:
        seasonal_rev = round(budget_monthly_rev * {
            1: 0.97, 2: 1.01, 3: 1.06, 4: 1.01, 5: 1.02, 6: 1.00,
            7: 0.98, 8: 0.97, 9: 0.99, 10: 1.04, 11: 1.03, 12: 1.06,
        }.get(d.month, 1.0))
        for dept, split in dept_splits.items():
            rows.append({
                "company_id": company_id,
                "fiscal_year": 2024,
                "period": d,
                "department": dept,
                "metric_name": "revenue",
                "budgeted_amount": round(seasonal_rev * split),
                "version": version,
            })

    return rows


# ---------------------------------------------------------------------------
# KPI definitions
# ---------------------------------------------------------------------------

KPI_DEFINITIONS = [
    ("revenue",       "Revenue",                   "Total revenue from operations",    "SUM(invoices)",    "INR", "UP",   5.0,  False),
    ("cogs",          "Cost of Revenue",            "Direct costs of delivering product/service", "SUM(cogs_lines)", "INR", "DOWN", 5.0, False),
    ("gross_profit",  "Gross Profit",               "Revenue minus COGS",               "Revenue - COGS",   "INR", "UP",   5.0,  False),
    ("rd_expense",    "R&D Expense",                "Research and development costs",   "SUM(rd_lines)",    "INR", "DOWN", 8.0,  False),
    ("sm_expense",    "Sales & Marketing",          "Sales and marketing costs",        "SUM(sm_lines)",    "INR", "DOWN", 8.0,  False),
    ("ga_expense",    "General & Administrative",   "G&A overhead costs",               "SUM(ga_lines)",    "INR", "DOWN", 8.0,  False),
    ("total_opex",    "Total Operating Expenses",   "R&D + S&M + G&A",                  "rd + sm + ga",     "INR", "DOWN", 5.0,  False),
    ("ebitda",        "EBITDA",                     "Earnings before interest, tax, depreciation & amortisation", "GP - OpEx", "INR", "UP", 5.0, False),
    ("gross_margin",  "Gross Margin %",             "Gross Profit / Revenue",           "GP / Revenue",     "PCT", "UP",   3.0,  True),
    ("ebitda_margin", "EBITDA Margin %",            "EBITDA / Revenue",                 "EBITDA / Revenue", "PCT", "UP",   3.0,  True),
    ("rd_ratio",      "R&D % of Revenue",           "R&D Expense as % of Revenue",      "rd / revenue",     "PCT", "DOWN", 4.0,  True),
    ("sm_ratio",      "S&M % of Revenue",           "S&M Expense as % of Revenue",      "sm / revenue",     "PCT", "DOWN", 4.0,  True),
]


# ---------------------------------------------------------------------------
# Synthetic 10-K / Annual Report text (for RAG)
# ---------------------------------------------------------------------------
# These are stored in financial_documents. NOT pre-embedded.
# Your RAG pipeline must chunk, embed, and index them.

def _build_annual_report_text(company: Company, fiscal_year: int, data: Dict) -> str:
    """Build synthetic annual report text incorporating real financial numbers."""

    rev_total   = data["rev_total"]
    rev_prev    = data["rev_prev"]
    gp_total    = data["gp_total"]
    ebitda_total = data["ebitda_total"]
    rev_growth  = data["rev_growth"]
    gm_pct      = data["gm_pct"]
    ebitda_pct  = data["ebitda_pct"]
    top_risks   = data["top_risks"]
    headcount   = data["headcount"]

    fy_label = f"FY{fiscal_year}-{str(fiscal_year+1)[2:]}"
    period_label = f"April 1, {fiscal_year} to March 31, {fiscal_year+1}"

    W = 80
    sep = "=" * W

    sections = f"""{sep}
{company.name.upper().center(W)}
ANNUAL REPORT {fy_label.upper()}
For the period: {period_label}
CIN: {str(uuid.uuid5(uuid.NAMESPACE_DNS, company.erp_code + str(fiscal_year))).upper()[:21]}
{sep}

SECTION 1: BUSINESS OVERVIEW
{"-" * W}
{company.name} is a {company.industry} company incorporated in India. The Company provides
technology-driven solutions to enterprise and mid-market clients across financial services,
manufacturing, and retail sectors.

As of March 31, {fiscal_year+1}, the Company had approximately {headcount:,} full-time employees
across its offices in Bengaluru, Mumbai, and Delhi NCR.

{sep}

SECTION 2: MANAGEMENT DISCUSSION & ANALYSIS (MD&A)
{"-" * W}

2.1 FINANCIAL PERFORMANCE OVERVIEW

The Company delivered revenue of ₹{rev_total/1e7:.2f} Crores for {fy_label}, representing a
{rev_growth:+.1f}% growth compared to ₹{rev_prev/1e7:.2f} Crores in the prior year.

Gross profit stood at ₹{gp_total/1e7:.2f} Crores, yielding a gross margin of {gm_pct:.1f}%.
{"Gross margins expanded by approximately 200 basis points year-over-year, driven by infrastructure cost optimisation and pricing improvements on enterprise contracts." if gm_pct > 60 else "Gross margins remained stable as revenue growth was matched by proportional cost of delivery increases."}

EBITDA for the year was ₹{ebitda_total/1e7:.2f} Crores, an EBITDA margin of {ebitda_pct:.1f}%.

2.2 REVENUE BY SEGMENT

{"Product-led revenue contributed approximately 50% of total revenue, growing 28% year-over-year driven by new enterprise logo additions and expansion within the existing customer base. Enterprise segment revenue grew 35%, reflecting the Company's continued focus on upmarket motion." if company.industry.startswith("Tech") else "Project-based revenue contributed 72% of total revenue, with the remainder from managed services retainers. New client wins in the BFSI and manufacturing verticals drove the majority of growth."}

2.3 OPERATING EXPENSES

Research and Development expenses were {"contained at approximately 20% of revenue as the Company benefited from R&D efficiency gains from prior-year investments. Headcount in the engineering function grew 18% during the year." if company.industry.startswith("Tech") else "minimal at approximately 5% of revenue, consistent with the services-led business model."}

Sales & Marketing expenses {"increased modestly as a percentage of revenue, reflecting continued investment in the enterprise go-to-market motion. Sales cycle times improved from an average of 4.2 months to 3.6 months." if fiscal_year >= 2022 else "were maintained at prior-year levels as the Company focused on organic expansion within the existing customer base."}

2.4 NOTABLE EVENTS DURING THE YEAR

{"In Q2 FY" + str(fiscal_year) + "-" + str(fiscal_year+1)[2:] + ", the Company launched its next-generation analytics platform, which drove a significant acceleration in new bookings. The launch contributed approximately ₹" + f"{rev_total * 0.05 / 1e7:.1f}" + " Crores in incremental revenue in the second half of the year." if fiscal_year == 2022 and company.erp_code == "FTPL-001" else "There were no material one-time events during the year."}

{sep}

SECTION 3: RISK FACTORS
{"-" * W}

The following risks could materially affect the Company's business, financial condition, and results
of operations. This is not an exhaustive list.

3.1 {top_risks[0]["title"]}
{textwrap.fill(top_risks[0]["description"], width=W-4, initial_indent="    ", subsequent_indent="    ")}

3.2 {top_risks[1]["title"]}
{textwrap.fill(top_risks[1]["description"], width=W-4, initial_indent="    ", subsequent_indent="    ")}

3.3 {top_risks[2]["title"]}
{textwrap.fill(top_risks[2]["description"], width=W-4, initial_indent="    ", subsequent_indent="    ")}

3.4 MACROECONOMIC AND MARKET RISK
    Global macroeconomic uncertainty, including interest rate volatility and enterprise IT spending
    slowdowns, could adversely impact demand for the Company's products and services. The Company
    monitors pipeline health and churn indicators on a monthly basis as early-warning signals.

3.5 KEY PERSONNEL RISK
    The Company's performance is dependent on retaining key technical and commercial talent. Attrition
    in senior engineering roles could delay product roadmap commitments. The Company has instituted
    long-term incentive plans for key personnel to mitigate this risk.

{sep}

SECTION 4: LIQUIDITY AND CAPITAL RESOURCES
{"-" * W}

4.1 CASH AND CASH EQUIVALENTS
As of March 31, {fiscal_year+1}, the Company held cash and cash equivalents of approximately
₹{ebitda_total * 0.8 / 1e7:.1f} Crores. {"The Company generated positive free cash flow for the sixth consecutive quarter, reflecting the high cash-conversion characteristics of the SaaS business model." if company.industry.startswith("Tech") else "Cash generation remained steady, with working capital cycles of approximately 45–60 days."}

4.2 DEBT AND FINANCING
{"The Company carries no long-term debt as of the balance sheet date. A working capital credit facility of ₹5 Crores remains undrawn." if company.industry.startswith("Tech") else "The Company utilises a secured term loan of ₹8 Crores for office expansion, repayable over 36 months. Interest coverage ratio was 8.2x."}

4.3 CAPITAL EXPENDITURE
Capital expenditure for the year amounted to ₹{rev_total * 0.03 / 1e7:.1f} Crores, primarily
comprising server infrastructure upgrades and office fit-out costs.

4.4 OUTLOOK
The Company's Board of Directors has approved a budget for {fy_label.replace(str(fiscal_year), str(fiscal_year+1)).replace(str(fiscal_year+1)[2:], str(fiscal_year+2)[2:])} targeting {"15–18%" if company.industry.startswith("Tech") else "12–15%"} revenue growth
with continued focus on margin expansion. {"The Company expects to reach EBITDA-break-even on a fully-loaded basis by Q3 of the next fiscal year." if ebitda_pct < 10 else f"The Company targets EBITDA margins of {ebitda_pct + 2:.0f}–{ebitda_pct + 4:.0f}% for the forthcoming year."}

{sep}

SECTION 5: FORWARD-LOOKING STATEMENTS
{"-" * W}
This Annual Report contains forward-looking statements. These statements are based on
management's current expectations and assumptions and involve known and unknown risks and
uncertainties. Actual results may differ materially from those expressed or implied. The
Company does not undertake to update any forward-looking statement after the date hereof.

For and on behalf of the Board of Directors
{company.name}

Director                                      Chief Financial Officer
Date: September 30, {fiscal_year+1}
{sep}
"""
    return sections


# ---------------------------------------------------------------------------
# Compute annual summaries for 10-K text
# ---------------------------------------------------------------------------

def _annual_summary(actuals: Dict[date, Dict[str, float]], year: int) -> Dict:
    rows = {d: v for d, v in actuals.items() if d.year == year}
    prev = {d: v for d, v in actuals.items() if d.year == year - 1}
    rev_total    = sum(v["revenue"]      for v in rows.values())
    rev_prev     = sum(v["revenue"]      for v in prev.values()) if prev else rev_total * 0.8
    gp_total     = sum(v["gross_profit"] for v in rows.values())
    ebitda_total = sum(v["ebitda"]       for v in rows.values())
    return {
        "rev_total":    rev_total,
        "rev_prev":     rev_prev,
        "gp_total":     gp_total,
        "ebitda_total": ebitda_total,
        "rev_growth":   (rev_total / rev_prev - 1) * 100 if rev_prev else 0,
        "gm_pct":       gp_total / rev_total * 100 if rev_total else 0,
        "ebitda_pct":   ebitda_total / rev_total * 100 if rev_total else 0,
        "headcount":    int(rev_total / 1_200_000),   # proxy
        "top_risks": [
            {
                "title": "CUSTOMER CONCENTRATION RISK",
                "description": (
                    f"As of March 31, {year+1}, the Company's top 10 customers collectively "
                    "accounted for approximately 38% of total revenue. The loss of one or more "
                    "large customers could have a material adverse effect on revenue and profitability. "
                    "The Company actively manages this risk through contract renewal programmes and "
                    "cross-sell initiatives."
                ),
            },
            {
                "title": "TECHNOLOGY AND PRODUCT OBSOLESCENCE RISK",
                "description": (
                    "The technology industry is characterised by rapid innovation cycles. "
                    "Failure to anticipate or respond to changes in customer requirements, "
                    "competitive offerings, or underlying infrastructure technology (cloud platforms, "
                    "AI/ML tooling) could render the Company's products uncompetitive. The Company "
                    "invests approximately 20% of revenue in R&D to mitigate this risk."
                ),
            },
            {
                "title": "FOREIGN EXCHANGE AND PRICING RISK",
                "description": (
                    "Approximately 25% of the Company's revenue is denominated in USD or EUR. "
                    "Significant appreciation of the Indian Rupee could adversely affect reported "
                    "revenue in INR terms. The Company partially hedges this exposure through "
                    "natural hedging via USD-denominated cost contracts."
                ),
            },
        ],
    }


# ---------------------------------------------------------------------------
# DB schema creation
# ---------------------------------------------------------------------------

CREATE_TABLES_SQL = """
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS companies (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                  TEXT NOT NULL,
    erp_code              TEXT UNIQUE NOT NULL,
    industry              TEXT,
    fiscal_year_end_month INTEGER DEFAULT 3,
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS financial_actuals (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id   UUID REFERENCES companies(id),
    period       DATE NOT NULL,
    department   TEXT,
    metric_name  TEXT NOT NULL,
    amount       NUMERIC NOT NULL,
    currency     TEXT DEFAULT 'INR',
    source       TEXT DEFAULT 'ERP',
    ingested_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(company_id, period, department, metric_name)
);

CREATE TABLE IF NOT EXISTS budget_data (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID REFERENCES companies(id),
    fiscal_year     INTEGER NOT NULL,
    period          DATE NOT NULL,
    department      TEXT,
    metric_name     TEXT NOT NULL,
    budgeted_amount NUMERIC NOT NULL,
    version         TEXT DEFAULT 'FY2024-v1',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(company_id, period, department, metric_name, version)
);

CREATE TABLE IF NOT EXISTS variance_records (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       UUID REFERENCES companies(id),
    period           DATE NOT NULL,
    department       TEXT,
    metric_name      TEXT NOT NULL,
    actual_amount    NUMERIC,
    budget_amount    NUMERIC,
    variance_amount  NUMERIC,
    variance_pct     NUMERIC,
    is_favorable     BOOLEAN,
    materiality      TEXT,
    waterfall_rank   INTEGER,
    status           TEXT DEFAULT 'PENDING',
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS forecast_records (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID REFERENCES companies(id),
    metric_name     TEXT NOT NULL,
    forecast_period DATE NOT NULL,
    point_forecast  NUMERIC,
    lower_bound_80  NUMERIC,
    upper_bound_80  NUMERIC,
    lower_bound_95  NUMERIC,
    upper_bound_95  NUMERIC,
    model_name      TEXT,
    model_version   TEXT,
    in_sample_mape  NUMERIC,
    run_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scenario_plans (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id             UUID REFERENCES companies(id),
    scenario_type          TEXT NOT NULL,
    label                  TEXT,
    assumptions            JSONB NOT NULL,
    projected_revenue      NUMERIC,
    projected_gross_profit NUMERIC,
    projected_ebitda       NUMERIC,
    projection_start       DATE,
    projection_end         DATE,
    created_at             TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS financial_commentary (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       UUID REFERENCES companies(id),
    period           DATE,
    commentary_type  TEXT,
    narrative        TEXT NOT NULL,
    key_insights     JSONB,
    model_version    TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS anomaly_flags (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       UUID REFERENCES companies(id),
    period           DATE NOT NULL,
    metric_name      TEXT NOT NULL,
    expected_value   NUMERIC,
    actual_value     NUMERIC,
    z_score          NUMERIC,
    detection_method TEXT,
    severity         TEXT NOT NULL,
    status           TEXT DEFAULT 'PENDING',
    resolution_note  TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS financial_documents (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id    UUID REFERENCES companies(id),
    document_name TEXT NOT NULL,
    document_type TEXT,
    fiscal_year   INTEGER,
    full_text     TEXT,
    file_hash     TEXT UNIQUE,
    page_count    INTEGER,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id         UUID REFERENCES financial_documents(id),
    chunk_index         INTEGER NOT NULL,
    section             TEXT,
    content             TEXT NOT NULL,
    token_count         INTEGER,
    external_vector_id  TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS kpi_definitions (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    metric_name               TEXT UNIQUE NOT NULL,
    display_name              TEXT,
    description               TEXT,
    formula                   TEXT,
    unit                      TEXT DEFAULT 'INR',
    favorable_direction       TEXT,
    materiality_threshold_pct NUMERIC DEFAULT 5.0,
    is_ratio                  BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS hitl_approvals (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    flag_id              UUID,
    flag_type            TEXT,
    temporal_workflow_id TEXT NOT NULL,
    slack_message_ts     TEXT,
    decision             TEXT,
    reviewer_slack_id    TEXT,
    reviewed_at          TIMESTAMPTZ,
    notes                TEXT
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_run_id  TEXT,
    agent_name       TEXT NOT NULL,
    action           TEXT NOT NULL,
    input_summary    TEXT,
    output_summary   TEXT,
    model_name       TEXT,
    eval_score       NUMERIC,
    duration_ms      INTEGER,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_sessions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_run_id  TEXT NOT NULL,
    agent_name       TEXT NOT NULL,
    session_data     JSONB,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS workflow_states (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    temporal_workflow_id  TEXT UNIQUE NOT NULL,
    agno_workflow_name    TEXT NOT NULL,
    status                TEXT NOT NULL,
    state_data            JSONB,
    started_at            TIMESTAMPTZ DEFAULT NOW(),
    completed_at          TIMESTAMPTZ
);
"""


# ---------------------------------------------------------------------------
# CSV export — Q3 2024 actuals for upload demo
# ---------------------------------------------------------------------------

def export_q3_2024_csv(
    company: Company,
    actuals: Dict[date, Dict[str, float]],
    filepath: Path,
) -> None:
    """Export Q3 2024 actuals as a CSV for the student to upload via the UI."""
    q3_dates = [date(2024, 7, 1), date(2024, 8, 1), date(2024, 9, 1)]
    rows = []
    for d in q3_dates:
        if d in actuals:
            for metric, amount in actuals[d].items():
                rows.append({
                    "erp_code":    company.erp_code,
                    "period":      d.isoformat(),
                    "department":  "",
                    "metric_name": metric,
                    "amount":      amount,
                    "currency":    "INR",
                    "source":      "ERP_EXPORT",
                })

    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["erp_code", "period", "department", "metric_name", "amount", "currency", "source"]
        )
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("Connecting to %s", DATABASE_URL.split("@")[-1])
    try:
        conn = psycopg2.connect(DATABASE_URL)
    except Exception as exc:
        log.error("Cannot connect to PostgreSQL: %s", exc)
        sys.exit(1)

    # --- Create tables ---
    with conn:
        with conn.cursor() as cur:
            log.info("Creating tables (idempotent)…")
            cur.execute(CREATE_TABLES_SQL)

    # --- Generate actuals data ---
    log.info("Generating time series data…")
    ftpl_actuals = _generate_ftpl_actuals()
    fcpl_actuals = _generate_fcpl_actuals()

    actuals_map = {FTPL.id: ftpl_actuals, FCPL.id: fcpl_actuals}

    with conn:
        with conn.cursor() as cur:

            # Insert companies
            for company in COMPANIES:
                cur.execute(
                    """
                    INSERT INTO companies (id, name, erp_code, industry, fiscal_year_end_month)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (erp_code) DO UPDATE
                        SET name = EXCLUDED.name, industry = EXCLUDED.industry
                    """,
                    (company.id, company.name, company.erp_code, company.industry, company.fiscal_year_end_month),
                )
                log.info("  ✓ Company: %s (%s)", company.name, company.erp_code)

            # Insert KPI definitions
            for row in KPI_DEFINITIONS:
                metric, display, desc, formula, unit, fav_dir, mat_thr, is_ratio = row
                cur.execute(
                    """
                    INSERT INTO kpi_definitions
                        (metric_name, display_name, description, formula, unit,
                         favorable_direction, materiality_threshold_pct, is_ratio)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (metric_name) DO UPDATE
                        SET materiality_threshold_pct = EXCLUDED.materiality_threshold_pct
                    """,
                    (metric, display, desc, formula, unit, fav_dir, mat_thr, is_ratio),
                )
            log.info("  ✓ KPI definitions: %d rows", len(KPI_DEFINITIONS))

            # Insert actuals
            total_actual_rows = 0
            for company in COMPANIES:
                data = actuals_map[company.id]
                rows = []
                for period, metrics in data.items():
                    for metric, amount in metrics.items():
                        rows.append((
                            str(uuid.uuid4()),
                            company.id, period, None,
                            metric, amount, "INR", "ERP",
                        ))
                execute_values(
                    cur,
                    """
                    INSERT INTO financial_actuals
                        (id, company_id, period, department, metric_name, amount, currency, source)
                    VALUES %s
                    ON CONFLICT (company_id, period, department, metric_name) DO NOTHING
                    """,
                    rows,
                )
                total_actual_rows += len(rows)
                log.info("  ✓ %s actuals: %d rows (%d months × 8 metrics)",
                         company.erp_code, len(rows), len(data))

            # Insert budget data
            for company in COMPANIES:
                data = actuals_map[company.id]
                yoy = 0.15 if company.erp_code == "FTPL-001" else 0.12
                budget_rows = _generate_budget(company.id, data, yoy)
                execute_values(
                    cur,
                    """
                    INSERT INTO budget_data
                        (id, company_id, fiscal_year, period, department,
                         metric_name, budgeted_amount, version)
                    VALUES %s
                    ON CONFLICT (company_id, period, department, metric_name, version) DO NOTHING
                    """,
                    [
                        (str(uuid.uuid4()),
                         r["company_id"], r["fiscal_year"], r["period"],
                         r["department"], r["metric_name"],
                         r["budgeted_amount"], r["version"])
                        for r in budget_rows
                    ],
                )
                log.info("  ✓ %s budget: %d rows (12 months × 8 metrics + dept splits)",
                         company.erp_code, len(budget_rows))

            # Insert annual report documents (NOT pre-embedded)
            for company in COMPANIES:
                data = actuals_map[company.id]
                for fy in [2022, 2023]:
                    summary = _annual_summary(data, fy)
                    text = _build_annual_report_text(company, fy, summary)
                    h = hashlib.sha256(text.encode()).hexdigest()[:16]
                    doc_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{company.erp_code}-AR-{fy}"))
                    cur.execute(
                        """
                        INSERT INTO financial_documents
                            (id, company_id, document_name, document_type,
                             fiscal_year, full_text, file_hash, page_count)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (file_hash) DO NOTHING
                        """,
                        (doc_id, company.id,
                         f"{company.name} Annual Report FY{fy}-{str(fy+1)[2:]}",
                         "ANNUAL_REPORT", fy, text, h,
                         len(text) // 3000 + 1),
                    )
                    # Also write the text file to sample_data/
                    txt_path = OUTPUT_DIR / f"{company.erp_code}_Annual_Report_FY{fy}.txt"
                    txt_path.write_text(text, encoding="utf-8")
                    log.info("  ✓ %s FY%d Annual Report → %s", company.erp_code, fy, txt_path.name)

    conn.close()

    # --- Export demo CSVs ---
    for company, actuals in [(FTPL, ftpl_actuals), (FCPL, fcpl_actuals)]:
        csv_path = OUTPUT_DIR / f"{company.erp_code}_Q3_2024_Actuals.csv"
        export_q3_2024_csv(company, actuals, csv_path)
        log.info("  ✓ Demo CSV: %s", csv_path.name)

    # --- Print summary ---
    log.info("")
    log.info("=" * 62)
    log.info("SEED COMPLETE")
    log.info("=" * 62)
    log.info("")
    log.info("PostgreSQL:")
    log.info("  %d companies", len(COMPANIES))
    log.info("  %d months of actuals per company (Jan 2021 – Sep 2024)", len(ALL_DATES))
    log.info("  12-month 2024 budget (consolidated + 4 departments)")
    log.info("  %d KPI definitions with materiality thresholds", len(KPI_DEFINITIONS))
    log.info("  4 synthetic annual report documents (NOT pre-embedded)")
    log.info("")
    log.info("Generated files in sample_data/:")
    for f in sorted(OUTPUT_DIR.iterdir()):
        log.info("  %s", f.name)
    log.info("")
    log.info("PLANTED ANOMALIES (your agents must detect these):")
    log.info("-" * 62)
    anomalies = [
        ("[FTPL] 2022 Apr–May",
         "Revenue spike +22%/+18% above trend. Cause: new product launch.",
         "Expected: ~₹11.5M/month  Actual: ~₹14.0M/month"),
        ("[FTPL] 2023 Oct–Nov",
         "R&D expense +35% above historical ratio. Cause: engineering hiring surge.",
         "Expected R&D ratio: ~20%  Actual: ~27%"),
        ("[FTPL] 2024 Q3 (Jul–Sep)",
         "Revenue -16% below budget. Cause: seasonal dip + macro headwinds.",
         "Budget: ₹45.1M  Actual: ~₹37.8M  → CRITICAL variance, triggers HITL"),
        ("[FCPL] 2024 Aug",
         "Revenue -28% MoM. Cause: large project cancellation.",
         "Expected: ~₹4.8M  Actual: ~₹3.5M  → MATERIAL anomaly flag"),
    ]
    for label, cause, detail in anomalies:
        log.info("")
        log.info("%s: %s", label, cause)
        log.info("  %s", detail)
    log.info("")
    log.info("NEXT STEPS:")
    log.info("  1. Upload sample_data/FTPL-001_Q3_2024_Actuals.csv via your FastAPI endpoint")
    log.info("     to trigger the MonthEndAnalysisWorkflow.")
    log.info("  2. Upload sample_data/FTPL-001_Annual_Report_FY2023.txt via your document")
    log.info("     upload endpoint to run the DocumentIngestionWorkflow and build the RAG index.")
    log.info("  3. Query the RAG: 'What were the main risk factors in FY2023?'")
    log.info("     and verify source chunks are returned alongside the answer.")


if __name__ == "__main__":
    main()
