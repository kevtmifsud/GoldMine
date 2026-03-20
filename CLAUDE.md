# GoldMine

Investment Research CRM for Portfolio Managers and Research Analysts. Combines a data-grid CRM with an AI-powered chat interface backed by a financial document knowledge base.

## Guiding Principle: Design for Scale

Every piece of this application — database queries, backend jobs, API endpoints, frontend rendering — must be designed to handle production-scale data. If a script processes 2 tickers today, it must work correctly and efficiently for 2 million tickers. Concretely:

- **Database**: Use indexes, pagination, and batch operations. Never `SELECT *` without `LIMIT`. Assume tables will have millions of rows.
- **Backend jobs & scripts**: Process data in batches/streams, not all-in-memory. Use cursors for large result sets. Add progress logging for long-running operations.
- **API endpoints**: Paginate list responses. Avoid N+1 queries. Use bulk endpoints where clients need multiple records.
- **Frontend**: Virtualize long lists (AG Grid already does this). Don't fetch unbounded data — always paginate or limit. Assume any list could have thousands of items.
- **General**: Prefer `INSERT ... ON CONFLICT` over check-then-insert. Use connection pooling. Design data models with partitioning and archival in mind. Never hardcode limits that will break at scale.

This is a reliability-first system for institutional users. When choosing between simplicity and scalability, choose scalability.

## Quick Start

```bash
# Start both servers
./scripts/dev_start.sh

# Or individually:
# Backend (port 8000)
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000

# Frontend (port 5173)
cd frontend && npm run dev
```

## Tech Stack

- **Backend**: Python 3.12+, FastAPI, Pydantic v2, structlog
- **Frontend**: React 18, TypeScript (strict), Vite 6, react-router-dom v7
- **Database**: Supabase (PostgreSQL + pgvector)
  - `psycopg2` (sync) — data-access layer (`app/data_access/db.py`)
  - `asyncpg` (async) — Mode 2 chat + financials (`app/mode2/db.py`)
- **AI**: Anthropic Claude (chat), OpenAI embeddings (document pipeline)
- **UI Libraries**: AG Grid (data tables), ECharts (charts), react-markdown

## Project Structure

```
backend/
  app/
    api/            # REST endpoints (data, entities, documents, financials, etc.)
    auth/           # JWT auth with httpOnly cookies
    config/         # Pydantic Settings (env_prefix="GOLDMINE_")
    data_access/    # Pluggable data providers (supabase or csv)
    mode2/          # AI chat system: classifier → ticker resolver → retrieval → generator
    pipeline/       # Offline document ingestion (scan → classify → chunk → embed)
    documents/      # User-uploaded document management
    email/          # Email rendering + SMTP/console delivery
    reports/        # Report generation (daily P&L)
    views/          # Saved view persistence
    tests/          # pytest suite
  .env              # Environment config (see backend/.env.example)

frontend/
  src/
    config/         # API clients (api.ts base axios, mode2Api.ts, viewsApi.ts, etc.)
    types/          # Shared TypeScript interfaces
    hooks/          # Custom hooks (useMode2Chat, usePackEditor, etc.)
    pages/          # Page components, including stock/ subpages
    components/     # Reusable components (chat/, ag-grid/, research/, etc.)
    styles/         # Per-feature CSS files

data/               # Local data files (views, documents, schedules, unstructured)
scripts/            # Utility scripts (migrations, data generation, pipeline)
instructions/       # Architecture specs (WF-00 through WF-12, DS-01 through DS-04)
```

## Architecture: Two-Mode System

**Mode 1 — Document Processing Pipeline** (offline, batch)
- Scans transcripts/docs → classifies → chunks semantically → generates embeddings → stores in pgvector
- Run via: `python scripts/run_pipeline.py`

**Mode 2 — Interactive AI Chat** (online, streaming)
- Per message: classify query (Haiku) → resolve tickers → retrieve context (vector + SQL) → generate response (Sonnet, SSE streaming)
- Every claim must cite `[TICKER | DOC_TYPE | PERIOD | SECTION]`
- Conversations/sessions persisted in Supabase

## Running Tests

```bash
# Backend
cd backend && source .venv/bin/activate
pytest                          # all tests
pytest app/tests/test_auth.py   # single file

# Frontend
cd frontend
npm test                        # all tests (single run)
npm run test:watch              # watch mode during development
npm run test:coverage           # with coverage report

# Both suites
(cd backend && source .venv/bin/activate && pytest) && (cd frontend && npm test)
```

