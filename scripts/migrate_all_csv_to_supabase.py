#!/usr/bin/env python3
"""One-time migration: create 9 Supabase tables and bulk-insert from CSV files.

Creates: stocks, people, portfolios, portfolio_trades, stock_history,
         stock_betas, earnings_calendar, sec_filings, transcripts_list

Drops the old `tickers` table after migration.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

csv.field_size_limit(sys.maxsize)

DATABASE_URL = "postgresql://postgres:sC.g6Wf#9h.Bf_f@db.ybjvfeevaxujenwvoewg.supabase.co:5432/postgres"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "structured"


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

CREATE_TABLES_SQL = """
-- stocks (replaces tickers)
CREATE TABLE IF NOT EXISTS stocks (
    ticker              VARCHAR(20) PRIMARY KEY,
    company_name        TEXT,
    sector              VARCHAR(100),
    industry            VARCHAR(200),
    market_cap_b        VARCHAR(20),
    pe_ratio            VARCHAR(20),
    price               VARCHAR(20),
    "52w_high"          VARCHAR(20),
    "52w_low"           VARCHAR(20),
    dividend_yield      VARCHAR(20),
    eps                 VARCHAR(20),
    revenue_b           VARCHAR(20),
    country             VARCHAR(50),
    exchange            VARCHAR(50),
    address             TEXT,
    city                VARCHAR(100),
    phone               VARCHAR(50),
    zip                 VARCHAR(20),
    long_business_summary TEXT,
    full_time_employees VARCHAR(20),
    web_site            TEXT,
    report_date         VARCHAR(20)
);

-- people
CREATE TABLE IF NOT EXISTS people (
    person_id           VARCHAR(20) PRIMARY KEY,
    name                TEXT,
    title               TEXT,
    organization        TEXT,
    type                VARCHAR(50),
    tickers             TEXT,
    age                 VARCHAR(10),
    born                VARCHAR(20),
    pay                 VARCHAR(30),
    exercised           VARCHAR(30),
    unexercised         VARCHAR(30)
);

-- portfolios
CREATE TABLE IF NOT EXISTS portfolios (
    portfolio_id        VARCHAR(20) PRIMARY KEY,
    name                VARCHAR(100),
    strategy            TEXT,
    aum                 VARCHAR(30),
    long_exposure       VARCHAR(30),
    short_exposure      VARCHAR(30),
    num_positions       VARCHAR(10),
    max_position_pct    VARCHAR(10),
    inception_date      VARCHAR(20),
    rebalance_frequency VARCHAR(50),
    total_trades        VARCHAR(10),
    unique_tickers      VARCHAR(10),
    status              VARCHAR(20)
);

-- portfolio_trades
CREATE TABLE IF NOT EXISTS portfolio_trades (
    date                VARCHAR(20) NOT NULL,
    ticker              VARCHAR(20) NOT NULL,
    action              VARCHAR(10) NOT NULL,
    shares              VARCHAR(20),
    price               VARCHAR(20),
    portfolio           VARCHAR(100) NOT NULL,
    side                VARCHAR(10),
    PRIMARY KEY (date, ticker, portfolio, action)
);
CREATE INDEX IF NOT EXISTS idx_pt_ticker ON portfolio_trades (ticker);
CREATE INDEX IF NOT EXISTS idx_pt_portfolio ON portfolio_trades (portfolio);
CREATE INDEX IF NOT EXISTS idx_pt_date ON portfolio_trades (date);

-- stock_history
CREATE TABLE IF NOT EXISTS stock_history (
    date                VARCHAR(20) NOT NULL,
    ticker              VARCHAR(20) NOT NULL,
    close               VARCHAR(20),
    eps_estimate        VARCHAR(20),
    eps_actual          VARCHAR(20),
    PRIMARY KEY (date, ticker)
);
CREATE INDEX IF NOT EXISTS idx_sh_ticker ON stock_history (ticker);
CREATE INDEX IF NOT EXISTS idx_sh_date ON stock_history (date);

-- stock_betas
CREATE TABLE IF NOT EXISTS stock_betas (
    ticker              VARCHAR(20) PRIMARY KEY,
    beta                VARCHAR(20)
);

-- earnings_calendar
CREATE TABLE IF NOT EXISTS earnings_calendar (
    ticker              VARCHAR(20) NOT NULL,
    report_date         VARCHAR(20) NOT NULL,
    time                VARCHAR(20),
    fiscal_quarter_ending VARCHAR(20),
    PRIMARY KEY (ticker, report_date)
);

-- sec_filings
CREATE TABLE IF NOT EXISTS sec_filings (
    accession_number    VARCHAR(50) PRIMARY KEY,
    symbol              VARCHAR(20),
    cik                 VARCHAR(20),
    company_name        TEXT,
    form_type           VARCHAR(20),
    form_type_description TEXT,
    filing_date         VARCHAR(20),
    report_date         VARCHAR(20),
    acceptance_date_time TEXT,
    filing_url          TEXT,
    primary_document    TEXT
);
CREATE INDEX IF NOT EXISTS idx_sf_symbol ON sec_filings (symbol);

