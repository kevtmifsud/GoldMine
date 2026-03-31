# Chatbot (Mode 2)

Reference for building and extending the Mode 2 AI chat system. Covers data source access, routing rules, retrieval strategy, session rules, cost warning logic, and behavioral constraints.

The chatbot is the primary interface of GoldMine. The database is its memory. Every feature built on top of the chatbot must respect the rules in this document.

---

## Pipeline overview

```
User message
    ↓
WF-06  Query Classifier (Haiku)
       — extracts: query_type, tickers[], fiscal_periods[], topic, estimated_ticker_count
       — no required_sources output — Claude decides retrieval via tool calls
    ↓
WF-07  Ticker Resolver
       — expands aliases, validates tickers against stocks table, no LLM call
    ↓
WF-09  Agentic Response Generator (Sonnet)
       — embeds user query (OpenAI), looks up Q&A library
       — starts Claude with always-loaded tools (5: search_tools, search_documents,
         get_financial_metrics, get_all_estimates, get_daily_pnl)
       — deferred tools (11) discovered on demand via search_tools
       — Claude calls tools as needed; discovered tools added to active set
       — tool results fed back; loop repeats until Claude produces final text
       — streams final response with enforced inline citations
       — system prompt loaded from instructions/domain/WF-09_system_prompt.md
    ↓
WF-10  Session Manager
       — compresses history every 10 turns (Haiku, fire-and-forget)
       — auto-generates session title after first exchange
```

### Tool search architecture

To reduce context token consumption, tools are split into two tiers:

**Always loaded** (sent in every API call):
- `search_tools` — discovers deferred tools by keyword
- `search_documents` — vector search over document chunks
- `get_financial_metrics` — reported company financials
- `get_all_estimates` — forward estimates (all four sources)
- `get_daily_pnl` — portfolio P&L data

**Deferred** (discovered on demand via `search_tools`):
- `get_portfolio_concentration`, `get_portfolio_risk`, `get_trade_requests`
- `get_stock_history`, `get_guidance`, `get_alt_data`
- `get_model_outputs`, `get_workflow_registry`, `run_workflow`, `get_workflow_output`
- `model_edit`

Search uses keyword/substring matching against `_DEFERRED_TOOL_INDEX` in `tools.py`. Falls back to returning all deferred tools if no keywords match.

When adding a new tool, decide which tier it belongs to:
- **Always loaded** if used in >50% of queries or on the critical path
- **Deferred** otherwise — add keywords to `_DEFERRED_TOOL_INDEX`

WF-08 (Retrieval Orchestration) no longer exists as a separate step. The `_query_*` functions in `retrieval.py` are now tool handlers called by `execute_tool()` in `tools.py`. Claude decides which data sources to query via the agentic tool-calling loop in `generator.py`.

Model assignments are stored in `model_config` table, not hardcoded. Hot-swap without redeploy by updating that table.

---

## Data source access map

The chatbot can read from the following sources. It cannot write to any of them.

| Source | Table | Retrieval method | Citation label | Notes |
|---|---|---|---|---|
| Company financials | `financial_metrics` | SQL | `[TICKER | Financials | Period]` | Reported actuals only, never portfolio P&L |
| Earnings transcripts | `chunks` (doc_type: earnings_transcript) | Vector | `[TICKER | Transcript | Period | Speaker]` | |
| SEC filings | `chunks` (doc_type: 10-K, 10-Q, 8-K) | Vector | `[TICKER | Filing | Type | Section]` | |
| Internal analyst notes | `analyst_notes` + `chunks` (doc_type: analyst_note) | Vector | `[TICKER | Analyst Note | Author | Date]` | Our team's notes only |
| External buyside notes | `buyside_notes` + `chunks` (doc_type: buyside_note) | Vector | `[TICKER | Buyside Note | Firm | Date]` | External buyside firms only |
| Sellside notes | `sellside_notes` + `chunks` (doc_type: sellside_note) | Vector | `[TICKER | Sellside Note | Firm | Date]` | |
| All estimates (all sources) | `daily_estimates` | SQL (most recent as_of_date) | Consensus: `[TICKER | Consensus | Period | Date]`, Buyside/Sellside: `[TICKER | {firm} | {analyst} | Period]`, Internal: `[TICKER | Internal | {analyst} | Period]` | Single query point for all four estimate sources. Returns consensus, buyside, internal, and sellside in one query grouped by source and firm. `staleness_days` column shows how many days since estimate was last updated. Layer 1 log tables (`consensus_estimates`, `buyside_estimates`, `internal_estimates`, `sellside_estimates`) are never queried directly by the chatbot. |
| Guidance | `guidance` | SQL | `[TICKER | Guidance | Period | Date]` | |
| Portfolio positions/P&L | `daily_pnl` | SQL | exempt — no citation required | |
| Portfolio concentration | `portfolio_concentration` | SQL | exempt | |
| Portfolio risk | `portfolio_risk` | SQL | exempt | |
| Trade requests | `trade_requests` | SQL (read-only) | exempt | |
| Market prices | `stock_history` | SQL | exempt — no citation required | |
| Alt data signals | `alt_data` | SQL via get_alt_data (per-signal limits, no aggregation) | `[TICKER | Alt Data | SIGNAL_NAME | DATE]` | Currently available: CMG, DPZ, SBUX (restaurant signals). Signals: credit_card_sss_yoy, credit_card_txn_yoy, credit_card_spv_yoy, foot_traffic_yoy, app_downloads_yoy, web_traffic_yoy, reservations_yoy (CMG/SBUX only), job_postings_yoy. NEVER use GROUP BY or aggregate functions on alt_data. |
| Model outputs | `model_outputs` | SQL (most recent version) | `[TICKER | Model | Date]` | |
| Prior workflow outputs | `workflow_outputs_earnings_preview` (and others) | SQL (structured lookup) | per workflow type | Not vector search |
| Workflow registry | `workflow_registry` | SQL | — | Runtime lookup for workflow execution |

