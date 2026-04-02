-- Create pages table for analyst dashboards/module pages.
-- Each page contains a JSONB array of tile configs that reference MCP tools.

CREATE TABLE IF NOT EXISTS pages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    tiles JSONB NOT NULL DEFAULT '[]',
    is_shared BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pages_user_id
    ON pages(user_id);

CREATE INDEX IF NOT EXISTS idx_pages_shared
    ON pages(is_shared)
    WHERE is_shared = true;
