"""
Initialize all Supabase tables for the Portfolio Intelligence Platform.
Runs WF-00 (infrastructure), DS-01 (structured financial), and DS-02 (Mode 2) schemas.
"""
import psycopg2

DATABASE_URL = "postgresql://postgres:sC.g6Wf#9h.Bf_f@db.ybjvfeevaxujenwvoewg.supabase.co:5432/postgres"

SCHEMA_SQL = """
-- ============================================================
-- 0. Enable pgvector
-- ============================================================
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- WF-00: Infrastructure tables
-- ============================================================

-- Processing Registry
CREATE TABLE IF NOT EXISTS processing_registry (
    document_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker                VARCHAR(20) NOT NULL,
    document_type         VARCHAR(50),
    file_path             TEXT NOT NULL UNIQUE,
    file_hash             VARCHAR(64) NOT NULL,
    first_processed_at    TIMESTAMP,
    last_processed_at     TIMESTAMP,
    processing_status     VARCHAR(20) DEFAULT 'pending'
                          CHECK (processing_status IN
                          ('pending','processing','complete','failed','archived')),
    worker_id             VARCHAR(100),
    processing_started_at TIMESTAMP,
    chunk_count           INTEGER,
    classification_method VARCHAR(20),
    error_message         TEXT,
    created_at            TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_registry_status ON processing_registry (processing_status);
CREATE INDEX IF NOT EXISTS idx_registry_ticker ON processing_registry (ticker);
CREATE INDEX IF NOT EXISTS idx_registry_hash   ON processing_registry (file_hash);

-- Chunks + Embeddings (1536 dims per WF-04 recommendation)
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES processing_registry(document_id),
    ticker          VARCHAR(20) NOT NULL,
    document_type   VARCHAR(50),
    section_name    TEXT,
    section_type    VARCHAR(50),
    fiscal_period   VARCHAR(20),
    filing_date     DATE,
    chunk_sequence  INTEGER,
    page_reference  INTEGER,
    word_count      INTEGER,
    chunk_text      TEXT NOT NULL,
    embedding       vector(1536),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chunks_ticker        ON chunks (ticker);
CREATE INDEX IF NOT EXISTS idx_chunks_document_id   ON chunks (document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_document_type ON chunks (document_type);
CREATE INDEX IF NOT EXISTS idx_chunks_section_type  ON chunks (section_type);
CREATE INDEX IF NOT EXISTS idx_chunks_filing_date   ON chunks (filing_date);
CREATE INDEX IF NOT EXISTS idx_chunks_active        ON chunks (is_active);
CREATE INDEX IF NOT EXISTS idx_chunks_ticker_type   ON chunks (ticker, document_type, filing_date);

-- Pipeline Run Logs
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_started_at       TIMESTAMP DEFAULT NOW(),
    run_completed_at     TIMESTAMP,
    run_type             VARCHAR(20) DEFAULT 'incremental'
                         CHECK (run_type IN ('incremental','full')),
    documents_scanned    INTEGER,
    documents_queued     INTEGER,
    documents_succeeded  INTEGER,
    documents_failed     INTEGER,
    chunks_generated     INTEGER,
    estimated_cost_usd   NUMERIC(10,4),
    run_duration_seconds INTEGER,
    status               VARCHAR(20) DEFAULT 'running'
                         CHECK (status IN ('running','complete','failed')),
    notes                TEXT
);

-- ============================================================
-- DS-01: Structured Financial Data tables
-- ============================================================

-- stocks (primary structured data table — replaces old tickers table)
CREATE TABLE IF NOT EXISTS stocks (
    ticker              VARCHAR(20) PRIMARY KEY,
    company_name        TEXT,
    sector              VARCHAR(100),
    industry            VARCHAR(200),
    market_cap_b        VARCHAR(20),
    pe_ratio            VARCHAR(20),
    price               VARCHAR(20),
    "52w_high"          VARCHAR(20),
    "52w_low"           VARCHAR(20),
    dividend_yield      VARCHAR(20),
    eps                 VARCHAR(20),
    revenue_b           VARCHAR(20),
    country             VARCHAR(50),
    exchange            VARCHAR(50),
    address             TEXT,
    city                VARCHAR(100),
    phone               VARCHAR(50),
    zip                 VARCHAR(20),
    long_business_summary TEXT,
    full_time_employees VARCHAR(20),
    web_site            TEXT,
    report_date         VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS people (
    person_id           VARCHAR(20) PRIMARY KEY,
    name                TEXT,
    title               TEXT,
    organization        TEXT,
    type                VARCHAR(50),
    tickers             TEXT,
    age                 VARCHAR(10),
    born                VARCHAR(20),
    pay                 VARCHAR(30),
    exercised           VARCHAR(30),
    unexercised         VARCHAR(30)
);

CREATE TABLE IF NOT EXISTS portfolios (
    portfolio_id        VARCHAR(20) PRIMARY KEY,
    name                VARCHAR(100),
    strategy            TEXT,
    aum                 VARCHAR(30),
    long_exposure       VARCHAR(30),
    short_exposure      VARCHAR(30),
    num_positions       VARCHAR(10),
    max_position_pct    VARCHAR(10),
    inception_date      VARCHAR(20),
    rebalance_frequency VARCHAR(50),
    total_trades        VARCHAR(10),
    unique_tickers      VARCHAR(10),
    status              VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS portfolio_trades (
    date                VARCHAR(20) NOT NULL,
    ticker              VARCHAR(20) NOT NULL,
    action              VARCHAR(10) NOT NULL,
    shares              VARCHAR(20),
    price               VARCHAR(20),
    portfolio           VARCHAR(100) NOT NULL,
    side                VARCHAR(10),
    PRIMARY KEY (date, ticker, portfolio, action)
);
CREATE INDEX IF NOT EXISTS idx_pt_ticker ON portfolio_trades (ticker);
CREATE INDEX IF NOT EXISTS idx_pt_portfolio ON portfolio_trades (portfolio);
CREATE INDEX IF NOT EXISTS idx_pt_date ON portfolio_trades (date);

CREATE TABLE IF NOT EXISTS stock_history (
    date                VARCHAR(20) NOT NULL,
    ticker              VARCHAR(20) NOT NULL,
    close               VARCHAR(20),
    eps_estimate        VARCHAR(20),
    eps_actual          VARCHAR(20),
    PRIMARY KEY (date, ticker)
);
CREATE INDEX IF NOT EXISTS idx_sh_ticker ON stock_history (ticker);
CREATE INDEX IF NOT EXISTS idx_sh_date ON stock_history (date);

CREATE TABLE IF NOT EXISTS stock_betas (
    ticker              VARCHAR(20) PRIMARY KEY,
    beta                VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS earnings_calendar (
    ticker              VARCHAR(20) NOT NULL,
    report_date         VARCHAR(20) NOT NULL,
    time                VARCHAR(20),
    fiscal_quarter_ending VARCHAR(20),
    PRIMARY KEY (ticker, report_date)
);

CREATE TABLE IF NOT EXISTS sec_filings (
    accession_number    VARCHAR(50) PRIMARY KEY,
    symbol              VARCHAR(20),
    cik                 VARCHAR(20),
    company_name        TEXT,
    form_type           VARCHAR(20),
    form_type_description TEXT,
    filing_date         VARCHAR(20),
    report_date         VARCHAR(20),
    acceptance_date_time TEXT,
    filing_url          TEXT,
    primary_document    TEXT
);
CREATE INDEX IF NOT EXISTS idx_sf_symbol ON sec_filings (symbol);

CREATE TABLE IF NOT EXISTS transcripts_list (
    transcripts_id      VARCHAR(100) PRIMARY KEY,
    symbol              VARCHAR(20),
    fiscal_year         VARCHAR(10),
    fiscal_quarter      VARCHAR(10),
    report_date         VARCHAR(20),
    transcripts         TEXT
);
CREATE INDEX IF NOT EXISTS idx_tl_symbol ON transcripts_list (symbol);

CREATE TABLE IF NOT EXISTS financial_metrics (
    ticker       VARCHAR(20) NOT NULL,
    metric_name  VARCHAR(100) NOT NULL,
    period_end   DATE NOT NULL,
    period_type  VARCHAR(10) CHECK (period_type IN ('quarterly', 'annual')),
    value        NUMERIC,
    created_at   TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (ticker, metric_name, period_end, period_type)
);

CREATE INDEX IF NOT EXISTS idx_fm_ticker ON financial_metrics (ticker);
CREATE INDEX IF NOT EXISTS idx_fm_ticker_period ON financial_metrics (ticker, period_type);
CREATE INDEX IF NOT EXISTS idx_fm_ticker_metric ON financial_metrics (ticker, metric_name);

-- ============================================================
-- DS-02: Mode 2 tables
-- ============================================================

-- User Profiles
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id         UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    display_name    TEXT,
    role            VARCHAR(50) DEFAULT 'analyst',
    is_admin        BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

-- User Ticker Lists
CREATE TABLE IF NOT EXISTS user_ticker_lists (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    list_name       TEXT NOT NULL,
    ticker          VARCHAR(20) NOT NULL,
    created_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE (user_id, list_name, ticker)
);

CREATE INDEX IF NOT EXISTS idx_lists_user_id ON user_ticker_lists (user_id);
CREATE INDEX IF NOT EXISTS idx_lists_name    ON user_ticker_lists (user_id, list_name);

-- Conversations
CREATE TABLE IF NOT EXISTS conversations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title           TEXT,
    ticker_context  VARCHAR(20),
    is_archived     BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversations_user   ON conversations (user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_ticker ON conversations (ticker_context);

-- Sessions
CREATE TABLE IF NOT EXISTS sessions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id     UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_id             UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    rolling_summary     TEXT,
    summary_covers_through INTEGER DEFAULT 0,
    turn_count          INTEGER DEFAULT 0,
    total_input_tokens  INTEGER DEFAULT 0,
    total_output_tokens INTEGER DEFAULT 0,
    total_cost_usd      NUMERIC(10,6) DEFAULT 0,
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_conversation ON sessions (conversation_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user         ON sessions (user_id);

-- Messages
CREATE TABLE IF NOT EXISTS messages (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id          UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    user_id             UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    role                VARCHAR(20) CHECK (role IN ('user', 'assistant')),
    content             TEXT NOT NULL,
    query_type          VARCHAR(50),
    tickers_referenced  TEXT[],
    source_chunks       JSONB,
    qa_library_hits     JSONB,
    classifier_model    VARCHAR(100),
    generator_model     VARCHAR(100),
    input_tokens        INTEGER,
    output_tokens       INTEGER,
    cost_usd            NUMERIC(10,6),
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages (session_id);
CREATE INDEX IF NOT EXISTS idx_messages_user    ON messages (user_id);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages (created_at);

-- Message Feedback
CREATE TABLE IF NOT EXISTS message_feedback (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id      UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    feedback_type   VARCHAR(20) CHECK (feedback_type IN
                    ('thumbs_up', 'thumbs_down', 'flagged', 'edited')),
    edited_content  TEXT,
    issue_notes     TEXT,
    issue_status    VARCHAR(20) DEFAULT 'open'
                    CHECK (issue_status IN ('open', 'triaging', 'resolved')),
    priority        VARCHAR(10) DEFAULT 'medium'
                    CHECK (priority IN ('low', 'medium', 'high')),
    resolved_by     UUID REFERENCES auth.users(id),
    resolved_at     TIMESTAMP,
    resolution_notes TEXT,
    created_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE (message_id, user_id, feedback_type)
);

CREATE INDEX IF NOT EXISTS idx_feedback_message      ON message_feedback (message_id);
CREATE INDEX IF NOT EXISTS idx_feedback_type         ON message_feedback (feedback_type);
CREATE INDEX IF NOT EXISTS idx_feedback_issue_status ON message_feedback (issue_status)
    WHERE feedback_type = 'flagged';

-- Feature Requests
CREATE TABLE IF NOT EXISTS feature_requests (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    session_id      UUID REFERENCES sessions(id),
    request_text    TEXT NOT NULL,
    status          VARCHAR(20) DEFAULT 'submitted'
                    CHECK (status IN ('submitted', 'reviewing', 'planned', 'declined', 'completed')),
    priority        VARCHAR(10)
                    CHECK (priority IN ('low', 'medium', 'high')),
    admin_notes     TEXT,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_feature_requests_user    ON feature_requests (user_id);
CREATE INDEX IF NOT EXISTS idx_feature_requests_status  ON feature_requests (status);
CREATE INDEX IF NOT EXISTS idx_feature_requests_created ON feature_requests (created_at);

-- Q&A Library
CREATE TABLE IF NOT EXISTS qa_library (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id          UUID REFERENCES messages(id),
    user_id             UUID REFERENCES auth.users(id),
    question            TEXT NOT NULL,
    answer              TEXT NOT NULL,
    question_embedding  vector(1536),
    source_chunks       JSONB,
    tickers_referenced  TEXT[],
    query_type          VARCHAR(50),
    fiscal_periods      TEXT[],
    validation_type     VARCHAR(20) CHECK (validation_type IN
                        ('thumbs_up', 'edited_approved')),
    validation_weight   NUMERIC(3,2) DEFAULT 1.0,
    use_count           INTEGER DEFAULT 0,
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_qa_tickers    ON qa_library USING GIN (tickers_referenced);
CREATE INDEX IF NOT EXISTS idx_qa_query_type ON qa_library (query_type);
CREATE INDEX IF NOT EXISTS idx_qa_active     ON qa_library (validation_type) WHERE validation_type IS NOT NULL;

-- Insights
CREATE TABLE IF NOT EXISTS insights (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    message_id      UUID REFERENCES messages(id),
    session_id      UUID REFERENCES sessions(id),
    title           TEXT,
    content         TEXT NOT NULL,
    ticker_context  VARCHAR(20),
    tags            TEXT[],
    is_private      BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_insights_user   ON insights (user_id);
CREATE INDEX IF NOT EXISTS idx_insights_ticker ON insights (ticker_context);

-- Conversation Shares
CREATE TABLE IF NOT EXISTS conversation_shares (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id     UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    shared_by           UUID NOT NULL REFERENCES auth.users(id),
    shared_with         UUID REFERENCES auth.users(id),
    share_with_team     BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMP DEFAULT NOW(),
    UNIQUE (conversation_id, shared_with)
);

-- Insight Shares
CREATE TABLE IF NOT EXISTS insight_shares (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    insight_id      UUID NOT NULL REFERENCES insights(id) ON DELETE CASCADE,
    shared_by       UUID NOT NULL REFERENCES auth.users(id),
    shared_with     UUID REFERENCES auth.users(id),
    share_with_team BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE (insight_id, shared_with)
);

-- Screening Cache
CREATE TABLE IF NOT EXISTS screening_cache (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_embedding     vector(1536),
    query_text          TEXT NOT NULL,
    query_hash          VARCHAR(64) NOT NULL,
    result_content      TEXT NOT NULL,
    source_chunks       JSONB,
    tickers_covered     TEXT[],
    fiscal_period       VARCHAR(20),
    model_used          VARCHAR(100),
    hit_count           INTEGER DEFAULT 0,
    created_at          TIMESTAMP DEFAULT NOW(),
    expires_at          TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cache_hash    ON screening_cache (query_hash);
CREATE INDEX IF NOT EXISTS idx_cache_expires ON screening_cache (expires_at);

-- API Cost Events
CREATE TABLE IF NOT EXISTS api_cost_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mode            VARCHAR(10) CHECK (mode IN ('mode_1', 'mode_2')),
    component       VARCHAR(50),
    model           VARCHAR(100) NOT NULL,
    input_tokens    INTEGER DEFAULT 0,
    output_tokens   INTEGER DEFAULT 0,
    cost_usd        NUMERIC(10,6) NOT NULL,
    user_id         UUID REFERENCES auth.users(id),
    session_id      UUID REFERENCES sessions(id),
    message_id      UUID REFERENCES messages(id),
    query_type      VARCHAR(50),
    ticker_count    INTEGER,
    document_id     UUID REFERENCES processing_registry(document_id),
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cost_mode       ON api_cost_events (mode);
CREATE INDEX IF NOT EXISTS idx_cost_user       ON api_cost_events (user_id);
CREATE INDEX IF NOT EXISTS idx_cost_model      ON api_cost_events (model);
CREATE INDEX IF NOT EXISTS idx_cost_component  ON api_cost_events (component);
CREATE INDEX IF NOT EXISTS idx_cost_created    ON api_cost_events (created_at);
CREATE INDEX IF NOT EXISTS idx_cost_query_type ON api_cost_events (query_type);

-- API Pricing
CREATE TABLE IF NOT EXISTS api_pricing (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model           VARCHAR(100) NOT NULL,
    provider        VARCHAR(50) NOT NULL,
    input_per_1m    NUMERIC(10,6) NOT NULL,
    output_per_1m   NUMERIC(10,6),
    effective_from  DATE NOT NULL,
    effective_to    DATE,
    is_current      BOOLEAN DEFAULT TRUE,
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS idx_pricing_model   ON api_pricing (model);
CREATE INDEX IF NOT EXISTS idx_pricing_current ON api_pricing (is_current);

-- Model Config
CREATE TABLE IF NOT EXISTS model_config (
    component           VARCHAR(100) PRIMARY KEY,
    model               VARCHAR(100) NOT NULL,
    provider            VARCHAR(50) NOT NULL,
    mode                VARCHAR(10) CHECK (mode IN ('mode_1', 'mode_2', 'both')),
    description         TEXT,
    updated_at          TIMESTAMP DEFAULT NOW(),
    updated_by          UUID REFERENCES auth.users(id),
    previous_model      VARCHAR(100),
    switched_at         TIMESTAMP
);

-- LLM Bug Reports
CREATE TABLE IF NOT EXISTS llm_bug_reports (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id     UUID REFERENCES conversations(id),
    session_id          UUID REFERENCES sessions(id),
    message_id          UUID,
    user_id             VARCHAR(100) NOT NULL,
    category            VARCHAR(50) NOT NULL,
    description         TEXT,
    user_query          TEXT NOT NULL,
    llm_response        TEXT NOT NULL,
    error_message       TEXT,
    tickers_referenced  TEXT[],
    query_type          VARCHAR(100),
    status              VARCHAR(30) DEFAULT 'new',
    resolution          TEXT,
    created_at          TIMESTAMP DEFAULT NOW(),
    resolved_at         TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_llm_bugs_status ON llm_bug_reports (status);
CREATE INDEX IF NOT EXISTS idx_llm_bugs_category ON llm_bug_reports (category);
CREATE INDEX IF NOT EXISTS idx_llm_bugs_created ON llm_bug_reports (created_at DESC);

-- ============================================================
-- Seed data
-- ============================================================

-- API Pricing seed
INSERT INTO api_pricing (model, provider, input_per_1m, output_per_1m, effective_from, is_current)
VALUES
    ('claude-haiku-4-5-20251001',    'anthropic', 0.80,   4.00,  '2025-01-01', TRUE),
    ('claude-sonnet-4-6',            'anthropic', 3.00,  15.00,  '2025-01-01', TRUE),
    ('text-embedding-3-large-1536',  'openai',    0.065,  NULL,  '2025-01-01', TRUE)
ON CONFLICT DO NOTHING;

-- Model Config seed
INSERT INTO model_config (component, model, provider, mode, description)
VALUES
    ('document_classifier',  'claude-haiku-4-5-20251001',   'anthropic', 'mode_1', 'Classifies document type in WF-02'),
    ('query_classifier',     'claude-haiku-4-5-20251001',   'anthropic', 'mode_2', 'Classifies user query type in WF-06'),
    ('response_generator',   'claude-sonnet-4-6',           'anthropic', 'mode_2', 'Generates final user-facing answers in WF-09'),
    ('screening_prefilter',  'claude-haiku-4-5-20251001',   'anthropic', 'mode_2', 'Pre-filters chunks for screening queries in WF-08'),
    ('session_compressor',   'claude-haiku-4-5-20251001',   'anthropic', 'mode_2', 'Compresses session history in WF-10'),
    ('query_embedder',       'text-embedding-3-large-1536', 'openai',    'mode_2', 'Embeds user queries for vector search'),
    ('document_embedder',    'text-embedding-3-large-1536', 'openai',    'mode_1', 'Embeds document chunks in WF-04'),
    ('qa_library_embedder',  'text-embedding-3-large-1536', 'openai',    'mode_2', 'Embeds questions for Q&A library')
ON CONFLICT DO NOTHING;
"""


