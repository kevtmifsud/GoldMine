-- 022: Create workflow_outputs_financial_model table
--
-- Stores metadata for each financial model generation run.
-- The actual Excel file lives in Supabase S3 storage bucket.

CREATE TABLE IF NOT EXISTS workflow_outputs_financial_model (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_run_id UUID REFERENCES workflow_runs(id),
    ticker TEXT NOT NULL,
    version TEXT NOT NULL,
    s3_path TEXT NOT NULL,
    s3_bucket TEXT NOT NULL DEFAULT 'financial_model_outputs',
    key_kpis TEXT[] NOT NULL DEFAULT '{}',
    assumptions_snapshot JSONB NOT NULL DEFAULT '{}',
    peer_set TEXT[] NOT NULL DEFAULT '{}',
    sheets_generated TEXT[] NOT NULL DEFAULT '{}',
    unmapped_metrics TEXT[] NOT NULL DEFAULT '{}',
    kpis_need_user_input BOOLEAN NOT NULL DEFAULT FALSE,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    generated_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS
    idx_financial_model_ticker
    ON workflow_outputs_financial_model(ticker);
CREATE INDEX IF NOT EXISTS
    idx_financial_model_workflow_run_id
    ON workflow_outputs_financial_model(workflow_run_id);
CREATE INDEX IF NOT EXISTS
    idx_financial_model_generated_at
    ON workflow_outputs_financial_model(generated_at DESC);
CREATE INDEX IF NOT EXISTS
    idx_financial_model_ticker_version
    ON workflow_outputs_financial_model(ticker, version DESC);
