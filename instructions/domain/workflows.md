# Workflows

Every repeatable, structured output in GoldMine is a workflow. This document defines the workflow framework, the process for adding new workflows, and the full spec for each defined workflow.

---

## Framework

A workflow is a defined process that:
1. Takes validated inputs (ticker, period, user context)
2. Pulls only from vetted database sources
3. Produces a structured output that is stored in its own table
4. Cites every data point used
5. Never fabricates numbers, trends, or explanations

Workflows differ from ad-hoc chatbot queries in that they have a defined output schema, a named output table, and a registry entry. They can be triggered on-demand by a user or scheduled automatically.

### Workflow registry

Every workflow must have a row in `workflow_registry` before it can be executed. Fields:
- `workflow_name` — machine name (e.g. `earnings_preview`)
- `display_name` — human name shown in UI (e.g. "Earnings Preview")
- `description` — one sentence describing what it produces
- `required_inputs` — JSONB (e.g. `{"ticker": "required", "period": "required"}`)
- `output_table` — where output rows are written (e.g. `workflow_outputs_earnings_preview`)
- `trigger_type` — `on_demand`, `scheduled`, or `both`
- `schedule_rule` — if scheduled, the rule (e.g. "7 days before earnings_calendar.report_date for all portfolio tickers")
- `is_active` — bool

### Adding a new workflow

1. Design the output schema (what does a completed run produce?)
2. Create the output table (`workflow_outputs_{name}`)
3. Insert a row into `workflow_registry`
4. Add the workflow spec to this document
5. Implement the execution logic in `backend/app/workflows/{name}.py`
6. Add the workflow name to WF-06 classifier's workflow detection list

### Output table naming

All workflow output tables follow the pattern `workflow_outputs_{workflow_name}`. Every output table must include:
- `id` uuid PK
- `workflow_run_id` uuid FK → `workflow_runs`
- `ticker` text
- `generated_at` timestamptz
- `generated_by` text (user_id or 'scheduler')

---

## Workflow: Earnings Preview

**Status:** IMPLEMENTED (2026-03-20)
**Implementation:** `backend/app/workflows/earnings_preview.py`
**Scheduler:** `scripts/run_scheduled_workflows.py`

**Registry name:** `earnings_preview`
**Trigger:** both (scheduled 7 days before earnings date for all portfolio tickers; on-demand for any ticker in the S&P 500 universe)
**Output table:** `workflow_outputs_earnings_preview`

### Purpose

A full pre-earnings briefing for a single ticker covering the reporting quarter and forward quarter (guidance). Pulls all available data from vetted sources. Never contains investment opinions or explanations of why trends exist — only what the data shows.

### Required inputs

- `ticker` — required
- `reporting_period` — required (e.g. 2026Q1)
- `forward_period` — required (e.g. 2026Q2 — for guidance comparison)

### KPI determination (per-ticker, dynamic)

Key metrics vary by company and change over time. Determination order:
1. Check `workflow_outputs_earnings_preview` for prior runs on this ticker — use `key_kpis` field from most recent prior preview
2. If no prior preview: check `analyst_notes` and `chunks` (doc_type: sellside_note) for this ticker to infer which metrics are discussed most
3. If neither exists: surface a modal to the user requesting manual KPI input before generation proceeds

The `key_kpis` field is always stored in the output and becomes the reference for the next preview.

### Output sections

**Section 1 — Estimates table**

All four estimate sources, side by side, for both reporting quarter and forward quarter:

| Metric | Internal | Buyside | Consensus | Sellside (avg) | Implied move |
|---|---|---|---|---|---|
| [key KPI 1] | cite | cite | cite | cite | calculated |
| [key KPI 2] | cite | cite | cite | cite | calculated |
| EPS | cite | cite | cite | cite | calculated |
| Revenue | cite | cite | cite | cite | calculated |

Implied move = calculated from estimates spread (bull/base/bear scenarios from model_outputs — planned, not yet implemented). No options data required.

Sources: raw log tables (internal_estimates, buyside_estimates, consensus_estimates, sellside_estimates) queried directly by the workflow. The chatbot queries daily_estimates instead.
All four always present. If a source has no estimate for a metric, show "N/A" — never omit the column.

Planned — not yet implemented:
- Implied move calculation from bull/base/bear scenarios (model_outputs)
- Sellside commentary context for estimate narrative (sellside_notes)
- Peer comp context for relative valuation (model_peers)

**Section 2 — Most recent quarter actuals**

Key metrics from last reported quarter. From `financial_metrics`. Cited.
Metrics: Revenue, Gross Profit, Gross Margin %, EBIT, EBITDA, Net Income, EPS (actual vs. prior estimate at time of report if available from `consensus_estimates` historical snapshot).

**Section 3 — Stock price behavior (last 90 days)**

From `stock_history`. Not cited (exempt source).
- Price change % over 90 days
- Key move dates (if available)
- Performance vs. index (S&P 500 from `stock_history`)

**Section 4 — Portfolio position**

From `daily_pnl` and `portfolio_concentration`. Not cited (exempt source).
- Current position size per portfolio (flagship / long_only)
- Side (long / short)
- Position weight % of portfolio
- P&L since inception of position

**Section 5 — Alt data signals**

All available `alt_data` types for this ticker. If no alt data exists for this ticker, section is omitted with a note.
For each data type present:
- Most recent complete quarter value + growth (YoY)
- Partial forward quarter value + growth (with explicit period coverage note, e.g. "17 days into Q1")
- Source vendor cited: `[TICKER | Alt Data | Type | Period]`

**Section 6 — Prior earnings preview reference**

