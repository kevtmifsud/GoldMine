# Data schema

Canonical reference for every table in GoldMine. For each table: grain, key columns, who writes it, whether it is insert-only or upsertable, and whether the chatbot (Mode 2) can query it.

**Insert-only** means no UPDATE or DELETE is ever issued against the table. New state is always a new row. This applies to anything that must be auditable over time.

---

## Existing tables (already built)

### `stocks`
Grain: one row per ticker. S&P 500 universe (503 tickers).
Writer: `update_all_data.py` (weekly). Upsertable.
Chatbot: read. Used for ticker resolution, sector/industry lookup, peer population.
Key columns:
- `ticker` varchar PK
- `company_name` text
- `sector` varchar
- `industry` varchar
- `market_cap_b` varchar
- `pe_ratio` varchar
- `price` varchar
- `52w_high` varchar
- `52w_low` varchar
- `dividend_yield` varchar
- `eps` varchar
- `revenue_b` varchar
- `country` varchar
- `exchange` varchar
- `address` text
- `city` varchar
- `phone` varchar
- `zip` varchar
- `long_business_summary` text
- `full_time_employees` varchar
- `web_site` text
- `report_date` varchar

### `financial_metrics`
Grain: one row per ticker per period per metric.
Writer: `update_all_data.py` (weekly). Upsertable.
Chatbot: read. Primary source for fundamental queries (revenue, margins, EPS, B/S, cash flow).
Key columns:
- `ticker` varchar
- `metric_name` varchar
- `period_end` date
- `period_type` varchar (annual | quarterly)
- `value` numeric
- `created_at` timestamptz

Never mix with portfolio P&L data — these are reported company financials only.

### `stock_history`
Grain: one row per ticker per date.
Writer: `update_all_data.py` (weekly). Upsertable.
Chatbot: read. Used for price/performance queries and EPS estimate vs actual comparison. Exempt from inline citation.
Key columns: `date` varchar, `ticker` varchar, `close` varchar, `eps_estimate` varchar (nullable), `eps_actual` varchar (nullable).
Note: All columns are VARCHAR. Always cast to appropriate types in queries: `date::date`, `close::numeric`, `NULLIF(eps_estimate, '')::numeric`, `NULLIF(eps_actual, '')::numeric`.

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
Key columns:
- `chunk_id` uuid PK
- `document_id` uuid FK → source document
- `ticker` text
- `document_type` text (earnings_transcript | 10-K | 10-Q | 8-K | analyst_note | sellside_note | buyside_note)
- `fiscal_period` text (e.g. Q4_2024, FY2024)
- `section_name` text (e.g. "CFO Remarks")
- `section_type` text (e.g. cfo_remarks, risk_factors)
- `chunk_text` text (the actual content)
- `chunk_sequence` integer (position in document)
- `word_count` integer
- `filing_date` date (nullable)
- `page_reference` integer (nullable)
- `is_active` boolean DEFAULT true
- `embedding` vector(1536) (OpenAI text-embedding-3-large)
- `created_at` timestamptz

Note: code uses actual DB column names correctly. This section was previously documented with different names — now corrected to match the actual schema.

### `people`
Grain: one row per person (executive, buyside analyst, or sellside analyst).
Writer: `update_all_data.py` (monthly, executives), `seed_analysts.py` (analysts). Upsertable.
Chatbot: read. Used for executive/compensation queries and analyst attribution on estimates.
Key columns: `person_id` varchar PK, `name` text, `title` text, `organization` text, `type` varchar (`executive` | `buyside_analyst` | `sellside_analyst`), `tickers` text (executives only), `sector_coverage` text[] (analysts only — sectors covered).

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
Chatbot: no direct access. Used by cost estimation logic and daily cost report.
Key columns:
- `id` uuid PK
- `mode` text (mode_2)
- `component` text (response_generator | query_classifier | query_embedder | screening_prefilter | session_compressor)
- `model` text (model name used)
- `input_tokens` integer
- `output_tokens` integer (nullable)
- `cost_usd` numeric
- `session_id` uuid (nullable)
- `message_id` uuid (nullable)
- `user_id` text (nullable)
- `query_type` text (nullable)
- `ticker_count` integer (nullable)
- `document_id` uuid (nullable)
- `created_at` timestamptz

