#!/usr/bin/env python3
"""Migration: create all new domain tables defined in instructions/domain/data-schema.md.

Tables created (20):
  Research & notes:     analyst_notes, buyside_notes, sellside_notes, sellside_estimates, guidance
  Estimates:            internal_estimates, buyside_estimates, consensus_estimates
  Portfolio & risk:     trade_requests, daily_pnl, portfolio_concentration, portfolio_risk
  Models:               model_outputs, model_peers
  Workflows:            workflow_registry, workflow_runs, workflow_outputs_earnings_preview
  Alt data:             alt_data
  Platform:             chat_sessions
  Model generation:     workflow_outputs_financial_model

All insert-only tables omit DELETE policies per domain spec.
Idempotent — safe to re-run (CREATE TABLE IF NOT EXISTS throughout).

Usage:
    python scripts/migrate_new_domain_tables.py
    python scripts/migrate_new_domain_tables.py --dry-run   # preview without changes
"""
from __future__ import annotations

import argparse
import sys

try:
    import psycopg2
except ImportError:
    psycopg2 = None  # type: ignore[assignment]

DATABASE_URL = "postgresql://postgres:sC.g6Wf#9h.Bf_f@db.ybjvfeevaxujenwvoewg.supabase.co:5432/postgres"

MIGRATION_SQL = """
-- ============================================================
-- Research & Notes tables
-- ============================================================

-- analyst_notes: internal analyst research notes (insert-only)
CREATE TABLE IF NOT EXISTS analyst_notes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL,
    tickers     TEXT[],
    sectors     TEXT[],
    industries  TEXT[],
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_analyst_notes_user
    ON analyst_notes (user_id);
CREATE INDEX IF NOT EXISTS idx_analyst_notes_tickers
    ON analyst_notes USING GIN (tickers);
CREATE INDEX IF NOT EXISTS idx_analyst_notes_sectors
    ON analyst_notes USING GIN (sectors);
CREATE INDEX IF NOT EXISTS idx_analyst_notes_created
    ON analyst_notes (created_at);

-- buyside_notes: external buyside firm notes (insert-only)
CREATE TABLE IF NOT EXISTS buyside_notes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker          TEXT NOT NULL,
    firm            TEXT NOT NULL,
    published_date  DATE NOT NULL,
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_buyside_notes_ticker
    ON buyside_notes (ticker);
CREATE INDEX IF NOT EXISTS idx_buyside_notes_firm
    ON buyside_notes (firm);
CREATE INDEX IF NOT EXISTS idx_buyside_notes_published
    ON buyside_notes (published_date);

-- sellside_notes: sellside firm notes (insert-only)
CREATE TABLE IF NOT EXISTS sellside_notes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker          TEXT NOT NULL,
    firm            TEXT NOT NULL,
    published_date  DATE NOT NULL,
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sellside_notes_ticker
    ON sellside_notes (ticker);
CREATE INDEX IF NOT EXISTS idx_sellside_notes_firm
    ON sellside_notes (firm);
CREATE INDEX IF NOT EXISTS idx_sellside_notes_published
    ON sellside_notes (published_date);

-- sellside_estimates: structured estimates extracted from sellside notes (insert-only)
CREATE TABLE IF NOT EXISTS sellside_estimates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker          TEXT NOT NULL,
    firm            TEXT NOT NULL,
    analysts        TEXT[],
    period          TEXT NOT NULL,
    metric          TEXT NOT NULL,
    value           NUMERIC NOT NULL,
    unit            TEXT,
    published_date  DATE NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sellside_est_ticker
    ON sellside_estimates (ticker);
CREATE INDEX IF NOT EXISTS idx_sellside_est_firm
    ON sellside_estimates (firm);
CREATE INDEX IF NOT EXISTS idx_sellside_est_period
    ON sellside_estimates (ticker, metric, period);
CREATE INDEX IF NOT EXISTS idx_sellside_est_published
    ON sellside_estimates (published_date);

-- guidance: company-issued forward guidance (insert-only)
CREATE TABLE IF NOT EXISTS guidance (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker          TEXT NOT NULL,
    period          TEXT NOT NULL,
    metric          TEXT NOT NULL,
    value           NUMERIC NOT NULL,
    unit            TEXT,
    guidance_type   TEXT NOT NULL CHECK (guidance_type IN
                    ('initial', 'raised', 'lowered', 'withdrawn')),
    source          TEXT NOT NULL CHECK (source IN
                    ('transcript', 'filing', 'manual')),
    issued_date     DATE NOT NULL,
    user_id         UUID,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_guidance_ticker
    ON guidance (ticker);
CREATE INDEX IF NOT EXISTS idx_guidance_period
    ON guidance (ticker, metric, period);
CREATE INDEX IF NOT EXISTS idx_guidance_issued
    ON guidance (issued_date);

-- ============================================================
-- Estimates tables (three separate tables, never mixed)
-- ============================================================

-- internal_estimates: our own forward estimates, PIT insert-only
CREATE TABLE IF NOT EXISTS internal_estimates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker          TEXT NOT NULL,
    period          TEXT NOT NULL,
    metric          TEXT NOT NULL,
    value           NUMERIC NOT NULL,
    unit            TEXT,
    user_id         UUID,
    model_version   TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_internal_est_ticker
    ON internal_estimates (ticker);
CREATE INDEX IF NOT EXISTS idx_internal_est_lookup
    ON internal_estimates (ticker, metric, period, created_at DESC);

-- buyside_estimates: external buyside forward estimates (insert-only)
CREATE TABLE IF NOT EXISTS buyside_estimates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker          TEXT NOT NULL,
    firm            TEXT NOT NULL,
    period          TEXT NOT NULL,
    metric          TEXT NOT NULL,
    value           NUMERIC NOT NULL,
    unit            TEXT,
    as_of_date      DATE NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_buyside_est_ticker
    ON buyside_estimates (ticker);
CREATE INDEX IF NOT EXISTS idx_buyside_est_lookup
    ON buyside_estimates (ticker, metric, period, as_of_date DESC);

-- consensus_estimates: street consensus estimates (insert-only)
CREATE TABLE IF NOT EXISTS consensus_estimates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker          TEXT NOT NULL,
    period          TEXT NOT NULL,
    metric          TEXT NOT NULL,
    value           NUMERIC NOT NULL,
    unit            TEXT,
    as_of_date      DATE NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_consensus_est_ticker
    ON consensus_estimates (ticker);
CREATE INDEX IF NOT EXISTS idx_consensus_est_lookup
    ON consensus_estimates (ticker, metric, period, as_of_date DESC);

-- ============================================================
-- Portfolio & Risk tables
-- ============================================================

-- trade_requests: PM trade request staging table (insert-only)
CREATE TABLE IF NOT EXISTS trade_requests (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL,
    ticker          TEXT NOT NULL,
    portfolio       TEXT NOT NULL CHECK (portfolio IN ('flagship', 'long_only')),
    action          TEXT NOT NULL CHECK (action IN ('buy', 'sell')),
    side            TEXT NOT NULL CHECK (side IN ('long', 'short')),
    target_pct      NUMERIC NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'executed', 'cancelled')),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    executed_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_trade_req_user
    ON trade_requests (user_id);
CREATE INDEX IF NOT EXISTS idx_trade_req_ticker
    ON trade_requests (ticker);
CREATE INDEX IF NOT EXISTS idx_trade_req_status
    ON trade_requests (status);
CREATE INDEX IF NOT EXISTS idx_trade_req_portfolio
    ON trade_requests (portfolio);

-- daily_pnl: pre-calculated daily P&L (insert-only)
CREATE TABLE IF NOT EXISTS daily_pnl (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date                        DATE NOT NULL,
    ticker                      TEXT NOT NULL,
    portfolio                   TEXT NOT NULL,
    side                        TEXT NOT NULL CHECK (side IN ('long', 'short')),
    sector                      TEXT,
    industry                    TEXT,
    unrealized_pnl              NUMERIC,
    realized_pnl                NUMERIC,
    daily_return                NUMERIC,
    cumulative_return           NUMERIC,
    contribution_to_portfolio   NUMERIC,
    created_at                  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pnl_date
    ON daily_pnl (date);
CREATE INDEX IF NOT EXISTS idx_pnl_ticker
    ON daily_pnl (ticker);
CREATE INDEX IF NOT EXISTS idx_pnl_portfolio_date
    ON daily_pnl (portfolio, date);
CREATE INDEX IF NOT EXISTS idx_pnl_sector
    ON daily_pnl (sector, date);
CREATE INDEX IF NOT EXISTS idx_pnl_side
    ON daily_pnl (side, date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pnl_grain
    ON daily_pnl (date, ticker, portfolio, side);

-- portfolio_concentration: daily concentration metrics (insert-only)
CREATE TABLE IF NOT EXISTS portfolio_concentration (
    id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date                            DATE NOT NULL,
    ticker                          TEXT NOT NULL,
    portfolio                       TEXT NOT NULL,
    side                            TEXT NOT NULL CHECK (side IN ('long', 'short')),
    sector                          TEXT,
    industry                        TEXT,
    geography                       TEXT,
    position_weight                 NUMERIC,
    sector_weight                   NUMERIC,
    industry_weight                 NUMERIC,
    geo_weight                      NUMERIC,
    is_market_neutral_compliant     BOOLEAN,
    created_at                      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conc_date
    ON portfolio_concentration (date);
CREATE INDEX IF NOT EXISTS idx_conc_portfolio_date
    ON portfolio_concentration (portfolio, date);
CREATE INDEX IF NOT EXISTS idx_conc_ticker
    ON portfolio_concentration (ticker);
CREATE UNIQUE INDEX IF NOT EXISTS idx_conc_grain
    ON portfolio_concentration (date, ticker, portfolio);

-- portfolio_risk: daily beta exposures (insert-only)
CREATE TABLE IF NOT EXISTS portfolio_risk (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date                        DATE NOT NULL,
    ticker                      TEXT NOT NULL,
    portfolio                   TEXT NOT NULL,
    beta                        NUMERIC,
    weighted_beta_contribution  NUMERIC,
    sector                      TEXT,
    side                        TEXT NOT NULL CHECK (side IN ('long', 'short')),
    created_at                  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_risk_date
    ON portfolio_risk (date);
CREATE INDEX IF NOT EXISTS idx_risk_portfolio_date
    ON portfolio_risk (portfolio, date);
CREATE INDEX IF NOT EXISTS idx_risk_ticker
    ON portfolio_risk (ticker);
CREATE UNIQUE INDEX IF NOT EXISTS idx_risk_grain
    ON portfolio_risk (date, ticker, portfolio);

-- ============================================================
-- Models tables
-- ============================================================

-- model_outputs: versioned financial model outputs, long/narrow (insert-only)
CREATE TABLE IF NOT EXISTS model_outputs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker          TEXT NOT NULL,
    version         TEXT NOT NULL,
    as_of_date      DATE NOT NULL,
    sheet           TEXT NOT NULL CHECK (sheet IN (
                    'income_statement', 'balance_sheet', 'cash_flow',
                    'valuation', 'kpis', 'scenarios', 'assumptions')),
    metric          TEXT NOT NULL,
    period          TEXT NOT NULL,
    scenario        TEXT NOT NULL CHECK (scenario IN
                    ('base', 'bull', 'bear', 'actual')),
    value           NUMERIC,
    unit            TEXT CHECK (unit IN
                    ('dollars', 'percentage', 'ratio', 'per_share')),
    created_by      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_model_ticker
    ON model_outputs (ticker);
CREATE INDEX IF NOT EXISTS idx_model_version
    ON model_outputs (ticker, version);
CREATE INDEX IF NOT EXISTS idx_model_current
    ON model_outputs (ticker, sheet, metric, period, scenario, as_of_date DESC);

-- model_peers: peer set per ticker for comps (upsertable)
CREATE TABLE IF NOT EXISTS model_peers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker          TEXT NOT NULL,
    peer_ticker     TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    created_by      TEXT,
    UNIQUE (ticker, peer_ticker)
);

CREATE INDEX IF NOT EXISTS idx_peers_ticker
    ON model_peers (ticker);

-- ============================================================
-- Workflow tables
-- ============================================================

-- workflow_registry: canonical list of all defined workflows (upsertable)
CREATE TABLE IF NOT EXISTS workflow_registry (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_name   TEXT NOT NULL UNIQUE,
    display_name    TEXT NOT NULL,
    description     TEXT,
    required_inputs JSONB,
    output_table    TEXT,
    trigger_type    TEXT NOT NULL CHECK (trigger_type IN
                    ('on_demand', 'scheduled', 'both')),
    schedule_rule   TEXT,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- workflow_runs: every workflow execution (insert-only)
CREATE TABLE IF NOT EXISTS workflow_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id     UUID NOT NULL REFERENCES workflow_registry(id),
    ticker          TEXT,
    triggered_by    TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    cost_usd        NUMERIC,
    output_id       UUID,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_wf_runs_workflow
    ON workflow_runs (workflow_id);
CREATE INDEX IF NOT EXISTS idx_wf_runs_ticker
    ON workflow_runs (ticker);
CREATE INDEX IF NOT EXISTS idx_wf_runs_status
    ON workflow_runs (status);
CREATE INDEX IF NOT EXISTS idx_wf_runs_created
    ON workflow_runs (created_at);

-- workflow_outputs_earnings_preview: structured earnings preview output (insert-only)
CREATE TABLE IF NOT EXISTS workflow_outputs_earnings_preview (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_run_id         UUID NOT NULL REFERENCES workflow_runs(id),
    ticker                  TEXT NOT NULL,
    reporting_period        TEXT NOT NULL,
    forward_period          TEXT NOT NULL,
    key_kpis                TEXT[],
    estimates_table         JSONB,
    actuals_section         JSONB,
    price_section           JSONB,
    portfolio_section       JSONB,
    alt_data_section        JSONB,
    prior_preview_reference JSONB,
    generated_at            TIMESTAMPTZ DEFAULT NOW(),
    generated_by            TEXT NOT NULL,
    citations               JSONB
);

CREATE INDEX IF NOT EXISTS idx_ep_ticker
    ON workflow_outputs_earnings_preview (ticker);
CREATE INDEX IF NOT EXISTS idx_ep_period
    ON workflow_outputs_earnings_preview (ticker, reporting_period);
CREATE INDEX IF NOT EXISTS idx_ep_generated
    ON workflow_outputs_earnings_preview (generated_at);

-- workflow_outputs_financial_model: model generation metadata (insert-only)
CREATE TABLE IF NOT EXISTS workflow_outputs_financial_model (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_run_id         UUID NOT NULL REFERENCES workflow_runs(id),
    ticker                  TEXT NOT NULL,
    version                 TEXT NOT NULL,
    s3_path                 TEXT,
    key_kpis                TEXT[],
    assumptions_snapshot    JSONB,
    generated_at            TIMESTAMPTZ DEFAULT NOW(),
    generated_by            TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fm_out_ticker
    ON workflow_outputs_financial_model (ticker);

-- ============================================================
-- Alt Data table
-- ============================================================

-- alt_data: single table, all alt data types (insert-only)
CREATE TABLE IF NOT EXISTS alt_data (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker          TEXT NOT NULL,
    data_type       TEXT NOT NULL CHECK (data_type IN (
                    'credit_card', 'web_traffic', 'app_downloads',
                    'google_trends', 'email_receipts', 'medical_claims')),
    date_frequency  TEXT NOT NULL CHECK (date_frequency IN
                    ('daily', 'weekly', 'monthly', 'quarterly')),
    date            DATE NOT NULL,
    value           NUMERIC,
    growth          NUMERIC,
    unit            TEXT,
    source_vendor   TEXT,
    data_as_of_date DATE,
    as_of_date      DATE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alt_ticker
    ON alt_data (ticker);
CREATE INDEX IF NOT EXISTS idx_alt_type
    ON alt_data (data_type);
CREATE INDEX IF NOT EXISTS idx_alt_ticker_type
    ON alt_data (ticker, data_type, date);
CREATE INDEX IF NOT EXISTS idx_alt_date
    ON alt_data (date);

-- ============================================================
-- Platform: Chat Sessions
-- ============================================================

-- chat_sessions: persisted chat history with visibility (insert-only, no hard deletes)
CREATE TABLE IF NOT EXISTS chat_sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL,
    title       TEXT,
    visibility  TEXT NOT NULL DEFAULT 'private'
                CHECK (visibility IN ('private', 'public')),
    messages    JSONB,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_sess_user
    ON chat_sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_chat_sess_visibility
    ON chat_sessions (visibility);
CREATE INDEX IF NOT EXISTS idx_chat_sess_created
    ON chat_sessions (created_at);

-- ============================================================
-- Seed: workflow_registry initial rows
-- ============================================================

INSERT INTO workflow_registry (workflow_name, display_name, description, required_inputs, output_table, trigger_type, schedule_rule)
VALUES
    ('earnings_preview',
     'Earnings Preview',
     'Full pre-earnings briefing covering estimates, actuals, price, portfolio position, and alt data signals',
     '{"ticker": "required", "reporting_period": "required", "forward_period": "required"}'::jsonb,
     'workflow_outputs_earnings_preview',
     'both',
     '7 days before earnings_calendar.report_date for all portfolio tickers'),
    ('financial_model_generation',
     'Financial Model Generation',
     'Generate a standardized 3-statement financial model following the canonical template',
     '{"ticker": "required", "key_kpis": "required"}'::jsonb,
     'workflow_outputs_financial_model',
     'on_demand',
     NULL)
ON CONFLICT (workflow_name) DO NOTHING;
"""

