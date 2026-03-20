# Financial models

Canonical template, versioning rules, and processing job spec for GoldMine financial models.

---

## Principles

- One model per ticker at any time (current version)
- Every edit or regeneration creates a new version — never overwrites
- The LLM never reads raw Excel files — it reads `model_outputs` (structured data)
- The Excel file in S3 is an output artifact, not a source of truth
- `internal_estimates` and price targets are always powered by the model processing job
- All models follow the canonical template below — no structural deviation

---

## Versioning

S3 path: `models/{ticker}/{ticker}_model_v{N}_{YYYY-MM-DD}.xlsx`

Version N increments on every new generation or edit. The model processing job always reads the highest version number for a given ticker.

`model_outputs` rows carry a `version` field. The chatbot always queries the most recent version:
```sql
SELECT DISTINCT ON (ticker, sheet, metric, period, scenario)
    *
FROM model_outputs
ORDER BY ticker, sheet, metric, period, scenario, as_of_date DESC
```

Historical versions are never deleted. Analysts and admins can reference prior versions by date.

---

## Canonical model template

All models contain these sheets in this order. Sheet names are exact — the model processing job locates data by sheet name.

### Sheet 1: ASSUMPTIONS

Single source of truth for all model drivers. The LLM reads and edits this sheet when processing user edit requests.

Structure: one row per assumption, columns for Base / Bull / Bear scenario values.

Required assumption rows:
- Revenue growth rate (by year, quarterly where available)
- Revenue by segment (if applicable — populate from `financial_metrics` history)
- Gross margin %
- R&D as % of revenue
- S&M as % of revenue
- G&A as % of revenue
- EBITDA margin %
- Effective tax rate
- D&A as % of revenue
- Capex as % of revenue
- Days sales outstanding
- Days inventory outstanding
- Days payable outstanding
- Share count (basic + diluted, annual)
- WACC (for DCF)
- Terminal growth rate (for DCF)

Period columns: 4 historical annual + 3 forward annual (base/bull/bear each), 4 historical quarterly + 4 forward quarterly (base only for quarterly).

---

### Sheet 2: INCOME_STATEMENT

Derived from ASSUMPTIONS. No hardcoded values — all cells reference ASSUMPTIONS.

Required rows:
- Revenue (total)
- Revenue by segment (if applicable)
- Cost of Revenue
- Gross Profit
- Gross Margin %
- R&D
- S&M
- G&A
- Total Operating Expenses
- EBIT
- EBIT Margin %
- D&A
- EBITDA
- EBITDA Margin %
- Interest Expense
- Other Income / (Expense)
- Pre-tax Income
- Income Tax
- Net Income
- Net Margin %
- Shares Outstanding (basic)
- Shares Outstanding (diluted)
- EPS (basic)
- EPS (diluted)

Periods: 4 historical annual + 3 forward annual × 3 scenarios, 4 historical quarterly + 4 forward quarterly (base scenario).
Historical values populated from `financial_metrics`.

---

### Sheet 3: BALANCE_SHEET

Required rows:
- Cash & Equivalents
- Accounts Receivable
- Inventory
- Other Current Assets
- Total Current Assets
- PP&E (net)
- Intangibles & Goodwill
- Other Long-term Assets
- Total Assets
- Accounts Payable
- Short-term Debt
- Other Current Liabilities
- Total Current Liabilities
- Long-term Debt
- Other Long-term Liabilities
- Total Liabilities
- Common Equity
- Retained Earnings
- Total Shareholders' Equity
- Total Liabilities + Equity

Same period structure as INCOME_STATEMENT.

---

### Sheet 4: CASH_FLOW

Required rows:
- Net Income
- D&A
- Stock-based Compensation
- Change in Accounts Receivable
- Change in Inventory
- Change in Accounts Payable
- Other Working Capital Changes
- Operating Cash Flow
- Capex
- Free Cash Flow
- FCF Margin %
- Acquisitions
- Other Investing Activities
- Net Cash from Investing
- Debt Issuance / (Repayment)
- Share Repurchases
- Dividends
- Net Cash from Financing
- Net Change in Cash
- Beginning Cash
- Ending Cash

Same period structure.

---

### Sheet 5: VALUATION

