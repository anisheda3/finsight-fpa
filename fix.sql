-- Add missing columns to financial_actuals
ALTER TABLE financial_actuals ADD COLUMN IF NOT EXISTS source_file_hash TEXT;

-- Add missing columns to forecast_records
ALTER TABLE forecast_records ADD COLUMN IF NOT EXISTS model_params JSONB DEFAULT '{}';
ALTER TABLE forecast_records ADD COLUMN IF NOT EXISTS holdout_months INTEGER;
ALTER TABLE forecast_records ADD COLUMN IF NOT EXISTS horizon_months INTEGER;
ALTER TABLE forecast_records ADD COLUMN IF NOT EXISTS training_start_period DATE;
ALTER TABLE forecast_records ADD COLUMN IF NOT EXISTS training_end_period DATE;
ALTER TABLE forecast_records ADD COLUMN IF NOT EXISTS run_id TEXT;
ALTER TABLE forecast_records ADD COLUMN IF NOT EXISTS selected_reason TEXT;
ALTER TABLE forecast_records ADD COLUMN IF NOT EXISTS fallback_reason TEXT;
ALTER TABLE forecast_records ADD COLUMN IF NOT EXISTS prior_model_used TEXT;
ALTER TABLE forecast_records ADD COLUMN IF NOT EXISTS prior_mape NUMERIC;

ALTER TABLE scenario_plans ADD COLUMN IF NOT EXISTS projected_pl JSONB DEFAULT '[]';
ALTER TABLE scenario_plans ADD COLUMN IF NOT EXISTS based_on_forecast_run_id TEXT;

ALTER TABLE financial_commentary ADD COLUMN IF NOT EXISTS figures_cited JSONB DEFAULT '[]';
ALTER TABLE financial_commentary ADD COLUMN IF NOT EXISTS grounding_score NUMERIC;

ALTER TABLE anomaly_flags ADD COLUMN IF NOT EXISTS actual_id UUID;
ALTER TABLE budget_data ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;

CREATE TABLE IF NOT EXISTS agent_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_run_id TEXT, session_id TEXT, agent_name TEXT NOT NULL,
    input JSONB, output JSONB, guardrail_results JSONB, eval_results JSONB,
    started_at TIMESTAMPTZ DEFAULT NOW(), completed_at TIMESTAMPTZ,
    status TEXT DEFAULT 'COMPLETED', duration_ms INTEGER
);

CREATE TABLE IF NOT EXISTS agent_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id TEXT, agent_name TEXT NOT NULL, memory_key TEXT NOT NULL,
    memory_value JSONB NOT NULL, tags TEXT[] DEFAULT '{}', updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(company_id, agent_name, memory_key)
);

ALTER TABLE variance_records DROP CONSTRAINT IF EXISTS variance_records_unique;
ALTER TABLE variance_records ADD CONSTRAINT variance_records_unique
    UNIQUE(company_id, period, COALESCE(department,''), metric_name);

ALTER TABLE anomaly_flags DROP CONSTRAINT IF EXISTS anomaly_flags_unique;
ALTER TABLE anomaly_flags ADD CONSTRAINT anomaly_flags_unique
    UNIQUE(company_id, period, metric_name, detection_method);
