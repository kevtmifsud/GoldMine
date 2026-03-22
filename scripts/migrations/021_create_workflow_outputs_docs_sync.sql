-- 021: Create workflow_outputs_docs_sync table
--
-- Stores output from the docs_sync workflow which compares codebase
-- state against markdown documentation and reconciles gaps.

CREATE TABLE IF NOT EXISTS workflow_outputs_docs_sync (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_run_id UUID REFERENCES workflow_runs(id),
    triggered_by TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    files_checked TEXT[] NOT NULL DEFAULT '{}',
    gaps_found JSONB NOT NULL DEFAULT '[]',
    files_updated TEXT[] NOT NULL DEFAULT '{}',
    items_needing_human_review JSONB NOT NULL DEFAULT '[]',
    summary TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS
    idx_docs_sync_workflow_run_id
    ON workflow_outputs_docs_sync(workflow_run_id);

CREATE INDEX IF NOT EXISTS
    idx_docs_sync_created_at
    ON workflow_outputs_docs_sync(created_at DESC);
