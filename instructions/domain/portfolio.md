# Portfolio & risk

Reference for the portfolio data pipeline, derivative tables, and chatbot access rules for portfolio data.

---

## Data flow

```
PM submits trade request (UI)
    → trade_requests (real-time, status: pending)

EOD: trade_completed_job
    → moves executed trade_requests from prior day → portfolio_trades

pnl_calculation_job (runs after trade_completed_job)
    → portfolio_trades → daily_pnl

concentration_job (runs after pnl_calculation_job)
    → portfolio_trades → portfolio_concentration

risk_job (runs after concentration_job)
    → portfolio_concentration + stock_betas → portfolio_risk
```

All derivative tables are insert-only daily snapshots. Historical state is always preserved. Never update or delete rows in `daily_pnl`, `portfolio_concentration`, or `portfolio_risk`.

---

## portfolio_trades (existing)

The raw ledger. Source of truth for all position and P&L calculations.
Columns: `date`, `ticker`, `action` (buy | sell), `shares`, `price`, `portfolio` (flagship | long_only), `side` (long | short).
Written by `trade_completed_job` only. Insert-only.

---

## trade_requests

Staging table for PM trade requests before execution.
Input format: `target_pct` — all trade sizes expressed as % of total fund AUM.
PMs convert dollar or share amounts to % before submitting. This keeps the input normalized across portfolios of different sizes.

Status flow: `pending` → `executed` (by trade_completed_job) | `cancelled` (by PM)

Chatbot access: read-only. Can display pending and historical requests. Cannot create, update, or cancel requests.

---

## daily_pnl

Pre-calculated daily P&L. Chatbot primary source for all portfolio queries.

Grain: one row per ticker per portfolio per side per sector per date.
This single grain supports all roll-up levels without separate tables:
- Total portfolio: `WHERE date = X AND portfolio = Y`, sum all rows
- By side: add `GROUP BY side`
- By sector: add `GROUP BY sector`
- By sector + side: `GROUP BY sector, side` (e.g. "Software Longs")
- By position: `WHERE ticker = X`

Never pull `financial_metrics` to answer portfolio P&L questions. `daily_pnl` is self-contained.

---

## portfolio_concentration

Daily concentration metrics. Chatbot source for exposure and weight queries.

Includes `is_market_neutral_compliant` flag for flagship portfolio. Flagship constraint: long $ exposure must equal short $ exposure within a defined tolerance (e.g. ±2%). The `concentration_job` calculates this flag. If the flag is false, it is a data signal — the chatbot can surface it but does not enforce or recommend action.

---

## portfolio_risk

Daily beta exposures. Chatbot source for risk queries.
Derived from `portfolio_concentration` joined with `stock_betas`.
Factor exposures beyond beta are not implemented — risk queries are answered via sector/industry/geography concentration until factor data is available.

---

## Chatbot access rules for portfolio data

1. Portfolio queries route to `daily_pnl`, `portfolio_concentration`, `portfolio_risk`, and `trade_requests` only
2. Never mix portfolio tables with `financial_metrics` — reported financials and portfolio P&L are separate concepts
3. `stock_history` is not a secondary source for portfolio queries — `daily_pnl` already incorporates price
4. All portfolio tables are exempt from inline citation — no citation markers needed in responses
5. `trade_requests` is read-only for the chatbot — never write to it

---

## Adding a new portfolio metric

When a new concentration or risk metric needs to be tracked:
1. Add the column to the appropriate derivative table schema in `instructions/domain/data-schema.md`
2. Update the relevant calculation job to populate it
3. Add it to this document under the relevant table section
4. Do not create a new table unless the grain is fundamentally different