### `model_config`
Grain: one row per pipeline component.
Writer: manual admin update. Upsertable.
Chatbot: read at runtime for model assignment. Enables hot-swap without redeploy.
Key columns: `component` (wf06_classifier | wf09_generator | etc.), `model_id`, `updated_at`.

### `api_pricing`
Grain: one row per model per pricing tier.
Writer: manual admin update. Upsertable.
Chatbot: no direct access. Used by cost calculation logic in `cost.py`.
Key columns: `model`, `input_per_1m` numeric, `output_per_1m` numeric, `is_current` bool.

### `portfolio_trades`
Grain: one row per executed trade.
Writer: `trade_completed_job` (moves executed `trade_requests` → `portfolio_trades`). Insert-only.
Chatbot: indirect (via `daily_pnl`). Source of truth for all position and P&L calculations.
Key columns: `date`, `ticker`, `action` (buy | sell), `shares`, `price`, `portfolio` ('Flagship' | 'Long Only'), `side` (long | short).
Portfolio names in the database use Title Case with spaces. The tool layer normalizes lowercase_underscore input to match these values via `PORTFOLIO_MAP` in `retrieval.py`.

### `workflow_outputs_docs_sync`
Grain: one row per docs_sync workflow run.
Writer: docs_sync workflow. Insert-only.
Chatbot: read. Surfaces documentation gap reports and sync history.
Key columns: `id` uuid PK, `workflow_run_id` uuid FK, `triggered_by` text, `started_at` timestamptz, `completed_at` timestamptz, `files_checked` text[], `gaps_found` jsonb, `files_updated` text[], `items_needing_human_review` jsonb, `summary` text, `created_at` timestamptz.

### `workflow_outputs_financial_model`
Grain: one row per financial model generation (ticker + version + run).
Writer: financial_model_generation workflow. Insert-only.
Chatbot: read. Prior models for a ticker are surfaced as context.
Key columns: `id` uuid PK, `workflow_run_id` uuid FK, `ticker` text, `version` text, `s3_path` text, `key_kpis` text[], `assumptions_snapshot` jsonb, `generated_at` timestamptz, `generated_by` text.

---

## Mode 2 platform tables (existing, pre-built)

These tables existed before the domain schema work and power the core Mode 2 chat infrastructure. They are all working correctly. Documented here for completeness.

### `conversations`
Grain: one row per conversation thread. The shareable unit — visibility lives here.
Writer: mode2 router on first message. Upsertable (title, visibility updates).
Chatbot: no direct access.
Key columns: `id` uuid PK, `user_id` text, `title` text, `ticker_context` text[], `visibility` text DEFAULT 'private' ('private' | 'public') — added in migration 026, `is_archived` bool, `origin_path` varchar, `created_at` timestamptz, `updated_at` timestamptz.
Visibility rules: private = owner only (default). public = entire team can view. Admin sees everything. Set at conversation level — all sessions within inherit the same visibility.
Note: parent of `sessions` table.

### `messages`
Grain: one row per chat message (user or assistant).
Writer: mode2 generator after each response. Insert-only.
Chatbot: no direct access — conversation history is for user reference only.
Key columns: `id` uuid PK, `session_id` uuid FK → `sessions`, `user_id` text, `role` varchar (user | assistant), `content` text, `query_type` varchar, `tickers_referenced` text[], `source_chunks` jsonb, `qa_library_hits` jsonb, `classifier_model` varchar, `generator_model` varchar, `input_tokens` integer, `output_tokens` integer, `cost_usd` numeric, `content_embedding` vector, `created_at` timestamptz.

### `qa_library`
Grain: one row per validated Q&A pair.
Writer: WF-11 feedback pipeline. Insert-only.
Chatbot: read via pgvector similarity search at start of every query (threshold 0.88).
Key columns: `id` uuid PK, `question` text, `answer` text, `question_embedding` vector, `tickers_referenced` text[], `validation_type` text, `validation_weight` numeric, `created_at` timestamptz.