def main():
    print("Connecting to Supabase...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    print("Running schema SQL...")
    cur.execute(SCHEMA_SQL)
    print("Schema SQL executed successfully.")

    # Verify all tables exist
    cur.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """)
    tables = [row[0] for row in cur.fetchall()]

    expected = [
        "api_cost_events", "api_pricing",
        "chunks", "conversation_shares", "conversations",
        "earnings_calendar", "feature_requests", "financial_metrics",
        "insight_shares", "insights", "message_feedback", "messages",
        "model_config", "people", "pipeline_runs", "portfolios",
        "portfolio_trades", "processing_registry", "qa_library",
        "screening_cache", "sec_filings", "sessions", "stocks",
        "stock_betas", "stock_history", "transcripts_list",
        "user_profiles", "user_ticker_lists",
    ]

    print(f"\nTables found in public schema: {len(tables)}")
    for t in tables:
        marker = "OK" if t in expected else "  (extra)"
        print(f"  {t} — {marker}")

    missing = [t for t in expected if t not in tables]
    if missing:
        print(f"\nMISSING tables: {missing}")
    else:
        print(f"\nAll {len(expected)} expected tables exist.")

    # Verify seed data
    cur.execute("SELECT COUNT(*) FROM api_pricing;")
    print(f"\napi_pricing rows: {cur.fetchone()[0]}")

    cur.execute("SELECT COUNT(*) FROM model_config;")
    print(f"model_config rows: {cur.fetchone()[0]}")

    # Verify pgvector
    cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector';")
    row = cur.fetchone()
    print(f"pgvector version: {row[0] if row else 'NOT INSTALLED'}")

    cur.close()
    conn.close()
    print("\nDone. Step 1 complete.")


if __name__ == "__main__":
    main()