Backend test config in `backend/pyproject.toml`. Fixtures in `conftest.py` use temp directories for views/documents/schedules but do not override the data provider — tests use whichever provider your `.env` configures.

Frontend tests use vitest + @testing-library/react. Config in `vite.config.ts` (`test` block). Setup file: `src/test/setup.ts`.

**Before every commit or push**, run the relevant test suite(s). If frontend code changed, run `npm test` in `frontend/`. If backend code changed, run `pytest` in `backend/`. Do not commit or push with failing tests.

## Maintenance Policies

### Keeping CLAUDE.md Current

Update CLAUDE.md **in the same session** whenever:
- A new page or route is added → update Project Structure and/or relevant sections
- A new entity type is added → update Architecture section
- A new API endpoint group or backend module is added → update Project Structure
- A top-level directory is created → update Project Structure
- An architectural pattern changes → update relevant section
- Test commands change → update Running Tests section

### Testing Requirements

**Backend** — required for new API endpoints and new business logic functions.
- Pattern: async test functions, `authed_client` fixture, assert status code + response shape
- Location: `backend/app/tests/`

**Frontend** — required for:
- New utility functions in `src/utils/` → add `src/test/<name>.test.ts`
- New shared components in `src/components/` → add `src/test/<Name>.test.tsx`
- New page components in `src/pages/` → add `src/test/<PageName>.test.tsx` (at minimum a render smoke test)

Common mock patterns:
- `vi.mock("../auth/useAuth")` — mock auth context for components that use `useAuth()`
- `<MemoryRouter>` — wrap components that use react-router hooks/components
- `vi.mock("../config/api")` — mock axios instance for API calls

## Code Conventions

### Backend (Python)
- All files start with `from __future__ import annotations`
- Absolute imports: `from app.config.settings import settings`
- Pydantic models for all request/response shapes
- Factory pattern for pluggable providers (data, storage, email)
- Logging: `structlog` with keyword args — `logger.info("event_name", key=value)`
- Error hierarchy: `GoldMineError` → `AuthenticationError`, `DataAccessError`, `NotFoundError`
- File naming: `snake_case.py`

### Frontend (TypeScript/React)
- Functional components only, named exports: `export function MyComponent()`
- Component files: `PascalCase.tsx`; hooks/utils: `camelCase.ts`
- API clients in `src/config/` — axios for REST, raw `fetch()` for SSE streaming
- axios instance (`src/config/api.ts`) sets `withCredentials: true`; 401 → redirect to `/login`
- CSS in `src/styles/` by feature name
- TypeScript strict mode (noUnusedLocals, noUnusedParameters)

### Stock Entity Pages
- `StockEntityPage.tsx` provides layout with sidebar + `<Outlet>` for nested subpages
- Subpages access entity context via `useStockEntity()` (which wraps `useOutletContext`)
- Every stock subpage renders `<EmbeddedChat />` at the top (Mode 2 powered)

## Environment Variables

All backend settings use `GOLDMINE_` prefix. Key variables:

| Variable | Default | Description |
|---|---|---|
| `GOLDMINE_ENV` | `development` | Affects cookie security, log format |
| `GOLDMINE_DATA_PROVIDER` | `supabase` | `supabase` or `csv` |
| `GOLDMINE_ANTHROPIC_API_KEY` | — | Claude API key |
| `SUPABASE_DATABASE_URL` | — | PostgreSQL DSN (has special chars, use custom parser) |

See `backend/.env.example` for the full list.

## Database Notes

- The Supabase DSN password contains special characters (`#`). The project uses a custom regex parser in `app/mode2/db.py` (`_parse_dsn()`) — do not use `asyncpg.connect(dsn)` directly.
- Schema migrations are run manually via SQL or Python scripts in `scripts/`.
- Architecture docs in `instructions/architecture/` contain the authoritative schema definitions.

## Data Updates

Unified script: `scripts/update_all_data.py` — replaces both `update_fundamentals_data.py` and `update_fundamental_reports.py`.