### `screening_cache`
Grain: one row per cached screening result.
Writer: WF-08 retrieval after screening runs. Upsertable (expires_at refreshed on re-query).
Key columns: `query_hash` text PK, `query_text` text, `result_content` jsonb, `expires_at` timestamptz, `hit_count` integer, `created_at` timestamptz.
Chatbot: read/write for screening queries.

### `conversation_shares`
Grain: one row per share grant.
Writer: sharing API. Insert-only.
Key columns: `id` uuid PK, `conversation_id` uuid FK, `shared_by` text, `shared_with` text, `created_at` timestamptz.
Chatbot: no access.

### `insights`
Grain: one row per saved insight.
Writer: mode2 router (analyst saves a message as insight). Insert-only.
Key columns: `id` uuid PK, `user_id` text, `message_id` uuid, `session_id` uuid, `title` text, `content` text, `ticker_context` text[], `tags` text[], `created_at` timestamptz.
Chatbot: no access.

### `insight_shares`
Grain: one row per insight share grant.
Writer: sharing API. Insert-only.
Chatbot: no access.

### `message_feedback`
Grain: one row per feedback action on a message.
Writer: WF-11 feedback pipeline. Insert-only.
Chatbot: no access.

### `llm_bug_reports`
Grain: one row per bug report submitted.
Writer: mode2 router bug report endpoint. Insert-only (status can be updated).
Key columns: `id` uuid PK, `category` text, `description` text, `user_query` text, `llm_response` text, `error_message` text, `tickers_referenced` text[], `query_type` text, `status` text, `resolution` text, `user_id` text, `created_at` timestamptz, `resolved_at` timestamptz.
Chatbot: no access.

### `llm_regression_tests`
Grain: one row per regression test case.
Writer: admin/developer. Upsertable.
Chatbot: no access.

### `user_ticker_lists`
Grain: one row per named ticker list per user.
Writer: mode2 router. Upsertable (ON CONFLICT updates tickers).
Key columns: `user_id` text, `list_name` text, `tickers` text[], `created_at` timestamptz, `updated_at` timestamptz.
Chatbot: read — classifier uses these to expand list references like "my tech names".

### `feature_requests`
Grain: one row per user-submitted feature request.
Writer: mode2 router /request command. Insert-only (status updated by admin).
Key columns: `id` uuid PK, `user_id` text, `session_id` uuid, `request_text` text, `status` text, `priority` text, `admin_notes` text, `created_at` timestamptz.
Chatbot: no access.

### `processing_registry`
Grain: one row per document in the ingestion pipeline.
Writer: WF-01 ingestion scanner. Upsertable.
Key columns: tracks MD5 change detection to avoid reprocessing unchanged docs.
Chatbot: no access.

### `pipeline_runs`
Grain: one row per pipeline execution.
Writer: WF-05 orchestrator. Insert-only.
Chatbot: no access.

### `portfolios`
Grain: one row per portfolio definition.
Writer: manual/admin or `generate_portfolio_trades.py`. Upsertable.
Key columns: `portfolio_id` text, `name` text, `strategy` text, `aum` numeric, `long_exposure` numeric, `short_exposure` numeric, `num_positions` integer, `max_position_pct` numeric, `inception_date` date, `rebalance_frequency` text, `total_trades` integer, `unique_tickers` integer, `status` text.
Note: currently 2 rows (Flagship, Long Only). Referenced by entities.py for portfolio detail views.
Chatbot: indirect — entities.py reads it for portfolio metadata.

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
Grain: one row per ticker per metric per period per firm per estimate_date. Event log table — chatbot never queries directly; use `daily_estimates` instead.
Writer: sellside extraction job (runs after sellside note ingestion). Insert-only.
Chatbot: indirect (via `daily_estimates`). Always presented alongside other estimate sources — never in isolation. Citation label: `[TICKER | Sellside Estimate | Firm | Date]`.
Key columns:
- `id` uuid PK
- `ticker` text
- `firm` text
- `analysts` text[] (array of analyst names at that firm)
- `period` text (e.g. 2026Q1, 2026A)
- `metric` text (revenue | eps | ebitda | etc.)
- `value` numeric
- `unit` text
- `estimate_date` date (when the estimate was made)
- `created_at` timestamptz

