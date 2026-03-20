# Data schema

Canonical reference for every table in GoldMine. For each table: grain, key columns, who writes it, whether it is insert-only or upsertable, and whether the chatbot (Mode 2) can query it.

**Insert-only** means no UPDATE or DELETE is ever issued against the table. New state is always a new row. This applies to anything that must be auditable over time.

---

## Existing tables (already built)

### `stocks`
Grain: one row per ticker. S&P 500 universe (503 tickers).
Writer: `update_all_data.py` (weekly). Upsertable.
Chatbot: read. Used for ticker resolution, sector/industry lookup, peer population.
Key columns: `ticker`, `company_name`, `sector`, `industry`, `market_cap`, `exchange`.

### `financial_metrics`
Grain: one row per ticker per period per metric.
Writer: `update_all_data.py` (weekly). Upsertable.
Chatbot: read. Primary source for fundamental queries (revenue, margins, EPS, B/S, cash flow).
Key columns: `ticker`, `period`, `metric_name`, `value`, `period_type` (annual | quarterly).
Never mix with portfolio P&L data — these are reported company financials only.

### `stock_history`
Grain: one row per ticker per date.
Writer: `update_all_data.py` (weekly). Upsertable.
Chatbot: read. Used for price/performance queries. Exempt from inline citation.
Key columns: `ticker`, `date`, `open`, `high`, `low`, `close`, `volume`, `adjusted_close`.

### `transcripts_list`
Grain: one row per earnings call (ticker + period).
Writer: `update_all_data.py`. Upsertable.
Chatbot: indirect (via `chunks`). Source registry for pipeline.
Key columns: `ticker`, `period`, `call_date`, `fiscal_quarter`.

### `sec_filings`
Grain: one row per filing (ticker + filing type + period).
Writer: `update_all_data.py`. Upsertable.
Chatbot: indirect (via `chunks`). Source registry for pipeline.
Key columns: `ticker`, `filing_type` (10-K | 10-Q | 8-K | DEF14A), `period`, `filed_date`, `primary_document`.

### `chunks`
Grain: one row per document chunk.
Writer: WF-04 (embedding + storage). Insert-only.
Chatbot: read via pgvector cosine similarity. Primary retrieval source for all document types.
Key columns: `id`, `ticker`, `doc_type`, `period`, `content`, `embedding` (1536-dim OpenAI), `source_doc_id`, `chunk_index`, `metadata` (JSONB — carries speaker, section, user_id, firm, ticker_list, sector_list, industry_list depending on doc_type).
Doc types: `earnings_transcript`, `10-K`, `10-Q`, `8-K`, `analyst_note`, `sellside_note`, `buyside_note`.

### `people`
Grain: one row per executive per company.
Writer: `update_all_data.py` (monthly). Upsertable.
Chatbot: read. Used for executive/compensation queries.
Key columns: `ticker`, `name`, `title`, `compensation`.

### `earnings_calendar`
Grain: one row per ticker per earnings date.
Writer: `update_all_data.py`. Upsertable.
Chatbot: read. Used for scheduling earnings preview workflows.
Key columns: `ticker`, `report_date`, `fiscal_period`, `confirmed`.

### `stock_betas`
Grain: one row per ticker.
Writer: `update_all_data.py`. Upsertable.
Chatbot: indirect (via `portfolio_risk`). Used by risk calculation job.
Key columns: `ticker`, `beta`, `as_of_date`.

### `user_profiles`
Grain: one row per user.
Writer: auth system. Upsertable.
Chatbot: read (for attribution display only, never surfaced in responses).
Key columns: `user_id`, `display_name`, `role` (analyst), `is_admin` (bool), `created_at`, `updated_at`.
Roles: `analyst` for all users. `is_admin=true` grants full session visibility.

### `api_cost_events`
Grain: one row per LLM API call.
Writer: chatbot pipeline (all WF stages). Insert-only.
Chatbot: no direct access. Used by cost estimation logic only.
Key columns: `id`, `workflow_step`, `model`, `input_tokens`, `output_tokens`, `cost_usd`, `session_id`, `created_at`.

### `model_config`
Grain: one row per pipeline component.
Writer: manual admin update. Upsertable.
Chatbot: read at runtime for model assignment. Enables hot-swap without redeploy.
Key columns: `component` (wf06_classifier | wf09_generator | etc.), `model_id`, `updated_at`.

---

## New tables (designed, not yet migrated)

---