```bash
# Weekly incremental (phases 1-9: prices, EPS, history, stocks, calendar,
# statements, beta, SEC filings, transcripts)
python scripts/update_all_data.py

# Full backfill from 2015
python scripts/update_all_data.py --full

# Also run monthly phases (company info + officers)
python scripts/update_all_data.py --include-profiles

# Single phase
python scripts/update_all_data.py --only prices
python scripts/update_all_data.py --only transcripts
python scripts/update_all_data.py --only filings
python scripts/update_all_data.py --only statements

# Options
python scripts/update_all_data.py --workers 20             # Thread pool size (default 10)
python scripts/update_all_data.py --fresh                  # Ignore all checkpoints
python scripts/update_all_data.py --start-date 2020-01-01  # Override history start
```

Key design decisions:
- **Bulk DuckDB queries** for all data phases: prices, EPS, calendar, statements, beta, SEC filings (`stock_sec_filing` parquet), and transcripts (`stock_earning_call_transcripts` parquet) — single query per data type instead of per-ticker API calls
- **Incremental by default** — queries DB for last-known dates, only fetches/upserts new data
- **All tickers** for filings + transcripts (no whitelist)
- **EDGAR enrichment** for SEC filings — sequential CIK lookups for `primary_document` field (rate-limited 0.15s)
- **Checkpoint/resume** for info + officers phases (per-ticker API calls)
- `--full` bypasses incremental bounds for initial backfill

Old scripts (`update_fundamentals_data.py`, `update_fundamental_reports.py`) kept as reference.

## Demo Users

| Username | Password | Role |
|---|---|---|
| `analyst1` | `analyst123` | Research Analyst |
| `analyst2` | `analyst456` | Research Analyst |
| `pm1` | `pm789` | Portfolio Manager |

Hardcoded in `backend/app/auth/users.py` (bcrypt hashed).
## Domain Knowledge & Business Rules

Architecture specs for the pipeline live in `instructions/architecture/` (WF-00 through WF-12, DS-01 through DS-04).

Business rules, data contracts, and domain specs live in `instructions/domain/`:

| File | What it covers |
|---|---|
| `instructions/domain/data-schema.md` | Every table: grain, columns, writer, chatbot access, insert policy |
| `instructions/domain/chatbot.md` | Routing rules, retrieval strategy, session rules, cost warning logic |
| `instructions/domain/workflows.md` | Workflow framework, earnings preview spec, model generation spec |
| `instructions/domain/portfolio.md` | Daily job sequence, derivative tables, market neutrality constraint |
| `instructions/domain/models.md` | Canonical Excel model template, processing job, versioning rules |

**When adding a new feature, check these files first.** They contain decisions that are not visible from the code — which table an output lands in, which sources the chatbot can and cannot query, what a workflow must produce to be considered complete.

## Database: New Tables (Not Yet Built)

The following tables have been designed but not yet migrated. Schema definitions are in `instructions/domain/data-schema.md`. Do not create ad-hoc schemas — use the specs there.

**Research & notes**
- `analyst_notes` — internal analyst research notes, insert-only, multi-ticker/sector scope
- `buyside_notes` — external buyside firm notes, ingested via vendor
- `sellside_notes` — sellside firm notes, ingested via vendor, chunked via pipeline
- `sellside_estimates` — structured estimates extracted from sellside notes
- `guidance` — company-issued forward guidance, manually entered until extraction is built

**Estimates (three separate tables, never mixed)**
- `internal_estimates` — our own forward estimates, PIT insert-only, powered by model processing job
- `buyside_estimates` — external buyside forward estimates, ingested daily
- `consensus_estimates` — street consensus estimates, ingested daily

**Portfolio & risk**
- `trade_requests` — PM trade requests, staging table before execution
- `daily_pnl` — pre-calculated daily P&L at position/side/sector/portfolio grain
- `portfolio_concentration` — daily concentration by sector/industry/geography/side
- `portfolio_risk` — daily beta exposures via `stock_betas` join

**Models**
- `model_outputs` — long/narrow structured outputs from financial models, versioned
- `model_peers` — peer set per ticker for comps, initially auto-populated from `stocks`

**Workflows**
- `workflow_registry` — canonical list of all defined workflows, queryable at runtime
- `workflow_runs` — every workflow execution: who triggered it, status, cost
- `workflow_outputs_earnings_preview` — structured output of earnings preview workflow

**Alt data**
- `alt_data` — single table, all alt data types via `data_type` column

**Platform**
- `chat_sessions` — persisted chat history, `visibility` (private | public), insert-only