If a prior earnings preview exists for this ticker, include a summary of what KPIs were flagged as important and how the actual results compared to estimates. From `workflow_outputs_earnings_preview` (structured lookup, not vector search).

### Output table schema: `workflow_outputs_earnings_preview`

- `id` uuid PK
- `workflow_run_id` uuid FK → `workflow_runs`
- `ticker` text
- `reporting_period` text
- `forward_period` text
- `key_kpis` text[] (array of metric names used in this preview)
- `estimates_table` jsonb (full estimates comparison, all sources)
- `actuals_section` jsonb
- `price_section` jsonb
- `portfolio_section` jsonb
- `alt_data_section` jsonb
- `prior_preview_reference` jsonb (nullable)
- `generated_at` timestamptz
- `generated_by` text (user_id or 'scheduler')
- `citations` jsonb (full citation trail for every data point used)

---

## Workflow: Financial Model Generation

**Registry name:** `financial_model_generation`
**Trigger:** on-demand only
**Output table:** `workflow_outputs_financial_model` (metadata only — actual model stored in S3)

### Purpose

Generate a standardized 3-statement financial model for a ticker. All models follow the canonical template defined in `instructions/domain/models.md`. One model per ticker — new generation creates a new version, never overwrites.

### Required inputs

- `ticker` — required
- `key_kpis` — required (from prior model, analyst notes, or user input)
- `peers` — from model_peers table (auto-populated if not set, planned)
- `base_assumptions` — revenue growth rates, margin assumptions, discount rate (can be provided by user or defaulted from sector medians in `financial_metrics`)

### Process

1. Pull `financial_metrics` for historical periods (3 years annual + 8 quarters)
2. Pull `consensus_estimates` and `internal_estimates` for forward periods
3. Pull model_peers for this ticker (planned); pull comps from `financial_metrics`
4. Pull prior model version from `model_outputs` if exists (for assumption continuity)
5. If user provided edit instruction (e.g. "change base case 2027 revenue growth to 15%"): read current `model_outputs` assumptions, apply edit, recalculate affected outputs
6. Generate Excel file following canonical template (see `instructions/domain/models.md`)
7. Write Excel to S3 with versioned path: `models/{ticker}/{ticker}_model_v{N}_{date}.xlsx`
8. Run model processing job: extract all structured outputs → insert new rows into `model_outputs` → update `internal_estimates`

### Output table schema: `workflow_outputs_financial_model`

- `id` uuid PK
- `workflow_run_id` uuid FK → `workflow_runs`
- `ticker` text
- `version` text
- `s3_path` text
- `key_kpis` text[]
- `assumptions_snapshot` jsonb (key assumptions used for this version)
- `generated_at` timestamptz
- `generated_by` text

---

## Workflow: Documentation Sync

**Registry name:** `docs_sync`
**Trigger:** both (on-demand via chatbot or CLI; automatically after major build sessions)
**Output table:** `workflow_outputs_docs_sync`

### Purpose

Scans codebase and infrastructure, compares against markdown documentation (data-schema.md, chatbot.md, workflows.md, WF-* architecture docs, CLAUDE.md), reconciles gaps, and produces a sync report. Auto-fixes minor gaps (missing columns, missing project structure entries). Flags anything requiring human judgment with a suggested fix.

### Required inputs

None — the workflow discovers everything by reading the codebase directly.

### Process

1. Query `information_schema.tables` for all public tables; compare against documented tables in `data-schema.md`
2. Import `GOLDMINE_TOOLS` from `tools.py`; compare each tool's data source against `chatbot.md` access map
3. Import `ALT_DATA_KEYWORD_MAP` from `classifier.py`; compare against `get_alt_data` tool enum and `chatbot.md` keyword table
4. Query `workflow_registry` for active workflows; compare against specs in `workflows.md`
5. Read `generator.py`, `classifier.py`, `router.py`; check `chatbot.md` pipeline overview and WF-08/WF-09 docs for stale content
6. Walk `backend/app/` directories; compare against CLAUDE.md Project Structure
7. Check `instructions/skills/` for expected skill files

### Output sections

- `files_checked`: every file read during the sync
- `gaps_found`: all gaps including auto-fixed ones (type: stale_content | missing_entry | wrong_value | needs_human_review)
- `files_updated`: files modified by auto-fix
- `items_needing_human_review`: gaps requiring human action, each with a `suggested_fix`
- `summary`: "{N} gaps found. {N} auto-fixed. {N} need human review."

### Output table schema: `workflow_outputs_docs_sync`

- `id` uuid PK
- `workflow_run_id` uuid FK → `workflow_runs`
- `triggered_by` text
- `started_at` timestamptz
- `completed_at` timestamptz
- `files_checked` text[]
- `gaps_found` jsonb
- `files_updated` text[]
- `items_needing_human_review` jsonb
- `summary` text
- `created_at` timestamptz

---

## Template: Adding a future workflow

When a new workflow is designed, add a section here following this structure:

```
## Workflow: {Display Name}

**Registry name:** {machine_name}
**Trigger:** on_demand | scheduled | both
**Output table:** workflow_outputs_{machine_name}

### Purpose
One paragraph. What does this produce and why does it exist?

### Required inputs
List each input: name, required/optional, source.

### Process
Numbered steps. Which tables are read, in what order, what transformations happen.
Each step cites its data source.

### Output sections
What does the output contain? Be specific about what data populates each section
and which table it comes from.

### Output table schema: workflow_outputs_{machine_name}
Column list with types.
```

Every workflow must follow the core rules:
- Only reads from vetted database sources
- Cites every data point
- Never fabricates or explains — only presents what the data shows
- Produces a stored, attributable output
- Registers in `workflow_registry` before execution
