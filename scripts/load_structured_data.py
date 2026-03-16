"""
Step 2: Load structured financial data from CSVs into Supabase.

Reads the long-format CSVs (ticker, metric, date, value), pivots to wide format
matching the Supabase table schemas, computes fiscal periods, and upserts.

Usage:
    python scripts/load_structured_data.py             # full load
    python scripts/load_structured_data.py --test      # test with 3 tickers
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

DATABASE_URL = "postgresql://postgres:sC.g6Wf#9h.Bf_f@db.ybjvfeevaxujenwvoewg.supabase.co:5432/postgres"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "structured"
FIN_DIR = DATA_DIR / "financials"

# ---------------------------------------------------------------------------
# Metric → Supabase column mappings
# ---------------------------------------------------------------------------
INCOME_METRICS = {
    "total_revenue": "revenue",
    "gross_profit": "gross_profit",
    "operating_income": "operating_income",
    "net_income": "net_income",
    "diluted_eps": "eps_diluted",
}

BALANCE_METRICS = {
    "total_assets": "total_assets",
    "total_liabilities_net_minority_interest": "total_liabilities",
    "stockholders_equity": "total_equity",
    "total_debt": "total_debt",
    "cash_and_cash_equivalents": "cash_and_equivalents",
}

CASHFLOW_METRICS = {
    "operating_cash_flow": "operating_cash_flow",
    "investing_cash_flow": "investing_cash_flow",
    "financing_cash_flow": "financing_cash_flow",
    "capital_expenditure": "capital_expenditures",
    "free_cash_flow": "free_cash_flow",
}


def safe_val(v):
    """Convert pandas value to Python-safe value for SQL."""
    if pd.isna(v) or v is None:
        return None
    if isinstance(v, float) and (math.isinf(v) or math.isnan(v)):
        return None
    return float(v)


# ---------------------------------------------------------------------------
# Fiscal period derivation
# ---------------------------------------------------------------------------
def get_fy_end_months(annual_df: pd.DataFrame) -> dict[str, int]:
    """Determine fiscal year end month per ticker from annual data."""
    fy_months: dict[str, int] = {}
    for ticker, grp in annual_df.groupby("ticker"):
        dates = pd.to_datetime(grp["date"], errors="coerce").dropna()
        if dates.empty:
            fy_months[ticker] = 12  # default calendar year
        else:
            # Most recent annual date determines FY end month
            fy_months[ticker] = dates.max().month
    return fy_months


def compute_fiscal_period_quarterly(date_str: str, fy_end_month: int) -> str | None:
    """Convert a quarterly period-end date to Q{N}_{YYYY} format."""
    try:
        dt = pd.Timestamp(date_str)
    except Exception:
        return None
    m = dt.month
    months_after = (m - fy_end_month - 1) % 12
    quarter_num = months_after // 3 + 1
    if m > fy_end_month:
        fiscal_year = dt.year + 1
    else:
        fiscal_year = dt.year
    return f"Q{quarter_num}_{fiscal_year}"


def compute_fiscal_period_annual(date_str: str) -> str | None:
    """Convert an annual period-end date to FY{YYYY} format."""
    try:
        dt = pd.Timestamp(date_str)
    except Exception:
        return None
    return f"FY{dt.year}"


# ---------------------------------------------------------------------------
# Pivot long-format CSV to wide rows
# ---------------------------------------------------------------------------
def pivot_financial_data(
    csv_path: Path,
    metric_map: dict[str, str],
    period_type: str,
    fy_end_months: dict[str, int],
    test_tickers: list[str] | None = None,
) -> list[dict]:
    """Read a long-format CSV and pivot to wide-format rows."""
    df = pd.read_csv(csv_path, dtype={"ticker": str, "metric": str, "value": str})

    # Filter to known metrics only
    df = df[df["metric"].isin(metric_map.keys())]

    # Filter out TTM rows
    df = df[df["date"] != "TTM"]

    if test_tickers:
        df = df[df["ticker"].isin(test_tickers)]

    if df.empty:
        return []

    # Pivot: each (ticker, date) becomes one row with metric columns
    pivoted = df.pivot_table(
        index=["ticker", "date"],
        columns="metric",
        values="value",
        aggfunc="first",
    ).reset_index()

    rows = []
    for _, row in pivoted.iterrows():
        ticker = row["ticker"]
        date_str = row["date"]
        fy_end = fy_end_months.get(ticker, 12)

        if period_type == "quarterly":
            fp = compute_fiscal_period_quarterly(date_str, fy_end)
        else:
            fp = compute_fiscal_period_annual(date_str)

        if fp is None:
            continue

        try:
            period_end = pd.Timestamp(date_str).date()
        except Exception:
            continue

        entry = {
            "ticker": ticker,
            "fiscal_period": fp,
            "fiscal_period_end": period_end,
            "period_type": period_type,
        }
        for src_metric, dest_col in metric_map.items():
            val = row.get(src_metric)
            entry[dest_col] = safe_val(pd.to_numeric(val, errors="coerce")) if val is not None else None

        rows.append(entry)

    return rows


# ---------------------------------------------------------------------------
# Compute margins for income statement rows
# ---------------------------------------------------------------------------
def add_margins(rows: list[dict]) -> list[dict]:
    """Compute margin percentages from absolute values."""
    for r in rows:
        rev = r.get("revenue")
        if rev and rev != 0:
            gp = r.get("gross_profit")
            oi = r.get("operating_income")
            ni = r.get("net_income")
            r["gross_margin"] = round(gp / rev * 100, 4) if gp is not None else None
            r["operating_margin"] = round(oi / rev * 100, 4) if oi is not None else None
            r["net_margin"] = round(ni / rev * 100, 4) if ni is not None else None
        else:
            r["gross_margin"] = None
            r["operating_margin"] = None
            r["net_margin"] = None
    return rows


# ---------------------------------------------------------------------------
# Upsert into Supabase
# ---------------------------------------------------------------------------
def upsert_rows(cur, table: str, columns: list[str], pk_columns: list[str], rows: list[dict]):
    """Bulk upsert rows using ON CONFLICT."""
    if not rows:
        return 0

    col_str = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    update_cols = [c for c in columns if c not in pk_columns and c != "created_at"]
    update_str = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)

    pk_str = ", ".join(pk_columns)

    sql = f"""
        INSERT INTO {table} ({col_str})
        VALUES ({placeholders})
        ON CONFLICT ({pk_str}) DO UPDATE SET {update_str}
    """

    data = []
    for r in rows:
        data.append(tuple(r.get(c) for c in columns))

    # Batch in chunks of 500
    batch_size = 500
    total = 0
    for i in range(0, len(data), batch_size):
        batch = data[i : i + batch_size]
        cur.executemany(sql, batch)
        total += len(batch)

    return total


# ---------------------------------------------------------------------------
# Load tickers from stocks.csv
# ---------------------------------------------------------------------------
def load_tickers(cur, test_tickers: list[str] | None = None):
    """Load tickers master table from stocks.csv."""
    stocks = pd.read_csv(DATA_DIR / "stocks.csv", dtype=str)
    if test_tickers:
        stocks = stocks[stocks["ticker"].isin(test_tickers)]

    rows = []
    for _, row in stocks.iterrows():
        mcap = pd.to_numeric(row.get("market_cap_b"), errors="coerce")
        if pd.notna(mcap):
            if mcap >= 10:
                tier = "large_cap"
            elif mcap >= 2:
                tier = "mid_cap"
            else:
                tier = "small_cap"
        else:
            tier = None

        rows.append({
            "ticker": row["ticker"],
            "company_name": row.get("company_name") if pd.notna(row.get("company_name")) else None,
            "sector": row.get("sector") if pd.notna(row.get("sector")) else None,
            "industry": row.get("industry") if pd.notna(row.get("industry")) else None,
            "market_cap_tier": tier,
            "country": row.get("country") if pd.notna(row.get("country")) else None,
            "currency": "USD",
        })

    columns = ["ticker", "company_name", "sector", "industry", "market_cap_tier", "country", "currency"]
    count = upsert_rows(cur, "tickers", columns, ["ticker"], rows)
    return count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Test with 3 tickers only")
    args = parser.parse_args()

    test_tickers = ["AAPL", "MSFT", "NVDA"] if args.test else None

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    # --- Phase 1: Load tickers ---
    print("=" * 60)
    print("Phase 1: Loading tickers")
    print("=" * 60)
    count = load_tickers(cur, test_tickers)
    print(f"  Upserted {count} tickers")

    # --- Phase 2: Determine FY end months from annual data ---
    print("\n" + "=" * 60)
    print("Phase 2: Determining fiscal year end months")
    print("=" * 60)
    annual_income = pd.read_csv(FIN_DIR / "annual_income_statements.csv", dtype={"ticker": str, "metric": str})
    annual_income = annual_income[annual_income["date"] != "TTM"]
    if test_tickers:
        annual_income = annual_income[annual_income["ticker"].isin(test_tickers)]
    fy_end_months = get_fy_end_months(annual_income)
    print(f"  Determined FY end month for {len(fy_end_months)} tickers")
    if test_tickers:
        for t in test_tickers:
            print(f"    {t}: FY ends month {fy_end_months.get(t, '?')}")

    # --- Phase 3: Load income statements ---
    print("\n" + "=" * 60)
    print("Phase 3: Loading income statements")
    print("=" * 60)
    income_cols = ["ticker", "fiscal_period", "fiscal_period_end", "period_type",
                   "revenue", "gross_profit", "operating_income", "net_income",
                   "eps_diluted", "gross_margin", "operating_margin", "net_margin"]
    income_pk = ["ticker", "fiscal_period", "period_type"]

    for period_type, csv_name in [
        ("quarterly", "quarterly_income_statements.csv"),
        ("annual", "annual_income_statements.csv"),
    ]:
        rows = pivot_financial_data(FIN_DIR / csv_name, INCOME_METRICS, period_type, fy_end_months, test_tickers)
        rows = add_margins(rows)
        count = upsert_rows(cur, "income_statement", income_cols, income_pk, rows)
        print(f"  {period_type}: {count} rows upserted")

    # --- Phase 4: Load balance sheets ---
    print("\n" + "=" * 60)
    print("Phase 4: Loading balance sheets")
    print("=" * 60)
    balance_cols = ["ticker", "fiscal_period", "fiscal_period_end", "period_type",
                    "total_assets", "total_liabilities", "total_equity",
                    "total_debt", "cash_and_equivalents"]
    balance_pk = ["ticker", "fiscal_period", "period_type"]

    for period_type, csv_name in [
        ("quarterly", "quarterly_balance_sheets.csv"),
        ("annual", "annual_balance_sheets.csv"),
    ]:
        rows = pivot_financial_data(FIN_DIR / csv_name, BALANCE_METRICS, period_type, fy_end_months, test_tickers)
        count = upsert_rows(cur, "balance_sheet", balance_cols, balance_pk, rows)
        print(f"  {period_type}: {count} rows upserted")

    # --- Phase 5: Load cash flows ---
    print("\n" + "=" * 60)
    print("Phase 5: Loading cash flows")
    print("=" * 60)
    cashflow_cols = ["ticker", "fiscal_period", "fiscal_period_end", "period_type",
                     "operating_cash_flow", "investing_cash_flow", "financing_cash_flow",
                     "capital_expenditures", "free_cash_flow"]
    cashflow_pk = ["ticker", "fiscal_period", "period_type"]

    for period_type, csv_name in [
        ("quarterly", "quarterly_cash_flows.csv"),
        ("annual", "annual_cash_flows.csv"),
    ]:
        rows = pivot_financial_data(FIN_DIR / csv_name, CASHFLOW_METRICS, period_type, fy_end_months, test_tickers)
        count = upsert_rows(cur, "cash_flows", cashflow_cols, cashflow_pk, rows)
        print(f"  {period_type}: {count} rows upserted")

    # --- Verification ---
    print("\n" + "=" * 60)
    print("Verification")
    print("=" * 60)

    for table in ["tickers", "income_statement", "balance_sheet", "cash_flows"]:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        total = cur.fetchone()[0]
        cur.execute(f"SELECT COUNT(DISTINCT ticker) FROM {table}")
        tickers = cur.fetchone()[0]
        print(f"  {table}: {total} rows, {tickers} tickers")

    # Sample data check
    print("\n  Sample: AAPL quarterly income (most recent 4)")
    cur.execute("""
        SELECT fiscal_period, fiscal_period_end, revenue, gross_margin, eps_diluted
        FROM income_statement
        WHERE ticker = 'AAPL' AND period_type = 'quarterly'
        ORDER BY fiscal_period_end DESC
        LIMIT 4
    """)
    for row in cur.fetchall():
        rev_b = f"${float(row[2]) / 1e9:.1f}B" if row[2] else "N/A"
        gm = f"{float(row[3]):.1f}%" if row[3] else "N/A"
        eps = f"${float(row[4]):.2f}" if row[4] else "N/A"
        print(f"    {row[0]} ({row[1]}): Rev {rev_b}, GM {gm}, EPS {eps}")

    cur.close()
    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