## Chatbot Behavioral Rules (Mode 2)

These rules apply to WF-09 (Response Generator) and must be preserved in its system prompt. Do not modify the system prompt without reviewing `instructions/domain/chatbot.md`.

**Read-only rule:** The chatbot reads from source tables and writes only to output tables (`workflow_outputs_*`, `chat_sessions`, `api_cost_events`). It never updates, deletes, or mutates any source table. Requests like "change my AAPL EPS estimate to $4.00" must be declined with an explanation that data changes happen through the data management interface.

**No fabrication rule:** The chatbot never invents numbers, trends, or explanations. Every figure must be sourced from a database table and cited. If data is unavailable, say so explicitly.

**No hierarchy rule:** When multiple sources contain different values for the same metric (e.g. internal vs. consensus vs. sellside estimates), all values are presented side by side with full citations. No source silently overrides another. The spread between estimates is often the most valuable information.

**Synthesis boundary:** The chatbot summarizes and presents what the data says. It does not generate investment theses, explain why a trend exists, or make recommendations. Structured workflow outputs (earnings previews, model outputs) are permitted because they follow defined templates pulling vetted data — they are not open-ended opinions.

**Citation rules:** Every piece of vetted data must be cited inline using `[TICKER | SourceType | Period | Detail]` format. Two source types are exempt from citation: `positions_trades` and `stock_history` (market prices).

## FastAPI Route Rules

The following route constraints apply to all chatbot-accessible endpoints:

- Source table endpoints exposed to the chatbot must be GET-only
- The only POST routes the chatbot can call are to output tables
- Never expose a DELETE or PATCH route to the chatbot layer
- Any new data source added to the chatbot's retrieval layer must be added to the source whitelist in `instructions/domain/chatbot.md` before implementation

## Auth & Roles

Roles are stored in `user_profiles.role` and `user_profiles.is_admin`.

| Role | Access |
|---|---|
| `analyst` | Own private sessions + all public sessions + all shared research data |
| `analyst` (is_admin=true) | All of the above + all private sessions of all users |

Session visibility: `chat_sessions.visibility` is `private` by default. Users can set their own sessions to `public`. Admins can read all sessions regardless of visibility. Nothing is ever hard-deleted — all sessions are retained for audit.

## WF-02 Classification Extension

WF-02 is path-based by default. For documents originating from UI forms (analyst notes) or vendor feeds (sellside/buyside notes), pass `document_type` explicitly on the `DocumentJob` to skip path classification. Set `classification_method='explicit'`. The existing transcript/filing pipeline is unaffected.

New document types supported by the pipeline:
- `analyst_note` — from UI, processed nightly by `analyst_notes_processing_job`
- `sellside_note` — from vendor feed, processed nightly
- `buyside_note` — from vendor feed, processed nightly

All three use the existing `chunks` table. Chunk metadata must carry `user_id` (analyst notes), `firm` (sellside/buyside), `ticker[]`, `sector[]`, `industry[]` from the parent document.
## Domain Knowledge & Business Rules

Architecture specs for the pipeline live in `instructions/architecture/` (WF-00 through WF-12, DS-01 through DS-04).

Business rules, data contracts, and domain specs live in `instructions/domain/`:

| File | What it covers |
|---|---|
| `instructions/domain/data-schema.md` | Every table: grain, columns, writer, chatbot access, insert policy |
| `instructions/domain/chatbot.md` | Routing rules, retrieval strategy, session rules, cost warning logic |
| `instructions/domain/workflows.md` | Workflow framework, earnings preview spec, model generation spec |
| `instructions/domain/portfolio.md` | Daily job sequence, derivative tables, market neutrality constraint |
| `instructions/domain/models.md` | Canonical Excel model template, processing job, versioning rules |

**When adding a new feature, check these files first.** They contain decisions that are not visible from the code — which table an output lands in, which sources the chatbot can and cannot query, what a workflow must produce to be considered complete.

## Database: New Tables (Not Yet Built)

The following tables have been designed but not yet migrated. Schema definitions are in `instructions/domain/data-schema.md`. Do not create ad-hoc schemas — use the specs there.