The chatbot does NOT have access to: `sessions` (as retrieval context), `api_cost_events`, raw S3 Excel files, `user_profiles` (beyond display_name for attribution).

---

## Routing rules

Claude decides which tools to call during the agentic loop. The tool descriptions in `tools.py` encode routing rules. Multi-source queries are the norm — Claude calls multiple tools in a single turn.

### Single-dimension routing

| Query intent | Primary source |
|---|---|
| Revenue, margins, EPS, balance sheet, cash flow | `financial_metrics` |
| What management said on a call | `chunks` (earnings_transcript) |
| Risk factors, MD&A, business description | `chunks` (10-K, 10-Q) |
| Our team's views on a name | `analyst_notes` — NEVER include sellside in this |
| External buyside views on a name | `buyside_notes` — NEVER include internal analyst notes |
| Sellside views on a name | `sellside_notes` — NEVER include internal or buyside notes |
| Portfolio positions, P&L, concentration | `daily_pnl`, `portfolio_concentration` — NEVER pull financial_metrics for P&L |
| Stock price, performance vs index | `stock_history` — self-contained, no secondary source |
| Alt data signals | `alt_data` via get_alt_data — credit card, foot traffic, app downloads, web traffic, reservations, job postings |
| Forward estimates (all) | `daily_estimates` — always returns all four sources (consensus, buyside, internal, sellside) in one query |
| Model assumptions or scenario outputs | `model_outputs` (most recent version) |

### Multi-source routing

When a query explicitly requires multiple dimensions, Claude calls multiple tools. Examples:

- "How does AAPL smartphone revenue correlate to credit card spend in California?" → `financial_metrics` + `alt_data` (credit_card)
- "What is AAPL Q4 revenue estimate?" → `daily_estimates` (returns all four sources in one query)
- "Earnings preview for NVDA" → triggers earnings_preview workflow (see workflows.md)
- "Top 5 holdings by unrealized gain" → `daily_pnl` only
- "What restaurants show highest YoY credit card growth and have spoken about it on earnings calls?" → `alt_data` (credit_card) + `chunks` (earnings_transcript) — this is a large query, apply cost warning check

### Source isolation rules (critical)

These rules are encoded in tool descriptions and the system prompt (WF-09_system_prompt.md):

1. **Portfolio P&L queries** route only to `daily_pnl` / `portfolio_concentration` / `portfolio_risk`. Never pull `financial_metrics` or `stock_history` as a secondary source for portfolio queries.
2. **Internal analyst note queries** never include `sellside_notes` or `buyside_notes`.
3. **Sellside queries** never include `analyst_notes` or `buyside_notes`.
4. **Alt data** always queries with explicit `data_type` filter. Never run `SELECT * FROM alt_data WHERE ticker = X` without a type.
5. **Estimates** — any query about forward estimates always retrieves all four estimate sources (`internal`, `buyside`, `consensus`, `sellside`). Never present a single estimate source in isolation.
6. **Portfolio separation** — when portfolio data is returned for multiple portfolios, always present each portfolio in a separate labeled section. Never aggregate across portfolios. This applies to all portfolio tool results: daily_pnl, portfolio_concentration, portfolio_risk. Results are ordered by portfolio first when querying all portfolios.

---

## Alt data keyword mapping

WF-06 maps natural language terms to `alt_data.data_type` values:

| Query terms | data_type filter |
|---|---|
| credit card, card data, transaction data, consumer spend, CC data, card trends, card spend, second measure | `credit_card` |
| foot traffic, store visits, location data, placer | `foot_traffic` |
| web traffic, website visits, web visits, site traffic, online traffic, similarweb | `web_traffic` |
| app downloads, download data, app installs, mobile downloads, app activity, sensor tower | `app_downloads` |
| reservations, opentable, reservation trends | `reservations` |
| job postings, hiring data, revelio, employment data | `job_postings` |
| google trends, search trends, search data, search interest | `google_trends` |
| email receipts, receipt data, email data, purchase receipts | `email_receipts` |
| medical claims, claims data, healthcare data, Rx data | `medical_claims` |

If the user mentions an alt data type not in this list, surface a message that this data type is not yet available rather than querying without a filter.

---

## Retrieval strategy by source type

**Vector search sources** (chunks table): use pgvector cosine similarity with `embedding` column (OpenAI text-embedding-3-large, 1536 dimensions). Filter by `doc_type` always. Filter by `ticker` when the query is ticker-specific. Retrieve top-K chunks (K varies by query complexity — single name: K=5-10, multi-name: K=3-5 per ticker).

**SQL sources** (structured tables): direct parameterized queries. Always use indexed columns in WHERE clauses (`ticker`, `period`, `as_of_date`, `date`). Never SELECT * without LIMIT. For `internal_estimates`, `model_outputs` — always use DISTINCT ON pattern to get most recent version.

**Hybrid queries** (e.g. estimates comparison): Claude calls multiple tools in the same turn. Tool results are fed back as context for the final response.

**Cross-source joins**: join key between most sources is `ticker`. Period alignment for alt data (weekly/monthly) to financials (quarterly) is pre-calculated in the `alt_data` table — never ask the LLM to aggregate or align periods.

---

## Cost warning logic

Trigger a cost warning chat message before executing when estimated chunk retrieval exceeds ~200 chunks. This occurs roughly when:
- Query spans 10+ tickers AND requires at least one vector search source
- Any query spanning 30+ tickers regardless of source type
- Full universe queries (all 503 tickers) — always warn

Warning message format (in-chat, before execution):
> "This query spans {N} tickers across {sources}. Estimated cost: ~${est}. Run it?"

Cost estimation: use historical averages from `api_cost_events` grouped by query shape (ticker_count bucket × source_count). Fall back to conservative fixed estimates per source per ticker until enough history exists.

No hard blocks. No PM approval gate. User confirms or cancels in chat.

---

## Workflow execution

When WF-06 classifies a query as a workflow request (e.g. "run earnings preview for AAPL"):

1. Look up `workflow_registry` by `workflow_name` to get `required_inputs`, `output_table`, `trigger_type`
2. Validate required inputs are present (ticker, period, etc.)
3. If first-time generation for this ticker and no KPIs can be found in prior previews or notes → surface modal asking user to input key KPIs before proceeding
4. Insert a row into `workflow_runs` with `status='pending'`
5. Execute workflow (see `instructions/domain/workflows.md` for each workflow spec)
6. Write output to the workflow's `output_table`
7. Update `workflow_runs` row with `status='completed'`, `cost_usd`, `output_id`

Scheduled workflows (e.g. earnings preview 7 days before report date) follow the same steps with `triggered_by='scheduler'`.

---

## Session rules

**Retrieval context:** the chatbot uses `analyst_notes`, `buyside_notes`, `sellside_notes`, `chunks`, and structured tables as context. It does NOT use `sessions` as retrieval context — conversation history is for user reference only, never fed back to the LLM.

**Prior workflow outputs:** when a user asks about a ticker and a prior workflow output exists (e.g. a previous earnings preview), surface it via structured SQL lookup — not vector search.

**Session visibility:** `sessions.visibility` defaults to `private`. Users can set their own sessions to `public`. Admin users (`is_admin=true`) can read all sessions. Visibility is enforced at the API layer, not the LLM layer.

**Session storage:** every session is retained permanently. No hard deletes. WF-10 compresses message history every 10 turns.

---

## Read-only constraint

The chatbot reads from source tables and writes only to output tables. This is an architectural constraint enforced at the FastAPI route level.

**Chatbot can write to:** `workflow_outputs_*` tables, `workflow_runs`, `sessions`, `api_cost_events`

**Chatbot cannot write to:** any source table (`financial_metrics`, `analyst_notes`, `portfolio_trades`, `internal_estimates`, `alt_data`, etc.)

When building new API routes: source table endpoints exposed to the chatbot must be GET-only. Do not expose DELETE or PATCH to the chatbot layer. Any request that sounds like a data mutation ("update my estimate", "delete that note", "change my position") must be declined by WF-09 with a message directing the user to the data management interface.
