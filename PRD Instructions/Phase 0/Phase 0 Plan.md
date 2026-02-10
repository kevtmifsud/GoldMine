# GoldMine Phase 0 — Foundations & Infrastructure

## Context

Building the foundational infrastructure for "GoldMine", an Investment Research CRM platform for Portfolio Managers and Research Analysts. Phase 0 establishes the app skeleton, authentication, data access abstraction, object storage abstraction, and logging — with no user-facing research functionality beyond login and the app shell.

**Key decisions:**
- **Frontend:** React + TypeScript (Vite)
- **Backend:** Python + FastAPI (lightweight, CSV-backed for now)
- **Data:** Static CSVs for structured data (swappable to Snowflake/Redshift later)
- **File storage:** Local filesystem (swappable to S3 later)
- **Auth:** JWT in httpOnly cookies
- **Project directory:** `/Users/kdonadio/Code/GoldMine`

---

## Prerequisites (Stage 0)

Install Homebrew, then Node 20 LTS and Python 3.11+:
```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install node@20 python@3.12
```

---

## Project Structure

```
GoldMine/
├── .gitignore
├── .env.example
├── README.md
├── backend/
│   ├── .env / .env.example
│   ├── requirements.txt / requirements-dev.txt
│   └── app/
│       ├── main.py                  # FastAPI app factory
│       ├── config/settings.py       # Pydantic Settings (env-based)
│       ├── logging_config.py        # Structured logging (structlog)
│       ├── exceptions.py            # Custom exceptions + global handlers
│       ├── auth/
│       │   ├── models.py            # LoginRequest, UserInfo pydantic models
│       │   ├── users.py             # Hardcoded user store (3 demo users)
│       │   ├── service.py           # JWT create/decode, credential validation
│       │   ├── router.py            # POST /auth/login, /logout, GET /auth/me
│       │   └── middleware.py        # ASGI middleware: extract JWT cookie, gate routes
│       ├── data_access/
│       │   ├── interfaces.py        # ABC: DataAccessProvider (query, get_record, list_datasets)
│       │   ├── models.py            # PaginatedResponse, FilterParams, DatasetInfo
│       │   ├── csv_provider.py      # CSV implementation (pandas, cached, paginated)
│       │   └── factory.py           # Returns provider based on config
│       ├── object_storage/
│       │   ├── interfaces.py        # ABC: ObjectStorageProvider (get_file, get_metadata, list)
│       │   ├── models.py            # FileMetadata
│       │   ├── local_provider.py    # Local filesystem + manifest.json
│       │   └── factory.py           # Returns provider based on config
│       ├── api/
│       │   ├── health.py            # GET /api/health
│       │   ├── data.py              # GET /api/data/, /api/data/{dataset}, /api/data/{dataset}/{id}
│       │   └── files.py             # GET /api/files/, /api/files/{id}/metadata, /api/files/{id}
│       └── tests/
│           ├── conftest.py
│           ├── test_health.py
│           ├── test_auth.py
│           ├── test_data_access.py
│           └── test_object_storage.py
├── frontend/
│   ├── vite.config.ts               # Dev proxy /auth + /api → localhost:8000
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx                  # Routing + AuthProvider wrapper
│   │   ├── config/api.ts            # Axios instance (withCredentials, 401 interceptor)
│   │   ├── auth/
│   │   │   ├── AuthContext.tsx       # Login state, /auth/me check on mount
│   │   │   ├── AuthGuard.tsx         # Redirect to /login if unauthenticated
│   │   │   ├── LoginPage.tsx         # Username/password form
│   │   │   └── useAuth.ts           # Convenience hook
│   │   ├── pages/HomePage.tsx        # Post-login shell placeholder
│   │   ├── components/Layout.tsx     # Header bar (logo, user name, logout)
│   │   └── styles/                   # CSS files
├── data/
│   ├── structured/
│   │   ├── stocks.csv               # ~75 rows (ticker, company, sector, market_cap, P/E, etc.)
│   │   ├── people.csv               # ~40 rows (executives, analysts)
│   │   └── datasets.csv             # ~10 rows (dataset metadata)
│   └── unstructured/
│       ├── files_manifest.json      # Index of all files with metadata + entity tags
│       ├── reports/*.pdf            # Placeholder research report PDFs
│       ├── transcripts/*.txt        # Sample earnings call transcripts
│       ├── data_exports/*.csv       # Sample CSV exports
│       └── audio/*.mp3              # Placeholder audio file
└── scripts/
    ├── generate_sample_data.py      # Generates all sample CSVs + unstructured files
    └── dev_start.sh                 # Starts backend + frontend in parallel
```

---

## Key Architectural Patterns

### 1. Provider Interface + Factory (swappable data sources)
- `DataAccessProvider` ABC defines: `query()`, `get_record()`, `list_datasets()`
- `CsvDataAccessProvider` implements it with pandas (cache CSVs in memory, filter/sort/paginate)
- `factory.py` selects provider based on `GOLDMINE_DATA_PROVIDER` env var
- **To swap to Snowflake later:** create `SnowflakeDataAccessProvider`, add to factory, change env var. Zero frontend changes.
- Same pattern for `ObjectStorageProvider` → `LocalStorageProvider` → future `S3StorageProvider`