**Research & notes**
- `analyst_notes` — internal analyst research notes, insert-only, multi-ticker/sector scope
- `buyside_notes` — external buyside firm notes, ingested via vendor
- `sellside_notes` — sellside firm notes, ingested via vendor, chunked via pipeline
- `sellside_estimates` — structured estimates extracted from sellside notes
- `guidance` — company-issued forward guidance, manually entered until extraction is built

**Estimates (three separate tables, never mixed)**
- `internal_estimates` — our own forward estimates, PIT insert-only, powered by model processing job
- `buyside_estimates` — external buyside forward estimates, ingested daily
- `consensus_estimates` — street consensus estimates, ingested daily

**Portfolio & risk**
- `trade_requests` — PM trade requests, staging table before execution
- `daily_pnl` — pre-calculated daily P&L at position/side/sector/portfolio grain
- `portfolio_concentration` — daily concentration by sector/industry/geography/side
- `portfolio_risk` — daily beta exposures via `stock_betas` join

**Models**
- `model_outputs` — long/narrow structured outputs from financial models, versioned
- `model_peers` — peer set per ticker for comps, initially auto-populated from `stocks`

**Workflows**
- `workflow_registry` — canonical list of all defined workflows, queryable at runtime
- `workflow_runs` — every workflow execution: who triggered it, status, cost
- `workflow_outputs_earnings_preview` — structured output of earnings preview workflow

**Alt data**
- `alt_data` — single table, all alt data types via `data_type` column

**Platform**
- `chat_sessions` — persisted chat history, `visibility` (private | public), insert-only

## Chatbot Behavioral Rules (Mode 2)

These rules apply to WF-09 (Response Generator) and must be preserved in its system prompt. Do not modify the system prompt without reviewing `instructions/domain/chatbot.md`.

**Read-only rule:** The chatbot reads from source tables and writes only to output tables (`workflow_outputs_*`, `chat_sessions`, `api_cost_events`). It never updates, deletes, or mutates any source table. Requests like "change my AAPL EPS estimate to $4.00" must be declined with an explanation that data changes happen through the data management interface.

**No fabrication rule:** The chatbot never invents numbers, trends, or explanations. Every figure must be sourced from a database table and cited. If data is unavailable, say so explicitly.

**No hierarchy rule:** When multiple sources contain different values for the same metric (e.g. internal vs. consensus vs. sellside estimates), all values are presented side by side with full citations. No source silently overrides another. The spread between estimates is often the most valuable information.

**Synthesis boundary:** The chatbot summarizes and presents what the data says. It does not generate investment theses, explain why a trend exists, or make recommendations. Structured workflow outputs (earnings previews, model outputs) are permitted because they follow defined templates pulling vetted data — they are not open-ended opinions.

**Citation rules:** Every piece of vetted data must be cited inline using `[TICKER | SourceType | Period | Detail]` format. Two source types are exempt from citation: `positions_trades` and `stock_history` (market prices).

## FastAPI Route Rules

The following route constraints apply to all chatbot-accessible endpoints:

- Source table endpoints exposed to the chatbot must be GET-only
- The only POST routes the chatbot can call are to output tables
- Never expose a DELETE or PATCH route to the chatbot layer
- Any new data source added to the chatbot's retrieval layer must be added to the source whitelist in `instructions/domain/chatbot.md` before implementation

## Auth & Roles

Roles are stored in `user_profiles.role` and `user_profiles.is_admin`.

| Role | Access |
|---|---|
| `analyst` | Own private sessions + all public sessions + all shared research data |
| `analyst` (is_admin=true) | All of the above + all private sessions of all users |

Session visibility: `chat_sessions.visibility` is `private` by default. Users can set their own sessions to `public`. Admins can read all sessions regardless of visibility. Nothing is ever hard-deleted — all sessions are retained for audit.

## WF-02 Classification Extension

WF-02 is path-based by default. For documents originating from UI forms (analyst notes) or vendor feeds (sellside/buyside notes), pass `document_type` explicitly on the `DocumentJob` to skip path classification. Set `classification_method='explicit'`. The existing transcript/filing pipeline is unaffected.

New document types supported by the pipeline:
- `analyst_note` — from UI, processed nightly by `analyst_notes_processing_job`
- `sellside_note` — from vendor feed, processed nightly
- `buyside_note` — from vendor feed, processed nightly

All three use the existing `chunks` table. Chunk metadata must carry `user_id` (analyst notes), `firm` (sellside/buyside), `ticker[]`, `sector[]`, `industry[]` from the parent document.