### `analyst_notes`
Grain: one row per published note.
Writer: analyst via platform UI. Insert-only. No edits, no deletes — analysts publish new notes instead.
Chatbot: read. Retrieved via `chunks` (vector search on embedded content). Citation label: `[TICKER | Analyst Note | Author | Date]`.
Key columns:
- `id` uuid PK
- `user_id` uuid FK → `user_profiles.user_id`
- `tickers` text[] (nullable — zero or many tickers)
- `sectors` text[] (nullable — zero or many sectors)
- `industries` text[] (nullable)
- `content` text (free-form, variable length)
- `created_at` timestamptz

Processing: nightly `analyst_notes_processing_job` sends new rows through WF-01 to WF-05 with `doc_type='analyst_note'` explicit override. Chunks inherit `user_id`, `tickers`, `sectors`, `industries` as metadata.

---

### `buyside_notes`
Grain: one row per external buyside note.
Writer: vendor ingestion job (nightly). Insert-only.
Chatbot: read via `chunks`. Citation label: `[TICKER | Buyside Note | Firm | Date]`.
Key columns:
- `id` uuid PK
- `ticker` text
- `firm` text
- `published_date` date
- `content` text
- `created_at` timestamptz

---

### `sellside_notes`
Grain: one row per sellside note.
Writer: vendor ingestion job (nightly). Insert-only.
Chatbot: read via `chunks`. Citation label: `[TICKER | Sellside Note | Firm | Date]`.
Key columns:
- `id` uuid PK
- `ticker` text
- `firm` text
- `published_date` date
- `content` text
- `created_at` timestamptz

Note: sellside notes are also processed by a structured extraction job that writes estimates and price targets to `sellside_estimates`.

---

### `sellside_estimates`
Grain: one row per ticker per metric per period per firm per published date.
Writer: sellside extraction job (runs after sellside note ingestion). Insert-only.
Chatbot: read. Always presented alongside `internal_estimates`, `buyside_estimates`, `consensus_estimates` — never in isolation. Citation label: `[TICKER | Sellside Estimate | Firm | Date]`.
Key columns:
- `id` uuid PK
- `ticker` text
- `firm` text
- `analysts` text[] (array of analyst names at that firm)
- `period` text (e.g. 2026Q1, 2026A)
- `metric` text (revenue | eps | ebitda | etc.)
- `value` numeric
- `unit` text
- `published_date` date
- `created_at` timestamptz

---

### `internal_estimates`
Grain: one row per ticker per metric per period per version (PIT).
Writer: model processing job only. Insert-only. Never updated — new estimates are new rows.
Chatbot: read. Always the most recent row per (ticker, metric, period). Citation label: `[TICKER | Internal Estimate | Author | Date]`.
Key columns:
- `id` uuid PK
- `ticker` text
- `period` text
- `metric` text
- `value` numeric
- `unit` text
- `user_id` uuid FK (analyst whose model produced this estimate)
- `model_version` text
- `created_at` timestamptz

Query pattern: `SELECT DISTINCT ON (ticker, metric, period) * FROM internal_estimates ORDER BY ticker, metric, period, created_at DESC`.

---

### `buyside_estimates`
Grain: one row per ticker per metric per period per firm per as_of_date.
Writer: vendor ingestion job (daily). Insert-only (preserve historical snapshots).
Chatbot: read. Citation label: `[TICKER | Buyside Estimate | Firm | Date]`.
Key columns:
- `id` uuid PK
- `ticker` text
- `firm` text
- `period` text
- `metric` text
- `value` numeric
- `unit` text
- `as_of_date` date
- `created_at` timestamptz

---

### `consensus_estimates`
Grain: one row per ticker per metric per period per as_of_date.
Writer: vendor ingestion job (daily). Insert-only (preserve historical snapshots).
Chatbot: read. Citation label: `[TICKER | Consensus | Period | Date]`.
Key columns:
- `id` uuid PK
- `ticker` text
- `period` text
- `metric` text
- `value` numeric
- `unit` text
- `as_of_date` date
- `created_at` timestamptz

---

### `guidance`
Grain: one row per company guidance issuance per ticker per metric per period.
Writer: manual entry by analysts (until automated extraction is built). Insert-only.
Chatbot: read. Used in earnings preview forward quarter view. Citation label: `[TICKER | Guidance | Period | Date]`.
Key columns:
- `id` uuid PK
- `ticker` text
- `period` text
- `metric` text
- `value` numeric
- `unit` text
- `guidance_type` text (initial | raised | lowered | withdrawn)
- `source` text (transcript | filing | manual)
- `issued_date` date
- `user_id` uuid FK (if manual entry)
- `created_at` timestamptz