### 2. Cookie-Based JWT Auth
- `POST /auth/login` validates credentials, returns JWT in `Set-Cookie: goldmine_token` (httpOnly, SameSite=Lax)
- ASGI middleware extracts cookie, decodes JWT, attaches user to `request.state.user`
- Middleware skips `/auth/login`, `/auth/logout`, `/api/health`
- No RBAC yet — all authenticated users have the same level. Middleware designed for future RBAC layer.

### 3. Server-Side Pagination Enforcement
- `MAX_PAGE_SIZE = 200` enforced in providers
- `PaginatedResponse` always includes full pagination metadata
- Client cannot request unbounded data

---

## Implementation Order (8 Stages)

### Stage 1: Prerequisites + Scaffolding
- Install Homebrew → Node 20 → Python 3.12
- Create GoldMine directory, `git init`
- `.gitignore`, `.env.example`, `README.md`
- Backend: create venv, `requirements.txt`, install deps
- Frontend: `npm create vite@latest` with react-ts template, install deps

### Stage 2: Backend Config + Skeleton
- `config/settings.py` (pydantic-settings with `GOLDMINE_` prefix)
- `logging_config.py` (structlog, JSON in prod, colored console in dev)
- `exceptions.py` (DataAccessError, AuthenticationError, global handlers)
- `main.py` (app factory, CORS, health router)
- **Verify:** `uvicorn app.main:app --reload` → `GET /api/health` returns 200

### Stage 3: Authentication
- `auth/models.py`, `auth/users.py` (3 demo users with bcrypt passwords)
- `auth/service.py` (credential check, JWT create/decode)
- `auth/router.py` (login, logout, me)
- `auth/middleware.py` (cookie extraction, route gating)
- Wire into `main.py`
- **Verify:** Login sets cookie, `/auth/me` returns user, unauthenticated → 401

### Stage 4: Sample Data Generation
- `scripts/generate_sample_data.py` — generates:
  - `stocks.csv`: 75 rows with ticker, company_name, sector, industry, market_cap_b, pe_ratio, price, 52w_high/low, dividend_yield, eps, revenue_b, country, exchange
  - `people.csv`: 40 rows with person_id, name, title, org, type, tickers
  - `datasets.csv`: 10 rows with dataset metadata
  - Placeholder PDFs (using fpdf2), text transcripts, sample CSV exports, placeholder audio
  - `files_manifest.json`

### Stage 5: Data Access Layer
- `data_access/interfaces.py` (DataAccessProvider ABC)
- `data_access/models.py` (PaginatedResponse, FilterParams, DatasetInfo)
- `data_access/csv_provider.py` (pandas-backed, cached, filtered, paginated)
- `data_access/factory.py`
- `api/data.py` (REST endpoints)
- **Verify:** `GET /api/data/stocks?page=1&page_size=10` returns paginated JSON

### Stage 6: Object Storage Layer
- `object_storage/interfaces.py` (ObjectStorageProvider ABC)
- `object_storage/models.py` (FileMetadata)
- `object_storage/local_provider.py` (reads manifest + local files)
- `object_storage/factory.py`
- `api/files.py` (REST endpoints)
- **Verify:** `GET /api/files/FILE-001/metadata` returns metadata, `GET /api/files/FILE-001` returns file bytes

### Stage 7: Frontend
- `vite.config.ts` (proxy to backend)
- `config/api.ts` (axios with credentials)
- `auth/` (AuthContext, AuthGuard, LoginPage, useAuth)
- `components/Layout.tsx` (header with logo + logout)
- `pages/HomePage.tsx` (welcome placeholder)
- `App.tsx` (routing + auth wiring)
- Styles
- **Verify:** Browser at localhost:5173 → login → home page → logout → redirect to login

### Stage 8: Tests + Polish
- `tests/conftest.py`, `test_health.py`, `test_auth.py`, `test_data_access.py`, `test_object_storage.py`
- `scripts/dev_start.sh`
- Update `README.md` with setup instructions
- **Verify:** `pytest -v` — all pass

---

## Phase 0 Exit Criteria Verification

| Criteria | How to verify |
|---|---|
| Users can authenticate and reach app shell | Login with analyst1/analyst123, see home page |
| Invalid credentials denied | Login with wrong password, see error |
| Unauthenticated users redirected | Visit / without session, get sent to /login |
| Backend health endpoint works | `GET /api/health` → 200 |
| All data reads through service layer | CSVs not served directly; only accessible via /api/data/* |
| Pagination enforced server-side | Request page_size=9999, get max 200 rows |
| File metadata without full download | `GET /api/files/{id}/metadata` returns JSON, not file bytes |
| Login < 500ms | Check DevTools Network tab |
| Structured logging active | Backend console shows JSON-formatted logs |
| Auth failures logged | Failed login attempts appear in logs |
| All tests pass | `pytest -v` |
