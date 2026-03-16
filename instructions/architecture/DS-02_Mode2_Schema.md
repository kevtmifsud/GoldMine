# DS-02: Mode 2 Database Schema

## Purpose

This document defines all Supabase tables required for Mode 2. These tables are created once and sit alongside the Mode 1 tables defined in WF-00. All Mode 2 application data — conversations, messages, Q&A library, insights, sharing, user lists, cost tracking, and model configuration — lives here.

---

## Schema Overview

```
auth.users                  ← Supabase Auth managed, do not create manually
user_profiles               ← extended user metadata
user_ticker_lists           ← analyst-defined ticker groups
conversations               ← top-level research threads
sessions                    ← chat threads within a conversation
messages                    ← individual turns: question + answer + sources
message_feedback            ← thumbs up/down/flag/edit + issue reporting per message
feature_requests            ← /request slash command submissions from analysts
qa_library                  ← validated Q&A entries with embeddings
insights                    ← user-saved moments from sessions
insight_shares              ← sharing records for insights
conversation_shares         ← sharing records for conversations
screening_cache             ← cached screening query results (24hr TTL)
api_cost_events             ← per-call cost and model tracking log
api_pricing                 ← current and historical pricing per model
model_config                ← active model assignments per component
```

---

## Table Definitions

Run all of the following in the Supabase SQL Editor in order.

### User Profiles

Extends Supabase Auth with app-specific user metadata. Created automatically when a new user signs up via a Supabase Auth trigger.

```sql
CREATE TABLE user_profiles (
    user_id         UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    display_name    TEXT,
    role            VARCHAR(50) DEFAULT 'analyst',
    is_admin        BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);
```

---

### User Ticker Lists

Stores analyst-defined ticker groups. System-defined groups (sectors, industries) are derived from the `tickers` table in DS-01 and do not live here.

```sql
CREATE TABLE user_ticker_lists (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    list_name       TEXT NOT NULL,
    ticker          VARCHAR(20) NOT NULL,
    created_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE (user_id, list_name, ticker)
);

CREATE INDEX idx_lists_user_id   ON user_ticker_lists (user_id);
CREATE INDEX idx_lists_name      ON user_ticker_lists (user_id, list_name);
```

---

### Conversations

Top-level container for a research thread. A conversation may contain multiple sessions over time about the same topic or ticker focus.

```sql
CREATE TABLE conversations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title           TEXT,
    ticker_context  VARCHAR(20),
    is_archived     BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_conversations_user     ON conversations (user_id);
CREATE INDEX idx_conversations_ticker   ON conversations (ticker_context);
```

---

### Sessions

Individual chat threads within a conversation. Each page load or new chat interaction creates a new session. The rolling summary is stored here and updated asynchronously.

```sql
CREATE TABLE sessions (
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

CREATE INDEX idx_sessions_conversation  ON sessions (conversation_id);
CREATE INDEX idx_sessions_user          ON sessions (user_id);
```

---

### Messages

Every turn in a session — user question and assistant response. Source chunks used are stored as JSONB so they can be rendered as citations in Goldmine without additional queries.

```sql
CREATE TABLE messages (
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

CREATE INDEX idx_messages_session   ON messages (session_id);
CREATE INDEX idx_messages_user      ON messages (user_id);
CREATE INDEX idx_messages_created   ON messages (created_at);
```

---

### Message Feedback

Analyst ratings and corrections on assistant messages. Includes structured issue reporting for flagged responses. Multiple feedback records per message are allowed (e.g. thumbs up from one analyst, edit from another on a shared conversation).

```sql
CREATE TABLE message_feedback (
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

CREATE INDEX idx_feedback_message       ON message_feedback (message_id);
CREATE INDEX idx_feedback_type          ON message_feedback (feedback_type);
CREATE INDEX idx_feedback_issue_status  ON message_feedback (issue_status)
    WHERE feedback_type = 'flagged';
```

`issue_notes` is populated when `feedback_type = 'flagged'` and captures the analyst's description of what was wrong. `issue_status`, `priority`, `resolved_by`, `resolved_at`, and `resolution_notes` are only relevant for flagged feedback and are managed by the technical lead via the admin issues endpoint.

---

### Feature Requests

Captures `/request` slash command submissions from analysts. Written directly without LLM involvement — one database write, one acknowledgment response. Serves as a running log of analyst-requested features for product prioritization.

```sql
CREATE TABLE feature_requests (
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

CREATE INDEX idx_feature_requests_user      ON feature_requests (user_id);
CREATE INDEX idx_feature_requests_status    ON feature_requests (status);
CREATE INDEX idx_feature_requests_created   ON feature_requests (created_at);
```

---

### Q&A Library

Validated question-answer pairs that the retrieval layer surfaces as prior institutional knowledge. Only entries with positive feedback enter the active library. The question embedding enables semantic similarity search.

```sql
CREATE TABLE qa_library (
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

CREATE INDEX idx_qa_tickers     ON qa_library USING GIN (tickers_referenced);
CREATE INDEX idx_qa_query_type  ON qa_library (query_type);
CREATE INDEX idx_qa_active      ON qa_library (validation_type) WHERE validation_type IS NOT NULL;

-- Create after initial library has entries:
-- CREATE INDEX idx_qa_embedding ON qa_library
--     USING ivfflat (question_embedding vector_cosine_ops) WITH (lists = 50);
```