---

### `alt_data`
Grain: one row per ticker per data_type per date.
Writer: vendor ingestion + normalization job. Insert-only (append new periods).
Chatbot: read. Coverage is sparse — not all tickers have all data types. Always check for null/missing before presenting. Citation label: `[TICKER | Alt Data | Type | Period]`.
Key columns:
- `id` uuid PK
- `ticker` text
- `data_type` text (credit_card | web_traffic | app_downloads | google_trends | email_receipts | medical_claims)
- `date_frequency` text (daily | weekly | monthly | quarterly)
- `date` date (end date of period)
- `value` numeric
- `growth` numeric (pre-calculated YoY or period-over-period — never ask chatbot to calculate)
- `unit` text
- `source_vendor` text
- `data_as_of_date` date
- `as_of_date` date
- `created_at` timestamptz

Alt data keyword → data_type mapping (for WF-06 classifier):
- credit card, card data, transaction data, consumer spend, CC data → `credit_card`
- web traffic, website visits, web visits, site traffic → `web_traffic`
- app downloads, download data, app installs, mobile downloads → `app_downloads`
- google trends, search trends, search data → `google_trends`
- email receipts, receipt data, email data → `email_receipts`
- medical claims, claims data, healthcare data → `medical_claims`

---

### `trade_requests`
Grain: one row per trade request.
Writer: PM via platform UI. Insert-only. Status updated as request progresses.
Chatbot: read-only (can query to show pending/executed requests). Never write via chatbot.
Key columns:
- `id` uuid PK
- `user_id` uuid FK → `user_profiles`
- `ticker` text
- `portfolio` text (flagship | long_only)
- `action` text (buy | sell)
- `side` text (long | short)
- `target_pct` numeric (% of total fund AUM)
- `status` text (pending | executed | cancelled)
- `created_at` timestamptz
- `executed_at` timestamptz (nullable)

EOD job `trade_completed_job`: moves executed `trade_requests` from prior day into `portfolio_trades`.

---

### `daily_pnl`
Grain: one row per ticker per portfolio per side per sector per date.
Writer: `pnl_calculation_job` (runs after `trade_completed_job`). Insert-only.
Chatbot: read. Primary source for all portfolio P&L queries. Supports roll-up at any level: total portfolio, by side, by sector, by sector+side, by position.
Key columns:
- `id` uuid PK
- `date` date
- `ticker` text
- `portfolio` text (flagship | long_only)
- `side` text (long | short)
- `sector` text
- `industry` text
- `unrealized_pnl` numeric
- `realized_pnl` numeric
- `daily_return` numeric
- `cumulative_return` numeric
- `contribution_to_portfolio` numeric
- `created_at` timestamptz

---

### `portfolio_concentration`
Grain: one row per ticker per portfolio per date.
Writer: `concentration_job` (daily, runs after `pnl_calculation_job`). Insert-only.
Chatbot: read. Used for concentration and exposure queries.
Key columns:
- `id` uuid PK
- `date` date
- `ticker` text
- `portfolio` text
- `side` text (long | short)
- `sector` text
- `industry` text
- `geography` text
- `position_weight` numeric (% of portfolio)
- `sector_weight` numeric
- `industry_weight` numeric
- `geo_weight` numeric
- `is_market_neutral_compliant` bool (flagship only: long $ = short $ within tolerance)
- `created_at` timestamptz

---

### `portfolio_risk`
Grain: one row per ticker per portfolio per date.
Writer: `risk_job` (daily, joins `portfolio_concentration` with `stock_betas`). Insert-only.
Chatbot: read. Used for beta exposure and risk queries.
Key columns:
- `id` uuid PK
- `date` date
- `ticker` text
- `portfolio` text
- `beta` numeric (from `stock_betas`)
- `weighted_beta_contribution` numeric
- `sector` text
- `side` text
- `created_at` timestamptz

---

### `model_outputs`
Grain: one row per ticker per version per sheet per metric per scenario per period.
Writer: model processing job only. Insert-only (new version = new rows, never overwrite).
Chatbot: read. Always queries most recent version per ticker. Citation label: `[TICKER | Model | Date]`.
Key columns:
- `id` uuid PK
- `ticker` text
- `version` text (auto-incremented per ticker)
- `as_of_date` date
- `sheet` text (income_statement | balance_sheet | cash_flow | valuation | kpis | scenarios | assumptions)
- `metric` text
- `period` text (2025Q1 | 2025A | etc.)
- `scenario` text (base | bull | bear | actual)
- `value` numeric
- `unit` text (dollars | percentage | ratio | per_share)
- `created_by` text (user_id if analyst upload, 'system' if LLM-generated)
- `created_at` timestamptz

