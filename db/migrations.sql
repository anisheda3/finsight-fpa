-- FinSight FP&A AI — PostgreSQL schema
-- Run: psql $POSTGRES_URL -f db/migrations.sql

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ─────────────────────────────────────────────────────────────
-- Companies
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS companies (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    erp_code    TEXT UNIQUE NOT NULL,
    industry    TEXT,
    fiscal_year_end_month INTEGER DEFAULT 3,  -- March = Indian FY
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────
-- Monthly financial actuals (time series)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS financial_actuals (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id    UUID REFERENCES companies(id) ON DELETE CASCADE,
    period        DATE NOT NULL,
    department    TEXT,
    metric_name   TEXT NOT NULL,
    amount        NUMERIC NOT NULL,
    currency      TEXT DEFAULT 'INR',
    source        TEXT DEFAULT 'ERP',
    source_file_hash TEXT,                   -- lineage
    ingested_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(company_id, period, department, metric_name)
);
CREATE INDEX IF NOT EXISTS idx_actuals_company_period
    ON financial_actuals(company_id, period);
CREATE INDEX IF NOT EXISTS idx_actuals_company_metric_period
    ON financial_actuals(company_id, metric_name, period);

-- ─────────────────────────────────────────────────────────────
-- Budget / plan data (versioned)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS budget_data (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID REFERENCES companies(id) ON DELETE CASCADE,
    fiscal_year     INTEGER NOT NULL,
    period          DATE NOT NULL,
    department      TEXT,
    metric_name     TEXT NOT NULL,
    budgeted_amount NUMERIC NOT NULL,
    version         TEXT DEFAULT 'FY2024-v1',
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(company_id, period, department, metric_name, version)
);
CREATE INDEX IF NOT EXISTS idx_budget_company_period
    ON budget_data(company_id, period);

-- ─────────────────────────────────────────────────────────────
-- KPI definitions / materiality
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS kpi_definitions (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    metric_name              TEXT UNIQUE NOT NULL,
    display_name             TEXT,
    description              TEXT,
    formula                  TEXT,
    unit                     TEXT DEFAULT 'INR',
    favorable_direction      TEXT CHECK (favorable_direction IN ('UP','DOWN')),
    materiality_threshold_pct NUMERIC DEFAULT 5.0,
    is_ratio                 BOOLEAN DEFAULT FALSE
);

-- ─────────────────────────────────────────────────────────────
-- Variance records
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS variance_records (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       UUID REFERENCES companies(id) ON DELETE CASCADE,
    period           DATE NOT NULL,
    department       TEXT,
    metric_name      TEXT NOT NULL,
    actual_amount    NUMERIC,
    budget_amount    NUMERIC,
    variance_amount  NUMERIC,
    variance_pct     NUMERIC,
    is_favorable     BOOLEAN,
    materiality      TEXT CHECK (materiality IN ('IMMATERIAL','NOTABLE','MATERIAL','CRITICAL')),
    waterfall_rank   INTEGER,
    actual_id        UUID REFERENCES financial_actuals(id),     -- lineage
    budget_id        UUID REFERENCES budget_data(id),           -- lineage
    status           TEXT DEFAULT 'PENDING',
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(company_id, period, department, metric_name)
);
CREATE INDEX IF NOT EXISTS idx_variance_company_period
    ON variance_records(company_id, period);

-- ─────────────────────────────────────────────────────────────
-- Forecast records  (model governance fields included)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS forecast_records (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id            UUID REFERENCES companies(id) ON DELETE CASCADE,
    metric_name           TEXT NOT NULL,
    forecast_period       DATE NOT NULL,
    point_forecast        NUMERIC,
    lower_bound_80        NUMERIC,
    upper_bound_80        NUMERIC,
    lower_bound_95        NUMERIC,
    upper_bound_95        NUMERIC,
    model_name            TEXT,           -- prophet | sarima | linear
    model_version         TEXT,
    model_params          JSONB,
    in_sample_mape        NUMERIC,        -- holdout MAPE at training time
    holdout_months        INTEGER,
    horizon_months        INTEGER,
    training_start_period DATE,
    training_end_period   DATE,
    run_id                TEXT,
    selected_reason       TEXT,
    fallback_reason       TEXT,
    prior_model_used      TEXT,
    prior_mape            NUMERIC,
    input_row_hash        TEXT,           -- lineage
    run_at                TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(company_id, metric_name, forecast_period, model_name, run_id)
);
CREATE INDEX IF NOT EXISTS idx_forecast_company_metric_period
    ON forecast_records(company_id, metric_name, forecast_period);

-- ─────────────────────────────────────────────────────────────
-- Anomaly flags
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS anomaly_flags (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id        UUID REFERENCES companies(id) ON DELETE CASCADE,
    period            DATE NOT NULL,
    metric_name       TEXT NOT NULL,
    expected_value    NUMERIC,
    actual_value      NUMERIC,
    z_score           NUMERIC,
    detection_method  TEXT,
    severity          TEXT NOT NULL CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    actual_id         UUID REFERENCES financial_actuals(id),    -- lineage
    status            TEXT DEFAULT 'PENDING',
    resolution_note   TEXT,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(company_id, period, metric_name, detection_method)
);
CREATE INDEX IF NOT EXISTS idx_anomaly_company_period
    ON anomaly_flags(company_id, period);

-- ─────────────────────────────────────────────────────────────
-- Scenario plans
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scenario_plans (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id             UUID REFERENCES companies(id) ON DELETE CASCADE,
    scenario_type          TEXT NOT NULL CHECK (scenario_type IN ('BASE','BULL','BEAR')),
    label                  TEXT,
    assumptions            JSONB NOT NULL,
    projected_revenue      NUMERIC,
    projected_gross_profit NUMERIC,
    projected_ebitda       NUMERIC,
    projected_pl           JSONB,                -- per-quarter detail
    projection_start       DATE,
    projection_end         DATE,
    based_on_forecast_run_id TEXT,               -- lineage
    created_at             TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(company_id, scenario_type, label, projection_start, projection_end)
);
CREATE INDEX IF NOT EXISTS idx_scenario_company_type
    ON scenario_plans(company_id, scenario_type);

-- ─────────────────────────────────────────────────────────────
-- Commentary
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS financial_commentary (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       UUID REFERENCES companies(id) ON DELETE CASCADE,
    period           DATE,
    commentary_type  TEXT,
    narrative        TEXT NOT NULL,
    key_insights     JSONB,
    figures_cited    JSONB,
    grounding_score  NUMERIC,
    model_version    TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────
-- HITL approvals
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS hitl_approvals (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    flag_id               UUID,
    flag_type             TEXT CHECK (flag_type IN ('anomaly','variance')),
    temporal_workflow_id  TEXT NOT NULL,
    slack_message_ts      TEXT,
    decision              TEXT CHECK (decision IN ('APPROVED','REJECTED','ADJUSTED','PENDING')),
    reviewer_slack_id     TEXT,
    reviewed_at           TIMESTAMPTZ,
    notes                 TEXT,
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────
-- Audit + agent run observability
-- ─────────────────────────────────────────────────────────────
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
CREATE INDEX IF NOT EXISTS idx_audit_workflow ON audit_logs(workflow_run_id);

CREATE TABLE IF NOT EXISTS agent_runs (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_run_id   TEXT,
    session_id        TEXT,
    agent_name        TEXT NOT NULL,
    input             JSONB,
    output            JSONB,
    guardrail_results JSONB,
    eval_results      JSONB,
    started_at        TIMESTAMPTZ DEFAULT NOW(),
    completed_at      TIMESTAMPTZ,
    status            TEXT,
    duration_ms       INTEGER
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_workflow ON agent_runs(workflow_run_id);

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

-- ─────────────────────────────────────────────────────────────
-- Documents (annual reports etc.)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS financial_documents (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id   UUID REFERENCES companies(id) ON DELETE CASCADE,
    title        TEXT,
    doc_type     TEXT,
    period_year  INTEGER,
    source_path  TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id  UUID REFERENCES financial_documents(id) ON DELETE CASCADE,
    chunk_index  INTEGER,
    content      TEXT,
    tokens       INTEGER,
    tsv          tsvector,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_document_chunks_document ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_tsv ON document_chunks USING GIN(tsv);

-- Auto-maintain tsvector
CREATE OR REPLACE FUNCTION document_chunks_tsv_trigger() RETURNS trigger AS $$
BEGIN
  NEW.tsv := to_tsvector('english', COALESCE(NEW.content, ''));
  RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_document_chunks_tsv ON document_chunks;
CREATE TRIGGER trg_document_chunks_tsv
BEFORE INSERT OR UPDATE ON document_chunks
FOR EACH ROW EXECUTE FUNCTION document_chunks_tsv_trigger();

-- ─────────────────────────────────────────────────────────────
-- Agent memory store (used by MemoryManager)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_memory (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id   UUID,
    agent_name   TEXT NOT NULL,
    memory_key   TEXT NOT NULL,
    memory_value JSONB NOT NULL,
    tags         TEXT[],
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_agent_memory_lookup
    ON agent_memory(company_id, agent_name, memory_key);

-- ─────────────────────────────────────────────────────────────
-- Seed: KPI definitions (referenced by VarianceAgent for materiality)
-- ─────────────────────────────────────────────────────────────
INSERT INTO kpi_definitions (metric_name, display_name, formula, favorable_direction, materiality_threshold_pct)
VALUES
  ('revenue',      'Revenue',       NULL,                                 'UP',   5.0),
  ('cogs',         'COGS',          NULL,                                 'DOWN', 5.0),
  ('gross_profit', 'Gross Profit',  'revenue - cogs',                     'UP',   5.0),
  ('rd',           'R&D Expense',   NULL,                                 'DOWN', 7.5),
  ('sm',           'Sales & Mktg',  NULL,                                 'DOWN', 7.5),
  ('ga',           'G&A Expense',   NULL,                                 'DOWN', 7.5),
  ('ebitda',       'EBITDA',        'gross_profit - rd - sm - ga',        'UP',   5.0)
ON CONFLICT (metric_name) DO NOTHING;