Note: `validation_weight` is 1.0 for thumbs-up entries and 1.5 for edited-and-approved entries, reflecting higher confidence in manually corrected answers.

---

### Insights

User-saved moments from sessions — specific answers or passages an analyst wants to reference later.

```sql
CREATE TABLE insights (
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

CREATE INDEX idx_insights_user      ON insights (user_id);
CREATE INDEX idx_insights_ticker    ON insights (ticker_context);
```

---

### Conversation Shares

```sql
CREATE TABLE conversation_shares (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id     UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    shared_by           UUID NOT NULL REFERENCES auth.users(id),
    shared_with         UUID REFERENCES auth.users(id),
    share_with_team     BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMP DEFAULT NOW(),
    UNIQUE (conversation_id, shared_with)
);
```

---

### Insight Shares

```sql
CREATE TABLE insight_shares (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    insight_id      UUID NOT NULL REFERENCES insights(id) ON DELETE CASCADE,
    shared_by       UUID NOT NULL REFERENCES auth.users(id),
    shared_with     UUID REFERENCES auth.users(id),
    share_with_team BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE (insight_id, shared_with)
);
```

---

### Screening Cache

Caches results of broad screening queries for 24 hours. Prevents re-running expensive multi-ticker retrievals when multiple analysts ask similar screening questions on the same day.

```sql
CREATE TABLE screening_cache (
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

CREATE INDEX idx_cache_hash     ON screening_cache (query_hash);
CREATE INDEX idx_cache_expires  ON screening_cache (expires_at);

-- Create after initial cache entries exist:
-- CREATE INDEX idx_cache_embedding ON screening_cache
--     USING ivfflat (query_embedding vector_cosine_ops) WITH (lists = 50);
```

---

### API Cost Events

Per-call cost and model tracking log. Written asynchronously after every LLM or embedding API call across both Mode 1 and Mode 2. Never blocks a user-facing response.

```sql
CREATE TABLE api_cost_events (
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

CREATE INDEX idx_cost_mode          ON api_cost_events (mode);
CREATE INDEX idx_cost_user          ON api_cost_events (user_id);
CREATE INDEX idx_cost_model         ON api_cost_events (model);
CREATE INDEX idx_cost_component     ON api_cost_events (component);
CREATE INDEX idx_cost_created       ON api_cost_events (created_at);
CREATE INDEX idx_cost_query_type    ON api_cost_events (query_type);
```

---

### API Pricing

Stores current and historical pricing per model. Model selection and cost calculation reference this table. Update this table when providers change pricing — never hardcode token prices in application code.

```sql
CREATE TABLE api_pricing (
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

CREATE INDEX idx_pricing_model      ON api_pricing (model);
CREATE INDEX idx_pricing_current    ON api_pricing (is_current);
```

**Seed with current pricing:**

```sql
INSERT INTO api_pricing (model, provider, input_per_1m, output_per_1m, effective_from, is_current) VALUES
('claude-haiku-4-5-20251001',    'anthropic', 0.80,   4.00,  '2025-01-01', TRUE),
('claude-sonnet-4-6',            'anthropic', 3.00,  15.00,  '2025-01-01', TRUE),
('text-embedding-3-large-1536',  'openai',    0.065,  NULL,  '2025-01-01', TRUE);
```

---

### Model Config

Controls which model is used for each pipeline component. Changing a model across the entire platform requires updating one row here — no code changes, no redeployment. Each component reads its assigned model at runtime.

```sql
CREATE TABLE model_config (
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
```

**Seed with initial model assignments:**

```sql
INSERT INTO model_config (component, model, provider, mode, description) VALUES
('document_classifier',     'claude-haiku-4-5-20251001',   'anthropic', 'mode_1', 'Classifies document type in WF-02'),
('query_classifier',        'claude-haiku-4-5-20251001',   'anthropic', 'mode_2', 'Classifies user query type in WF-06'),
('response_generator',      'claude-sonnet-4-6',           'anthropic', 'mode_2', 'Generates final user-facing answers in WF-09'),
('screening_prefilter',     'claude-haiku-4-5-20251001',   'anthropic', 'mode_2', 'Pre-filters chunks for screening queries in WF-08'),
('session_compressor',      'claude-haiku-4-5-20251001',   'anthropic', 'mode_2', 'Compresses session history in WF-10'),
('query_embedder',          'text-embedding-3-large-1536', 'openai',    'mode_2', 'Embeds user queries for vector search'),
('document_embedder',       'text-embedding-3-large-1536', 'openai',    'mode_1', 'Embeds document chunks in WF-04'),
('qa_library_embedder',     'text-embedding-3-large-1536', 'openai',    'mode_2', 'Embeds questions for Q&A library');
```

---

## Updating a Model Assignment

When a new model is released and you want to switch a component:

```sql
UPDATE model_config
SET
    previous_model  = model,
    model           = 'claude-new-model-identifier',
    switched_at     = NOW(),
    updated_at      = NOW()
WHERE component = 'response_generator';

-- Also add the new model to api_pricing:
UPDATE api_pricing SET is_current = FALSE, effective_to = CURRENT_DATE
WHERE model = 'claude-sonnet-4-6';

INSERT INTO api_pricing (model, provider, input_per_1m, output_per_1m, effective_from, is_current)
VALUES ('claude-new-model-identifier', 'anthropic', X.XX, X.XX, CURRENT_DATE, TRUE);
```

The platform reads model assignments at runtime on every API call — the switch takes effect immediately with no redeployment required.