Query pattern for current model: `SELECT DISTINCT ON (ticker, sheet, metric, period, scenario) * FROM model_outputs ORDER BY ticker, sheet, metric, period, scenario, as_of_date DESC`.

LLM model edit flow: user requests edit → system reads current `model_outputs` (most recent version) → LLM receives current assumptions + edit instruction → LLM generates updated outputs → new version rows inserted → model processing job writes updated `internal_estimates`.

---

### `model_peers`
Grain: one row per ticker per peer ticker.
Writer: model generation job (initial population) + analyst via data management UI. Upsertable.
Chatbot: read. Used to pull peer comps from `financial_metrics` for valuation sheet.
Key columns:
- `id` uuid PK
- `ticker` text
- `peer_ticker` text
- `created_at` timestamptz
- `created_by` text (user_id or 'system')

Initial population: 5 peers per ticker, selected from `stocks` table matching same `sector` and `industry`.

---

### `workflow_registry`
Grain: one row per defined workflow.
Writer: developer (manual insert on new workflow definition). Upsertable.
Chatbot: read at runtime. Used to look up output table, required inputs, and trigger rules when user requests a workflow by name.
Key columns:
- `id` uuid PK
- `workflow_name` text (earnings_preview | financial_model_generation | etc.)
- `display_name` text
- `description` text
- `required_inputs` jsonb (e.g. {"ticker": "required", "period": "required"})
- `output_table` text (e.g. workflow_outputs_earnings_preview)
- `trigger_type` text (on_demand | scheduled | both)
- `schedule_rule` text (nullable — e.g. "7 days before earnings_calendar.report_date")
- `is_active` bool
- `created_at` timestamptz

---

### `workflow_runs`
Grain: one row per workflow execution.
Writer: workflow execution layer. Insert-only.
Chatbot: read (can report on prior runs for a ticker). Never write via chatbot.
Key columns:
- `id` uuid PK
- `workflow_id` uuid FK → `workflow_registry`
- `ticker` text (nullable for portfolio-wide workflows)
- `triggered_by` text (user_id or 'scheduler')
- `status` text (pending | running | completed | failed)
- `started_at` timestamptz
- `completed_at` timestamptz (nullable)
- `cost_usd` numeric (nullable — populated on completion)
- `output_id` uuid (nullable — FK to relevant workflow_outputs table)
- `created_at` timestamptz

---

### `workflow_outputs_earnings_preview`
Grain: one row per earnings preview generation (ticker + period + run).
Writer: earnings preview workflow. Insert-only.
Chatbot: read. Prior previews for a ticker are surfaced as context when generating new ones (structured lookup, not vector search).
Key columns: see `instructions/domain/workflows.md` for full earnings preview output schema.

---

### `chat_sessions`
Grain: one row per chat session.
Writer: WF-10 session manager. Insert-only. No hard deletes ever.
Chatbot: no — chat history is never fed back to the LLM as retrieval context.
Key columns:
- `id` uuid PK
- `user_id` uuid FK → `user_profiles`
- `title` text (auto-generated after first exchange by WF-10)
- `visibility` text (private | public) default 'private'
- `messages` jsonb (compressed every 10 turns by WF-10)
- `created_at` timestamptz
- `updated_at` timestamptz

Visibility rules: private = author only. public = entire team. Admin (`is_admin=true`) can read all sessions regardless of visibility. Sessions are never deleted — retained permanently for audit.

---

## Daily job execution order

```
Market close
    ↓
trade_completed_job        — executed trade_requests → portfolio_trades
    ↓
pnl_calculation_job        — portfolio_trades → daily_pnl
    ↓
concentration_job          — portfolio_trades → portfolio_concentration
    ↓
risk_job                   — portfolio_concentration + stock_betas → portfolio_risk
    ↓
model_processing_job       — S3 Excel (latest version) → model_outputs + internal_estimates
    ↓
analyst_notes_processing_job — new analyst_notes rows → chunks (via WF-01 to WF-05)
    ↓
vendor_ingestion_jobs      — buyside_notes, sellside_notes, alt_data, buyside_estimates,
                             consensus_estimates → respective tables
```
