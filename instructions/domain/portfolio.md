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

## Columns added post-migration

Columns added via `020_alter_daily_pnl_add_columns.sql`:
- `shares_held`: net shares from trade ledger per position
- `market_value`: abs(shares_held * closing_price)
- `cost_basis`: avg_cost_per_share * shares_held

Columns added via `024_alter_daily_pnl_add_pnl_columns.sql`:
- `daily_realized_pnl`: P&L from positions closed on THIS date only. 0.0 on days with no closes. NOT cumulative.
- `ytd_pnl`: year-to-date total P&L from Jan 1 of current year. Includes both unrealized change and realized.
- `itd_pnl`: inception-to-date total P&L since first trade ever. = unrealized_pnl + SUM(all daily_realized_pnl ever)

## P&L terminology (critical — never mix these)

- `daily_realized_pnl`: TODAY only. Positions closed today. Zero on most days.
- `unrealized_pnl`: Current mark-to-market on ALL open positions. Changes every day with prices.
- `ytd_pnl`: Jan 1 to today. Labeled "YTD P&L".
- `itd_pnl`: Since inception. Labeled "ITD P&L" or "Inception to Date P&L".
- NEVER use "Realized P&L" without a time qualifier. The old `realized_pnl` column was cumulative inception-to-date and was confusingly labeled — it has been superseded by `itd_pnl`.

## Fields computed at query time (not stored)

These fields are derived at query time from daily_pnl and portfolio_trades. Do not add them as columns.
- `portfolio_value`: initial_capital + SUM(itd_pnl)
- `total_trades`, `num_buys`, `num_sells`: COUNT from portfolio_trades
- `buy_amount`, `sell_amount`: SUM(shares*price) from portfolio_trades filtered by action

## Functions retained in entities.py / daily_pnl_report.py

`_price_on_date()`, `_load_portfolio_trades()`, `_compute_portfolio_holdings()` are kept intentionally. They handle trade-level detail and YTD capital-flow adjustments not captured in daily_pnl.

---

## portfolio_concentration

Daily concentration metrics. Chatbot source for exposure and weight queries.

Includes `market_value` (position dollar value from daily_pnl), `portfolio_market_value` (total portfolio dollar value), and `is_market_neutral_compliant` flag.

Market neutral compliance:
- Flagship only — Long Only has NULL (no market neutral requirement)
- Calculated from dollar values: `abs(long$ - short$) / total$ < 0.02`
- Dollar values sourced from `daily_pnl.market_value` (shares * close price)
- Portfolio-level flag: same boolean applied to ALL rows for that portfolio + date
- The `concentration_job` calculates this flag daily. If false, it is a data signal — the chatbot can surface it but does not enforce or recommend action.

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