NEW_TABLES = [
    "analyst_notes",
    "buyside_notes",
    "sellside_notes",
    "sellside_estimates",
    "guidance",
    "internal_estimates",
    "buyside_estimates",
    "consensus_estimates",
    "trade_requests",
    "daily_pnl",
    "portfolio_concentration",
    "portfolio_risk",
    "model_outputs",
    "model_peers",
    "workflow_registry",
    "workflow_runs",
    "workflow_outputs_earnings_preview",
    "workflow_outputs_financial_model",
    "alt_data",
    "chat_sessions",
]


def main():
    parser = argparse.ArgumentParser(description="Create new domain tables")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print SQL without executing")
    args = parser.parse_args()

    if args.dry_run:
        print("=== DRY RUN — SQL that would be executed ===\n")
        print(MIGRATION_SQL)
        return

    if psycopg2 is None:
        print("ERROR: psycopg2 is required. Install via: pip install psycopg2-binary")
        sys.exit(1)

    print("Connecting to Supabase...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    # Check which tables already exist
    cur.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """)
    existing = {row[0] for row in cur.fetchall()}

    already = [t for t in NEW_TABLES if t in existing]
    needed = [t for t in NEW_TABLES if t not in existing]

    if already:
        print(f"Tables already exist (will be skipped by IF NOT EXISTS): "
              f"{', '.join(already)}")
    print(f"Tables to create: {', '.join(needed) if needed else '(all exist)'}")

    print("\nRunning migration SQL...")
    cur.execute(MIGRATION_SQL)
    print("Migration SQL executed successfully.")

    # Verify
    cur.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """)
    post_tables = {row[0] for row in cur.fetchall()}

    print(f"\nVerification — new tables:")
    for t in NEW_TABLES:
        status = "OK" if t in post_tables else "MISSING"
        print(f"  {t} — {status}")

    missing = [t for t in NEW_TABLES if t not in post_tables]
    if missing:
        print(f"\nERROR: Missing tables after migration: {missing}")
        sys.exit(1)
    else:
        print(f"\nAll {len(NEW_TABLES)} new tables verified.")

    # Verify seed data
    cur.execute("SELECT COUNT(*) FROM workflow_registry;")
    print(f"workflow_registry rows: {cur.fetchone()[0]}")

    cur.close()
    conn.close()
    print("\nMigration complete.")


if __name__ == "__main__":
    main()