DCF section (base case only):
- Projection period FCF (5 years forward, from CASH_FLOW)
- Terminal value (Gordon Growth, using WACC and terminal growth rate from ASSUMPTIONS)
- Enterprise value
- Net debt (from BALANCE_SHEET)
- Equity value
- Implied share price (base / bull / bear — bull/bear use sensitivity on WACC ±50bps and terminal growth ±50bps)
- Current price (from `stock_history`)
- Upside / downside %

Comps section:
- Peer set from `model_peers` (5 peers, auto-populated from `stocks` by sector + industry)
- Metrics pulled from `financial_metrics` for each peer: EV/EBITDA (NTM), P/E (NTM), EV/Sales (NTM), FCF yield
- Subject company implied multiples at current price
- Premium / discount to peer median

Price target summary: implied price per scenario (bull / base / bear) from DCF + a multiples-derived target. This populates `internal_estimates` for price target metric.

---

### Sheet 6: KPIs

Ticker-specific. Contains the key operating metrics that matter for this name.

Structure: same period layout as financial sheets. One row per KPI.

KPIs are determined by:
1. Prior `workflow_outputs_earnings_preview.key_kpis` for this ticker (most recent)
2. Analyst notes and sellside notes (inferred from most-discussed metrics)
3. User input (first-time generation or explicit update)

Example KPIs by sector:
- SaaS: ARR, Net Revenue Retention, CAC Payback, Seats/MAUs
- Retail/Consumer: Same-store sales, Units, ASP, Store count
- Financials: NIM, Loan growth, NPL ratio
- Healthcare: Patient volume, ARPU, Rx fills
- Advertising: Impressions, CPM, ARPU

KPIs feed the earnings preview estimates table (Section 1 of earnings preview).

---

### Sheet 7: SCENARIOS

Summary sheet. One block per scenario (base / bull / bear).

Each block shows key output metrics side by side across all forecast periods:
- Revenue
- Revenue growth %
- EBITDA
- EBITDA margin %
- EPS
- FCF
- Implied price target
- [Ticker-specific KPIs from KPIs sheet]

This sheet is what the chatbot primarily reads when answering questions about model scenarios. The model processing job extracts this sheet first.

---

## Model processing job

Runs daily (or triggered immediately on new upload / LLM edit).

Steps:
1. Identify most recent Excel version per ticker in S3
2. Parse ASSUMPTIONS sheet → write to `model_outputs` (sheet='assumptions')
3. Parse SCENARIOS sheet → write to `model_outputs` (sheet='scenarios') — base/bull/bear rows
4. Parse INCOME_STATEMENT, BALANCE_SHEET, CASH_FLOW → write to `model_outputs`
5. Parse KPIs sheet → write to `model_outputs` (sheet='kpis')
6. Parse VALUATION → extract price targets per scenario → upsert `internal_estimates` (metric='price_target')
7. Extract forward period estimates from SCENARIOS → upsert `internal_estimates` for revenue, EPS, EBITDA, FCF, and KPI metrics

All writes to `model_outputs` use the new version number + today's `as_of_date`. Old version rows are never touched.

---

## LLM model edit flow

When user sends an edit instruction (e.g. "change base case 2027 revenue growth to 15%"):

1. WF-06 classifies as `model_edit` query type for the resolved ticker
2. System reads current `model_outputs` for that ticker (most recent version, ASSUMPTIONS sheet)
3. LLM receives: full assumptions table (current values) + user edit instruction
4. LLM outputs: updated assumptions table with edit applied + recalculated affected outputs
5. New Excel written to S3 (version N+1)
6. Model processing job triggered immediately (not waiting for nightly run)
7. New rows inserted to `model_outputs` and `internal_estimates`

The LLM never reads raw Excel. It only reads structured `model_outputs` data and generates structured output that the processing job converts back to Excel.

---

## Peer set management

Initial population: 5 peers per ticker from `stocks` table, same `sector` AND `industry`.
Stored in `model_peers` (`ticker`, `peer_ticker`, `created_by`).

Analysts can update peer sets through the data management interface (not the chatbot).
The chatbot reads `model_peers` to know which peers to pull for the VALUATION comps table.
If fewer than 5 peers exist in the same sector+industry, expand to sector-only match to fill the set.
