# DS-01: Structured Financial Data — CSV Source

## Purpose

This document describes the structured financial data source — a set of CSVs stored in Google Drive containing clean financial figures across all tickers. This data source is entirely separate from the text document pipeline (WF-01 through WF-05). It does not go through chunking or embedding. It feeds directly into the structured query layer that Mode 2 uses to answer numerical questions.

---

## Current Files

Located in Google Drive under `/structured_data/`:

| File | Description |
|---|---|
| `quarterly_income_statement.csv` | Revenue, gross profit, operating income, net income, EPS — by quarter |
| `annual_income_statement.csv` | Same fields — by fiscal year |
| `quarterly_balance_sheet.csv` | Assets, liabilities, equity, debt — by quarter |
| `annual_balance_sheet.csv` | Same fields — by fiscal year |
| `quarterly_cash_flows.csv` | Operating, investing, financing cash flows, capex, FCF — by quarter |
| `annual_cash_flows.csv` | Same fields — by fiscal year |

---

## Data Structure

Each CSV contains data for all tickers in a single file. Rows are differentiated by ticker. The expected column structure for each file is:

**All files must include at minimum:**

| Column | Format | Example |
|---|---|---|
| `ticker` | Uppercase string | `AAPL` |
| `fiscal_period` | `Q{N}_{YYYY}` for quarterly, `FY{YYYY}` for annual | `Q4_2024` or `FY2024` |
| `fiscal_period_end_date` | `YYYY-MM-DD` | `2024-12-31` |
| [metric columns] | Numeric, in reported currency units | `119575` (millions) |

**Fiscal period format is a hard requirement.** The `fiscal_period` value in these CSVs must exactly match the fiscal period component in transcript filenames (e.g., a CSV row with `fiscal_period = Q4_2024` must correspond to the transcript file `AAPL_Q4_2024.txt`). Any mismatch breaks Mode 2's ability to join financial figures with transcript context.

---

## How This Data Is Used in Mode 2

When a user asks a numerical question — revenue, margins, EPS, debt levels, capex — Mode 2 queries this structured data directly without involving the LLM or the vector database. This is fast, cheap, and precise.

When a user asks a hybrid question — "what did management say about the margin compression last quarter?" — Mode 2 uses the structured data to identify the relevant period and figures, then retrieves the corresponding transcript chunks from the vector database to provide the narrative context.

The structured data and the transcript embeddings are complementary. Neither alone is as powerful as both together.

---

## Tickers Master Table

A tickers master table should be derived from the structured CSVs and stored in Supabase. This is a reference table listing every ticker the platform covers along with categorical attributes used for filtering and grouping in Mode 2.

**Recommended schema:**

```sql
CREATE TABLE tickers (
    ticker          VARCHAR(20) PRIMARY KEY,
    company_name    TEXT,
    sector          VARCHAR(100),
    industry        VARCHAR(100),
    market_cap_tier VARCHAR(20),  -- large_cap / mid_cap / small_cap
    country         VARCHAR(50),
    currency        VARCHAR(10),
    first_seen_at   TIMESTAMP DEFAULT NOW(),
    is_active       BOOLEAN DEFAULT TRUE
);
```

Populate this table initially by extracting the distinct ticker values from the CSVs and enriching with sector/industry data. This table becomes the basis for peer group comparisons and sector-level queries in Mode 2.

---

## Loading CSVs Into Supabase

The structured financial data should be loaded into Supabase tables so Mode 2 can query it with SQL rather than parsing CSVs at runtime. CSVs are fine for storage and as the source of truth, but SQL queries against a database table are significantly faster and more flexible.

**Recommended Supabase tables:**

```sql
CREATE TABLE income_statement (
    ticker              VARCHAR(20) NOT NULL,
    fiscal_period       VARCHAR(20) NOT NULL,
    fiscal_period_end   DATE,
    period_type         VARCHAR(10) CHECK (period_type IN ('quarterly', 'annual')),
    revenue             NUMERIC,
    gross_profit        NUMERIC,
    operating_income    NUMERIC,
    net_income          NUMERIC,
    eps_diluted         NUMERIC,
    gross_margin        NUMERIC,
    operating_margin    NUMERIC,
    net_margin          NUMERIC,
    created_at          TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (ticker, fiscal_period, period_type)
);

CREATE TABLE balance_sheet (
    ticker              VARCHAR(20) NOT NULL,
    fiscal_period       VARCHAR(20) NOT NULL,
    fiscal_period_end   DATE,
    period_type         VARCHAR(10) CHECK (period_type IN ('quarterly', 'annual')),
    total_assets        NUMERIC,
    total_liabilities   NUMERIC,
    total_equity        NUMERIC,
    total_debt          NUMERIC,
    cash_and_equivalents NUMERIC,
    created_at          TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (ticker, fiscal_period, period_type)
);

CREATE TABLE cash_flows (
    ticker                  VARCHAR(20) NOT NULL,
    fiscal_period           VARCHAR(20) NOT NULL,
    fiscal_period_end       DATE,
    period_type             VARCHAR(10) CHECK (period_type IN ('quarterly', 'annual')),
    operating_cash_flow     NUMERIC,
    investing_cash_flow     NUMERIC,
    financing_cash_flow     NUMERIC,
    capital_expenditures    NUMERIC,
    free_cash_flow          NUMERIC,
    created_at              TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (ticker, fiscal_period, period_type)
);

CREATE INDEX idx_income_ticker   ON income_statement (ticker);
CREATE INDEX idx_balance_ticker  ON balance_sheet (ticker);
CREATE INDEX idx_cashflow_ticker ON cash_flows (ticker);
```

**Loading process:** CSVs can be loaded into these tables directly via the Supabase dashboard (**Table Editor → Import CSV**) or programmatically. When new CSV data is delivered, upsert rows using the primary key `(ticker, fiscal_period, period_type)` to handle updates without creating duplicates.

---

## Key Considerations

**CSVs are the source of truth, Supabase tables are the query layer.** Always update the CSV first, then reload into Supabase. Never edit the Supabase tables directly.

**Fiscal period format discipline.** Before loading any CSV data, audit the `fiscal_period` column across all files to ensure the format is consistent (`Q4_2024`, not `Q4-2024`, `2024-Q4`, or `4Q24`). Similarly audit transcript filenames. Inconsistencies here are the single most likely cause of broken Mode 2 cross-source queries.

**Currency and units.** Document the currency and unit scale (e.g., USD millions) for each metric column. This is easy to overlook but critical when Mode 2 surfaces figures to users. Store this as a comment in the table definition or a separate metadata table.

**New data deliveries.** When updated CSVs arrive from your data provider, the load process should be upsert-based — update existing rows, insert new ones. A full truncate-and-reload is acceptable if the CSV always contains the complete historical dataset.