---

### `internal_estimates`
Grain: one row per ticker per metric per period per version (PIT). Event log table — chatbot never queries directly; use `daily_estimates` instead.
Writer: model processing job only. Insert-only. Never updated — new estimates are new rows.
Chatbot: indirect (via `daily_estimates`). Citation label: `[TICKER | Internal Estimate | Author | Date]`.
Key columns:
- `id` uuid PK
- `ticker` text
- `period` text
- `metric` text
- `value` numeric
- `unit` text
- `estimate_date` date (when the estimate was made)
- `user_id` uuid FK (analyst whose model produced this estimate)
- `model_version` text
- `created_at` timestamptz

---

### `buyside_estimates`
Grain: one row per ticker per metric per period per analyst per estimate_date. Event log table — chatbot never queries directly; use `daily_estimates` instead.
Writer: vendor ingestion job (daily). Insert-only (preserve historical snapshots).
Chatbot: indirect (via `daily_estimates`). Citation label: `[TICKER | Buyside Estimate | Firm | Date]`.
Key columns:
- `id` uuid PK
- `ticker` text
- `firm` text
- `analyst_name` text (individual analyst name)
- `analyst_person_id` varchar FK → `people.person_id`
- `period` text
- `metric` text
- `value` numeric
- `unit` text
- `estimate_date` date (when the estimate was made)
- `created_at` timestamptz

---

### `consensus_estimates`
Grain: one row per ticker per metric per period per estimate_date. Event log table — chatbot never queries directly; use `daily_estimates` instead.
Writer: vendor ingestion job (daily). Insert-only (preserve historical snapshots).
Chatbot: indirect (via `daily_estimates`). Citation label: `[TICKER | Consensus | Period | Date]`.
Key columns:
- `id` uuid PK
- `ticker` text
- `period` text
- `metric` text
- `value` numeric
- `unit` text
- `estimate_date` date (when the estimate was made)
- `created_at` timestamptz

---

### `daily_estimates`
Grain: one row per ticker per metric per period per source per firm per as_of_date (calendar date).
Writer: `daily_estimates_job.py` (nightly forward-fill from all four log tables). Insert-only.
Chatbot: read. The **only** table the chatbot queries for estimates. All four sources unified. Citation labels vary by source (see WF-09 system prompt).
Key columns:
- `id` uuid PK
- `ticker` text
- `metric` text
- `period` text (e.g. 2026Q1, 2026A)
- `period_start_date` date
- `period_end_date` date
- `source` text (`consensus` | `buyside` | `internal` | `sellside`)
- `firm` text (nullable — NULL for consensus and internal)
- `analyst_name` text (nullable)
- `analyst_person_id` varchar FK → `people.person_id` (nullable)
- `user_id` uuid (nullable — for internal estimates)
- `value` numeric
- `unit` text
- `estimate_date` date (when the estimate was originally made)
- `as_of_date` date (the calendar date this row represents)
- `staleness_days` integer (generated: `as_of_date - estimate_date`)
- `created_at` timestamptz

Unique constraint: `(ticker, metric, period, source, firm, analyst_name, as_of_date)`. `firm` and `analyst_name` are NOT NULL (empty string for sources without them).

Query pattern: `WHERE as_of_date = (SELECT MAX(as_of_date) FROM daily_estimates WHERE ticker = ANY($1))` to get the latest snapshot.

## Estimates architecture (two layers)

**Layer 1 — Event log tables (insert-only):**
- `consensus_estimates`
- `buyside_estimates`
- `internal_estimates`
- `sellside_estimates`

One row per estimate event. `estimate_date`: when the estimate was made. `created_at`: when inserted into DB. Never updated or deleted. Chatbot never queries these directly.

