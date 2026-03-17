#!/usr/bin/env python3
"""One-time migration: create financial_metrics table, migrate data from old
wide tables (income_statement, balance_sheet, cash_flows), then drop them.

Usage:
    python scripts/migrate_financial_tables.py
    python scripts/migrate_financial_tables.py --dry-run   # preview without changes
"""
from __future__ import annotations

import argparse
import sys

import psycopg2

DATABASE_URL = "postgresql://postgres:sC.g6Wf#9h.Bf_f@db.ybjvfeevaxujenwvoewg.supabase.co:5432/postgres"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS financial_metrics (
    ticker       VARCHAR(20) NOT NULL,
    metric_name  VARCHAR(100) NOT NULL,
    period_end   DATE NOT NULL,
    period_type  VARCHAR(10) CHECK (period_type IN ('quarterly', 'annual')),
    value        NUMERIC,
    created_at   TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (ticker, metric_name, period_end, period_type)
);

CREATE INDEX IF NOT EXISTS idx_fm_ticker ON financial_metrics (ticker);
CREATE INDEX IF NOT EXISTS idx_fm_ticker_period ON financial_metrics (ticker, period_type);
CREATE INDEX IF NOT EXISTS idx_fm_ticker_metric ON financial_metrics (ticker, metric_name);
"""

# Each entry: (old_table, column_name, metric_name_in_new_table)
INCOME_MAPPINGS = [
    ("income_statement", "revenue", "total_revenue"),
    ("income_statement", "gross_profit", "gross_profit"),
    ("income_statement", "operating_income", "operating_income"),
    ("income_statement", "net_income", "net_income"),
    ("income_statement", "eps_diluted", "diluted_eps"),
]

BALANCE_MAPPINGS = [
    ("balance_sheet", "total_assets", "total_assets"),
    ("balance_sheet", "total_liabilities", "total_liabilities_net_minority_interest"),
    ("balance_sheet", "total_equity", "stockholders_equity"),
    ("balance_sheet", "total_debt", "total_debt"),
    ("balance_sheet", "cash_and_equivalents", "cash_and_cash_equivalents"),
]

CASHFLOW_MAPPINGS = [
    ("cash_flows", "operating_cash_flow", "operating_cash_flow"),
    ("cash_flows", "investing_cash_flow", "investing_cash_flow"),
    ("cash_flows", "financing_cash_flow", "financing_cash_flow"),
    ("cash_flows", "capital_expenditures", "capital_expenditure"),
    ("cash_flows", "free_cash_flow", "free_cash_flow"),
]

ALL_MAPPINGS = INCOME_MAPPINGS + BALANCE_MAPPINGS + CASHFLOW_MAPPINGS


def migrate(dry_run: bool = False) -> None:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    # Step 1: Create financial_metrics table
    print("Creating financial_metrics table...")
    if not dry_run:
        cur.execute(CREATE_TABLE_SQL)
    print("  Done.")

    # Step 2: Migrate data from old wide tables
    total_migrated = 0
    for old_table, old_col, new_metric in ALL_MAPPINGS:
        # Check if old table exists
        cur.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = %s",
            (old_table,),
        )
        if not cur.fetchone():
            print(f"  Skipping {old_table}.{old_col} — table does not exist")
            continue

        # Check if column exists
        cur.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s AND column_name = %s",
            (old_table, old_col),
        )
        if not cur.fetchone():
            print(f"  Skipping {old_table}.{old_col} — column does not exist")
            continue

        migrate_sql = f"""
            INSERT INTO financial_metrics (ticker, metric_name, period_end, period_type, value)
            SELECT ticker, '{new_metric}', fiscal_period_end, period_type, {old_col}
            FROM {old_table}
            WHERE fiscal_period_end IS NOT NULL AND {old_col} IS NOT NULL
            ON CONFLICT (ticker, metric_name, period_end, period_type)
            DO UPDATE SET value = EXCLUDED.value
        """

        if dry_run:
            cur.execute(
                f"SELECT COUNT(*) FROM {old_table} "
                f"WHERE fiscal_period_end IS NOT NULL AND {old_col} IS NOT NULL"
            )
            count = cur.fetchone()[0]
            print(f"  [DRY RUN] {old_table}.{old_col} → {new_metric}: {count} rows")
        else:
            cur.execute(migrate_sql)
            count = cur.rowcount
            print(f"  {old_table}.{old_col} → {new_metric}: {count} rows migrated")

        total_migrated += count

    print(f"\nTotal rows migrated: {total_migrated}")

    # Step 3: Verify
    if not dry_run:
        cur.execute("SELECT COUNT(*) FROM financial_metrics")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(DISTINCT ticker) FROM financial_metrics")
        tickers = cur.fetchone()[0]
        cur.execute("SELECT COUNT(DISTINCT metric_name) FROM financial_metrics")
        metrics = cur.fetchone()[0]
        print(f"\nfinancial_metrics: {total} rows, {tickers} tickers, {metrics} metrics")

        # Sample check
        cur.execute("""
            SELECT metric_name, period_end, period_type, value
            FROM financial_metrics
            WHERE ticker = 'AAPL'
            ORDER BY period_end DESC
            LIMIT 5
        """)
        print("\nSample: AAPL (most recent 5 rows)")
        for row in cur.fetchall():
            print(f"  {row[0]:30s} {row[1]} {row[2]:10s} {row[3]}")

    # Step 4: Drop old tables
    old_tables = ["income_statement", "balance_sheet", "cash_flows"]
    for table in old_tables:
        cur.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = %s",
            (table,),
        )
        if not cur.fetchone():
            print(f"\n  {table} — already gone")
            continue
        if dry_run:
            print(f"\n  [DRY RUN] Would drop table: {table}")
        else:
            cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
            print(f"\n  Dropped table: {table}")

    cur.close()
    conn.close()
    print("\nMigration complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate financial tables to long-format")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making changes")
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
