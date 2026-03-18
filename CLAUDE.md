# GoldMine

Investment Research CRM for Portfolio Managers and Research Analysts. Combines a data-grid CRM with an AI-powered chat interface backed by a financial document knowledge base.

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

## Demo Users

| Username | Password | Role |
|---|---|---|
| `analyst1` | `analyst123` | Research Analyst |
| `analyst2` | `analyst456` | Research Analyst |
| `pm1` | `pm789` | Portfolio Manager |

Hardcoded in `backend/app/auth/users.py` (bcrypt hashed).