**Layer 2 — Daily pre-calculated:**
- `daily_estimates`

One row per ticker × metric × period × source × firm × as_of_date. Forward-filled nightly by `daily_estimates_job.py`. Chatbot queries only this table.

`staleness_days = as_of_date - estimate_date` (computed column — DB calculates automatically). High staleness = estimate not recently updated.

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
- `portfolio` text ('Flagship' | 'Long Only')
- `side` text (long | short)
- `sector` text
- `industry` text
- `unrealized_pnl` numeric
- `realized_pnl` numeric
- `daily_return` numeric
- `cumulative_return` numeric
- `contribution_to_portfolio` numeric
- `shares_held` numeric
- `market_value` numeric
- `cost_basis` numeric
- `daily_realized_pnl` numeric (P&L from positions closed on THIS date only. 0.0 on days with no closes. NOT cumulative.)
- `ytd_pnl` numeric (year-to-date total P&L from Jan 1 of current year. Includes both unrealized change and realized. Recalculated daily.)
- `itd_pnl` numeric (inception-to-date total P&L since first trade ever. = unrealized_pnl + SUM(all daily_realized_pnl ever for this position))
- `created_at` timestamptz

Portfolio names in the database use Title Case with spaces. The tool layer normalizes lowercase_underscore input to match these values via `PORTFOLIO_MAP` in `retrieval.py`.

## P&L terminology (critical — never mix these)

- `daily_realized_pnl`: TODAY only. Positions closed today. Zero on most days.
- `unrealized_pnl`: Current mark-to-market on ALL open positions. Changes every day with prices.
- `ytd_pnl`: Jan 1 to today. Labeled "YTD P&L".
- `itd_pnl`: Since inception. Labeled "ITD P&L" or "Inception to Date P&L".
- NEVER use "Realized P&L" without a time qualifier. The old `realized_pnl` column was cumulative inception-to-date and was confusingly labeled — it has been superseded by `itd_pnl`.

---

### `portfolio_concentration`
Grain: one row per ticker per portfolio per date.
Writer: `concentration_job` (daily, runs after `pnl_calculation_job`). Insert-only.
Chatbot: read. Used for concentration and exposure queries.
Key columns:
- `id` uuid PK
- `date` date
- `ticker` text
- `portfolio` text ('Flagship' | 'Long Only')
- `side` text (long | short)
- `sector` text
- `industry` text
- `geography` text
- `position_weight` numeric (% of portfolio)
- `sector_weight` numeric
- `industry_weight` numeric
- `geo_weight` numeric
- `market_value` numeric (this position's dollar value: shares * close price)
- `portfolio_market_value` numeric (total dollar value of all positions in this portfolio on this date)
- `is_market_neutral_compliant` bool (Flagship only, NULL for Long Only. Calculated from dollar values: abs(long$ - short$) / total$ < 0.02. Portfolio-level flag applied to all rows for that portfolio + date.)
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
- `portfolio` text ('Flagship' | 'Long Only')
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

### `sessions`
Grain: one row per chat session.
Writer: WF-10 session manager. Sessions created on first message, updated on every turn.
Chatbot: no — chat history is for user reference only, never fed back to LLM as retrieval context.
Key columns:
- `id` uuid PK
- `conversation_id` uuid FK → `conversations`
- `user_id` text (analyst username)
- `rolling_summary` text (compressed history, updated every 10 turns by WF-10)
- `summary_covers_through` integer (turn number through which summary is current)
- `turn_count` integer
- `total_input_tokens` integer
- `total_output_tokens` integer
- `total_cost_usd` numeric
- `title` text (auto-generated after turn 1) — added in migration 025
- `created_at` timestamptz
- `updated_at` timestamptz

Note: `chat_sessions` table was dropped (migration 025). Visibility was moved from sessions to conversations in migration 026 — it belongs at the conversation level since that is the shareable unit.

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
    ↓
daily_estimates_job        — all 4 estimate log tables → daily_estimates (forward-fill)
```