-- transcripts_list
CREATE TABLE IF NOT EXISTS transcripts_list (
    transcripts_id      VARCHAR(100) PRIMARY KEY,
    symbol              VARCHAR(20),
    fiscal_year         VARCHAR(10),
    fiscal_quarter      VARCHAR(10),
    report_date         VARCHAR(20),
    transcripts         TEXT
);
CREATE INDEX IF NOT EXISTS idx_tl_symbol ON transcripts_list (symbol);
"""


# ---------------------------------------------------------------------------
# Table configs: (table_name, csv_filename, column_order, pk_columns)
# ---------------------------------------------------------------------------

TABLES = [
    (
        "stocks",
        "stocks.csv",
        ["ticker", "company_name", "sector", "industry", "market_cap_b",
         "pe_ratio", "price", "52w_high", "52w_low", "dividend_yield",
         "eps", "revenue_b", "country", "exchange", "address", "city",
         "phone", "zip", "long_business_summary", "full_time_employees",
         "web_site", "report_date"],
    ),
    (
        "people",
        "people.csv",
        ["person_id", "name", "title", "organization", "type", "tickers",
         "age", "born", "pay", "exercised", "unexercised"],
    ),
    (
        "portfolios",
        "portfolios.csv",
        ["portfolio_id", "name", "strategy", "aum", "long_exposure",
         "short_exposure", "num_positions", "max_position_pct",
         "inception_date", "rebalance_frequency", "total_trades",
         "unique_tickers", "status"],
    ),
    (
        "portfolio_trades",
        "portfolio_trades.csv",
        ["date", "ticker", "action", "shares", "price", "portfolio", "side"],
    ),
    (
        "stock_history",
        "stock_history.csv",
        ["date", "ticker", "close", "eps_estimate", "eps_actual"],
    ),
    (
        "stock_betas",
        "stock_betas.csv",
        ["ticker", "beta"],
    ),
    (
        "earnings_calendar",
        "earnings_calendar.csv",
        ["ticker", "report_date", "time", "fiscal_quarter_ending"],
    ),
    (
        "sec_filings",
        "sec_filings.csv",
        ["symbol", "cik", "accession_number", "company_name", "form_type",
         "form_type_description", "filing_date", "report_date",
         "acceptance_date_time", "filing_url", "primary_document"],
    ),
    (
        "transcripts_list",
        "transcripts_list.csv",
        ["symbol", "fiscal_year", "fiscal_quarter", "report_date",
         "transcripts", "transcripts_id"],
    ),
]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _bulk_insert(cur, table: str, columns: list[str], rows: list[dict[str, str]]) -> int:
    """Bulk-insert rows using execute_values with ON CONFLICT DO NOTHING."""
    if not rows:
        return 0

    col_names = ", ".join(f'"{c}"' for c in columns)
    placeholders = "(" + ", ".join(["%s"] * len(columns)) + ")"
    sql = f'INSERT INTO {table} ({col_names}) VALUES %s ON CONFLICT DO NOTHING'

    tuples = [tuple(row.get(c, "") for c in columns) for row in rows]

    # Insert in batches of 5000 for large tables
    batch_size = 5000
    total_inserted = 0
    for i in range(0, len(tuples), batch_size):
        batch = tuples[i : i + batch_size]
        execute_values(cur, sql, batch, template=placeholders, page_size=batch_size)
        total_inserted += len(batch)
        if len(tuples) > batch_size:
            print(f"  ... {table}: inserted {total_inserted}/{len(tuples)} rows")

    return total_inserted


def main():
    print("Connecting to Supabase...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    print("Creating tables...")
    cur.execute(CREATE_TABLES_SQL)
    print("Tables created.\n")

    for table, csv_file, columns in TABLES:
        csv_path = DATA_DIR / csv_file
        if not csv_path.exists():
            print(f"SKIP {table}: {csv_file} not found")
            continue

        print(f"Loading {csv_file} -> {table}...")
        rows = _read_csv(csv_path)
        count = _bulk_insert(cur, table, columns, rows)
        print(f"  {table}: {count} rows inserted from {len(rows)} CSV rows")

        # Verify row count
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        db_count = cur.fetchone()[0]
        print(f"  {table}: {db_count} total rows in DB\n")

    # Drop old tickers table
    print("Dropping old tickers table...")
    cur.execute("DROP TABLE IF EXISTS tickers CASCADE")
    print("Old tickers table dropped.\n")

    # Verify all new tables
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' ORDER BY table_name
    """)
    tables_in_db = [row[0] for row in cur.fetchall()]
    expected_new = [
        "stocks", "people", "portfolios", "portfolio_trades",
        "stock_history", "stock_betas", "earnings_calendar",
        "sec_filings", "transcripts_list",
    ]
    print("Verification:")
    for t in expected_new:
        status = "OK" if t in tables_in_db else "MISSING"
        print(f"  {t}: {status}")

    cur.close()
    conn.close()
    print("\nMigration complete.")


if __name__ == "__main__":
    main()
