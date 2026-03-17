#!/usr/bin/env python3
"""Download stock prices, EPS, earnings calendar, financial statements, and beta.

Runs eight phases sequentially:
  Phase 0 — Tickers:    Upsert stocks.csv tickers into Supabase tickers table
  Phase 1 — Prices:     Per-ticker defeatbeta-api price() calls
  Phase 2 — EPS:        Per-ticker defeatbeta-api ttm_eps() calls with
                         checkpoint/resume + synthetic fallback
  Phase 3 — Write:      Writes data/structured/stock_history.csv
  Phase 4 — Stocks:     Updates stocks.csv with computed financials
  Phase 5 — Calendar:   Bulk DuckDB query → data/structured/earnings_calendar.csv
  Phase 6 — Statements: Bulk DuckDB queries → Supabase financial_metrics table
  Phase 7 — Beta:       Bulk DuckDB query + local computation →
                         data/structured/stock_betas.csv

Phases 5-7 use bulk SQL queries against the HuggingFace parquet files via DuckDB,
fetching all tickers in a single query per data type instead of per-ticker calls.
Phases 1-2 remain per-ticker because they have checkpoint/resume logic.

CLI flags:
  --fresh              Re-fetch all EPS (ignore checkpoint)
  --synthetic-only     Skip real EPS fetches, use synthetic EPS only
  --prices-only        Skip EPS entirely (empty EPS columns)
  --skip-calendar      Skip earnings calendar phase
  --skip-statements    Skip financial statements phase
  --skip-beta          Skip stock beta phase
  --skip-tickers       Skip tickers upsert phase
  --start-date DATE    Price history start date (default: 2015-01-01)
"""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import logging
import math
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

import finnhub
import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from defeatbeta_api.client.duckdb_client import get_duckdb_client
from defeatbeta_api.client.hugging_face_client import HuggingFaceClient
from defeatbeta_api.data.ticker import Ticker
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")

STOCKS_CSV = ROOT / "data" / "structured" / "stocks.csv"
OUTPUT_CSV = ROOT / "data" / "structured" / "stock_history.csv"
CHECKPOINT = ROOT / "scripts" / ".eps_checkpoint.json"

CALENDAR_CSV = ROOT / "data" / "structured" / "earnings_calendar.csv"
BETA_CSV = ROOT / "data" / "structured" / "stock_betas.csv"

FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
FINNHUB_LOOKAHEAD_DAYS = 90  # ~3 months of future earnings
FINNHUB_CHUNK_DAYS = 7       # query in weekly chunks to avoid 1500-row API cap

DATABASE_URL = os.environ.get(
    "SUPABASE_DATABASE_URL",
    "postgresql://postgres:sC.g6Wf#9h.Bf_f@db.ybjvfeevaxujenwvoewg.supabase.co:5432/postgres",
)

PRICE_WORKERS = 10
EPS_WORKERS = 10

CALENDAR_COLUMNS = ["ticker", "report_date", "time", "fiscal_quarter_ending"]
STATEMENT_COLUMNS = ["ticker", "metric", "date", "value"]
BETA_COLUMNS = ["ticker", "beta"]

# (finance_type, period_type, output csv filename)
STATEMENT_TYPES = [
    ("income_statement", "quarterly", "quarterly_income_statements.csv"),
    ("income_statement", "annual", "annual_income_statements.csv"),
    ("balance_sheet", "quarterly", "quarterly_balance_sheets.csv"),
    ("balance_sheet", "annual", "annual_balance_sheets.csv"),
    ("cash_flow", "quarterly", "quarterly_cash_flows.csv"),
    ("cash_flow", "annual", "annual_cash_flows.csv"),
]

# Approximate sector P/E ratios for synthetic EPS derivation
SECTOR_PE = {
    "Technology": 25,
    "Healthcare": 22,
    "Financials": 14,
    "Consumer Discretionary": 20,
    "Communication Services": 18,
    "Industrials": 18,
    "Consumer Staples": 22,
    "Energy": 12,
    "Utilities": 16,
    "Materials": 15,
    "Real Estate": 35,
}
DEFAULT_PE = 20

random.seed(42)

# Thread-safe checkpoint access
_checkpoint_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Ticker helpers
# ---------------------------------------------------------------------------

def load_tickers() -> list[str]:
    """Read tickers from the stocks Supabase table."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT ticker FROM stocks ORDER BY ticker")
    tickers = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return tickers


def load_sectors() -> dict[str, str]:
    """Load ticker -> sector mapping from the stocks Supabase table."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT ticker, sector FROM stocks")
    sectors = {row[0]: row[1] or "" for row in cur.fetchall()}
    cur.close()
    conn.close()
    return sectors


def to_api_ticker(ticker: str) -> str:
    """defeatbeta-api data uses Yahoo Finance format (dashes instead of dots)."""
    return ticker.replace(".", "-")


def from_api_ticker(symbol: str) -> str:
    """Convert API symbol (BRK-B) back to our ticker format (BRK.B)."""
    return symbol.replace("-", ".")


def _build_symbol_in_clause(tickers: list[str]) -> str:
    """Build a SQL IN clause with API-format ticker symbols."""
    api_tickers = [to_api_ticker(t) for t in tickers]
    return ", ".join(f"'{s}'" for s in api_tickers)


def _get_parquet_url(table_name: str) -> str:
    """Get the HuggingFace parquet URL for a given table."""
    return HuggingFaceClient().get_url_path(table_name)


def _bulk_query(sql: str) -> pd.DataFrame:
    """Execute a SQL query against the DuckDB singleton."""
    db = get_duckdb_client(log_level=logging.WARNING)
    return db.query(sql)


# ---------------------------------------------------------------------------
# Phase 1 — Prices
# ---------------------------------------------------------------------------

def fetch_price_for_ticker(
    ticker: str, start_date: str,
) -> list[tuple[str, str, float]]:
    """Fetch daily closing prices for one ticker from defeatbeta-api."""
    api_ticker = to_api_ticker(ticker)
    t = Ticker(api_ticker, log_level=logging.WARNING)
    df = t.price()
    if df is None or df.empty:
        return []

    rows: list[tuple[str, str, float]] = []
    for _, row in df.iterrows():
        date_str = str(row["report_date"])[:10]
        if date_str < start_date:
            continue
        close = round(float(row["close"]), 2)
        rows.append((date_str, ticker, close))

    return rows


def fetch_prices(
    tickers: list[str], start_date: str,
) -> list[tuple[str, str, float]]:
    """Download daily closing prices for all tickers using ThreadPoolExecutor."""
    print(f"Downloading price history for {len(tickers)} tickers "
          f"({PRICE_WORKERS} threads)...")

    all_rows: list[tuple[str, str, float]] = []
    completed = 0
    failed: list[str] = []

    with ThreadPoolExecutor(max_workers=PRICE_WORKERS) as pool:
        futures = {
            pool.submit(fetch_price_for_ticker, ticker, start_date): ticker
            for ticker in tickers
        }
        for future in as_completed(futures):
            ticker = futures[future]
            completed += 1
            try:
                rows = future.result()
                all_rows.extend(rows)
                if completed % 50 == 0 or completed == len(tickers):
                    print(f"  [{completed}/{len(tickers)}] prices fetched...",
                          flush=True)
            except Exception as e:
                failed.append(ticker)
                print(f"  [{completed}/{len(tickers)}] {ticker} -> "
                      f"PRICE ERROR: {e}", file=sys.stderr, flush=True)

    if not all_rows:
        print("ERROR: No price data returned", file=sys.stderr)
        sys.exit(1)

    if failed:
        print(f"WARNING: {len(failed)} tickers failed price fetch: "
              f"{', '.join(sorted(failed)[:20])}", file=sys.stderr)

    all_rows.sort(key=lambda r: (r[0], r[1]))
    print(f"Got {len(all_rows)} price rows for "
          f"{len(set(r[1] for r in all_rows))} tickers")
    return all_rows


# ---------------------------------------------------------------------------
# Phase 2a — Real EPS (defeatbeta-api per-ticker)
# ---------------------------------------------------------------------------

def fetch_eps_for_ticker(ticker: str) -> dict[str, float]:
    """Fetch quarterly EPS actuals for one ticker.

    Returns {date_str: eps_actual}.
    """
    api_ticker = to_api_ticker(ticker)
    result: dict[str, float] = {}
    t = Ticker(api_ticker, log_level=logging.WARNING)
    df = t.ttm_eps()
    if df is None or df.empty:
        return result

    for _, row in df.iterrows():
        date_str = str(row["report_date"])[:10]
        eps_val = row.get("eps")
        if eps_val is None or (isinstance(eps_val, float) and math.isnan(eps_val)):
            continue
        result[date_str] = round(float(eps_val), 2)
    return result


def load_checkpoint() -> dict[str, dict[str, float]]:
    if CHECKPOINT.exists():
        with open(CHECKPOINT) as f:
            data = json.load(f)
        # Handle old checkpoint format {ticker: {date: [est, actual]}}
        for ticker, dates in data.items():
            for d, v in dates.items():
                if isinstance(v, list):
                    data[ticker][d] = v[1] if len(v) > 1 else v[0]
        return data
    return {}


def save_checkpoint(data: dict[str, dict[str, float]]) -> None:
    with _checkpoint_lock:
        with open(CHECKPOINT, "w") as f:
            json.dump(data, f)


def process_ticker(
    ticker: str,
    checkpoint: dict[str, dict[str, float]],
) -> tuple[str, int]:
    """Fetch EPS for one ticker and update the checkpoint."""
    try:
        eps = fetch_eps_for_ticker(ticker)
        with _checkpoint_lock:
            checkpoint[ticker] = eps
        save_checkpoint(checkpoint)
        return ticker, len(eps)
    except Exception:
        return ticker, -1


def fetch_real_eps(
    tickers: list[str],
    fresh: bool,
) -> tuple[dict[str, dict[str, float]], list[str]]:
    """Fetch real EPS actuals for all tickers using thread pool + checkpoint.

    Returns (eps_actuals, failed_tickers).
    eps_actuals: {ticker: {date_str: eps_actual}}
    """
    checkpoint: dict[str, dict[str, float]] = {} if fresh else load_checkpoint()
    if checkpoint and not fresh:
        print(f"Resuming from checkpoint ({len(checkpoint)} tickers already fetched)")

    remaining = [t for t in tickers if t not in checkpoint]
    failed: list[str] = []

    if not remaining:
        print("All tickers already fetched (use --fresh to re-fetch)")
    else:
        print(f"\nFetching EPS data for {len(remaining)} tickers "
              f"({EPS_WORKERS} threads)...")

        completed = 0
        with ThreadPoolExecutor(max_workers=EPS_WORKERS) as pool:
            futures = {
                pool.submit(process_ticker, ticker, checkpoint): ticker
                for ticker in remaining
            }
            for future in as_completed(futures):
                ticker = futures[future]
                try:
                    _, count = future.result()
                    completed += 1
                    if count >= 0:
                        print(f"  [{completed}/{len(remaining)}] {ticker} -> "
                              f"{count} earnings dates", flush=True)
                    else:
                        failed.append(ticker)
                        print(f"  [{completed}/{len(remaining)}] {ticker} -> "
                              f"FAILED", flush=True)
                except Exception as e:
                    completed += 1
                    failed.append(ticker)
                    print(f"  [{completed}/{len(remaining)}] {ticker} -> "
                          f"ERROR: {e}", file=sys.stderr, flush=True)

    total = sum(len(v) for v in checkpoint.values())
    print(f"Real EPS: {total} data points across {len(checkpoint)} tickers")

    return dict(checkpoint), failed


# ---------------------------------------------------------------------------
# Phase 2b — Build EPS lookup (real actuals + synthetic estimates)
# ---------------------------------------------------------------------------

def build_eps_lookup(
    eps_actuals: dict[str, dict[str, float]],
    price_rows: list[tuple[str, str, float]],
    sectors: dict[str, str],
) -> dict[str, dict[str, tuple[float, float]]]:
    """Combine real EPS actuals with synthetic EPS estimates.

    For each ticker with real EPS data:
      - eps_actual comes from defeatbeta-api
      - eps_estimate is derived from close price / sector P/E / 4
      - Fiscal quarter-end dates are mapped to the nearest trading date

    Returns {ticker: {date_str: (eps_estimate, eps_actual)}}.
    """
    # Build sorted trading dates and price lookup per ticker
    ticker_dates: dict[str, list[str]] = {}
    ticker_prices: dict[str, dict[str, float]] = {}
    for date_str, ticker, close in price_rows:
        ticker_dates.setdefault(ticker, []).append(date_str)
        ticker_prices.setdefault(ticker, {})[date_str] = close

    for dates in ticker_dates.values():
        dates.sort()

    eps_lookup: dict[str, dict[str, tuple[float, float]]] = {}

    for ticker, eps_dates in eps_actuals.items():
        if ticker not in ticker_dates:
            continue

        sector = sectors.get(ticker, "")
        pe = SECTOR_PE.get(sector, DEFAULT_PE)
        trading_dates = ticker_dates[ticker]
        prices = ticker_prices[ticker]
        ticker_eps: dict[str, tuple[float, float]] = {}

        for eps_date, actual in eps_dates.items():
            # Map fiscal quarter-end date to nearest trading date on or after
            idx = bisect.bisect_left(trading_dates, eps_date)
            if idx >= len(trading_dates):
                mapped_date = trading_dates[-1]
            else:
                mapped_date = trading_dates[idx]

            close = prices.get(mapped_date, 0)
            if close > 0:
                eps_estimate = round(close / pe / 4, 2)
            else:
                eps_estimate = round(actual * 0.95, 2)

            ticker_eps[mapped_date] = (eps_estimate, actual)

        if ticker_eps:
            eps_lookup[ticker] = ticker_eps

    total = sum(len(v) for v in eps_lookup.values())
    print(f"EPS lookup (real actuals + synthetic estimates): "
          f"{total} data points across {len(eps_lookup)} tickers")
    return eps_lookup


# ---------------------------------------------------------------------------
# Phase 2c — Synthetic EPS (fallback from prices + sector P/E)
# ---------------------------------------------------------------------------

def get_quarterly_dates(dates: list[str]) -> set[str]:
    """Pick one date per quarter (closest to earnings report months)."""
    quarters: dict[str, list[str]] = {}
    for d in dates:
        year, month = d[:4], int(d[5:7])
        if month in (1, 2):
            qkey = f"{year}-Q4"
        elif month in (4, 5):
            qkey = f"{year}-Q1"
        elif month in (7, 8):
            qkey = f"{year}-Q2"
        elif month in (10, 11):
            qkey = f"{year}-Q3"
        else:
            continue
        quarters.setdefault(qkey, []).append(d)

    selected: set[str] = set()
    for dates_in_q in quarters.values():
        dates_in_q.sort()
        selected.add(dates_in_q[-1])
    return selected


def generate_synthetic_eps(
    price_rows: list[tuple[str, str, float]],
    sectors: dict[str, str],
    tickers_to_fill: set[str] | None = None,
) -> dict[str, dict[str, tuple[float, float]]]:
    """Derive EPS from prices and sector P/E ratios.

    If tickers_to_fill is None, generates for all tickers.
    Otherwise, only generates for the specified tickers.
    """
    # Group rows by ticker
    ticker_entries: dict[str, list[tuple[str, float]]] = {}
    for date_str, ticker, close in price_rows:
        if tickers_to_fill is not None and ticker not in tickers_to_fill:
            continue
        ticker_entries.setdefault(ticker, []).append((date_str, close))

    eps_lookup: dict[str, dict[str, tuple[float, float]]] = {}
    for ticker, entries in ticker_entries.items():
        sector = sectors.get(ticker, "")
        pe = SECTOR_PE.get(sector, DEFAULT_PE)

        dates = [d for d, _ in entries]
        quarterly_dates = get_quarterly_dates(dates)

        date_to_close = {d: c for d, c in entries}
        ticker_eps: dict[str, tuple[float, float]] = {}

        for date in quarterly_dates:
            if date not in date_to_close:
                continue
            close = date_to_close[date]
            annual_eps = close / pe
            quarterly_eps = annual_eps / 4
            surprise = random.uniform(-0.05, 0.10)
            eps_estimate = round(quarterly_eps, 2)
            eps_actual = round(quarterly_eps * (1 + surprise), 2)
            ticker_eps[date] = (eps_estimate, eps_actual)

        if ticker_eps:
            eps_lookup[ticker] = ticker_eps

    total = sum(len(v) for v in eps_lookup.values())
    print(f"Synthetic EPS: {total} data points across {len(eps_lookup)} tickers")
    return eps_lookup


# ---------------------------------------------------------------------------
# Phase 5 — Earnings Calendar (DefeatBeta historical + Finnhub future)
# ---------------------------------------------------------------------------

def _fetch_historical_calendar(tickers: list[str]) -> list[dict[str, str]]:
    """Bulk-fetch historical earnings calendar from DefeatBeta."""
    print("  Fetching historical calendar from DefeatBeta (bulk query)...")
    symbols_clause = _build_symbol_in_clause(tickers)
    url = _get_parquet_url("stock_earning_calendar")
    sql = (
        f"SELECT symbol, report_date, time, fiscal_quarter_ending "
        f"FROM '{url}' "
        f"WHERE symbol IN ({symbols_clause}) "
        f"ORDER BY symbol, report_date"
    )
    df = _bulk_query(sql)
    if df is None or df.empty:
        print("  WARNING: No historical calendar data returned", file=sys.stderr)
        return []

    rows: list[dict[str, str]] = []
    for _, row in df.iterrows():
        rows.append({
            "ticker": from_api_ticker(str(row["symbol"])),
            "report_date": str(row["report_date"])[:10],
            "time": str(row.get("time", "time-not-supplied")),
            "fiscal_quarter_ending": str(row["fiscal_quarter_ending"])[:10],
        })
    print(f"  Historical: {len(rows)} rows ({df['symbol'].nunique()} tickers)")
    return rows


def _fetch_finnhub_calendar(tickers: list[str]) -> list[dict[str, str]]:
    """Fetch upcoming earnings dates from Finnhub in weekly chunks.

    Queries the full market calendar and filters to our ticker universe.
    Uses weekly chunks because the API caps responses at 1500 rows.
    """
    if not FINNHUB_API_KEY:
        print("  WARNING: FINNHUB_API_KEY not set, skipping future dates",
              file=sys.stderr)
        return []

    api_tickers = {to_api_ticker(t): t for t in tickers}
    client = finnhub.Client(api_key=FINNHUB_API_KEY)

    today = datetime.now()
    end = today + timedelta(days=FINNHUB_LOOKAHEAD_DAYS)

    print(f"  Fetching future calendar from Finnhub "
          f"({today.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')})...")

    all_rows: list[dict[str, str]] = []
    chunk_start = today

    while chunk_start < end:
        chunk_end = min(chunk_start + timedelta(days=FINNHUB_CHUNK_DAYS), end)
        start_str = chunk_start.strftime("%Y-%m-%d")
        end_str = chunk_end.strftime("%Y-%m-%d")

        try:
            result = client.earnings_calendar(
                _from=start_str, to=end_str, symbol="", international=False,
            )
            entries = result.get("earningsCalendar", [])

            if len(entries) >= 1500:
                print(f"  WARNING: {start_str} to {end_str} hit 1500-row cap, "
                      f"some entries may be missing", file=sys.stderr)

            for e in entries:
                sym = e.get("symbol", "")
                if sym not in api_tickers:
                    continue
                # Map Finnhub hour codes to readable time
                hour = e.get("hour", "")
                if hour == "bmo":
                    time_str = "before-market-open"
                elif hour == "amc":
                    time_str = "after-market-close"
                else:
                    time_str = "time-not-supplied"

                # Finnhub doesn't provide fiscal_quarter_ending directly;
                # approximate from quarter + year
                quarter = e.get("quarter")
                year = e.get("year")
                if quarter and year:
                    # Standard quarter-end months: Q1=Mar, Q2=Jun, Q3=Sep, Q4=Dec
                    q_month = {1: 3, 2: 6, 3: 9, 4: 12}.get(quarter, 12)
                    # Last day of quarter-end month
                    if q_month == 12:
                        fqe = f"{year}-12-31"
                    else:
                        next_month_start = datetime(year, q_month + 1, 1)
                        fqe = (next_month_start - timedelta(days=1)).strftime("%Y-%m-%d")
                else:
                    fqe = ""

                all_rows.append({
                    "ticker": api_tickers[sym],
                    "report_date": e.get("date", ""),
                    "time": time_str,
                    "fiscal_quarter_ending": fqe,
                })
        except Exception as exc:
            print(f"  WARNING: Finnhub query {start_str}–{end_str} failed: {exc}",
                  file=sys.stderr)

        chunk_start = chunk_end
        time.sleep(1)  # respect rate limits

    unique = len({r["ticker"] for r in all_rows})
    print(f"  Finnhub future: {len(all_rows)} rows ({unique} tickers)")
    return all_rows


def fetch_earnings_calendars(tickers: list[str]) -> None:
    """Merge DefeatBeta historical + Finnhub future earnings calendars."""
    print(f"Building earnings calendar for {len(tickers)} tickers...")

    historical = _fetch_historical_calendar(tickers)
    future = _fetch_finnhub_calendar(tickers)

    # Merge and deduplicate by (ticker, report_date)
    seen: set[tuple[str, str]] = set()
    merged: list[dict[str, str]] = []
    # Historical rows first (they have accurate fiscal_quarter_ending)
    for row in historical:
        key = (row["ticker"], row["report_date"])
        if key not in seen:
            seen.add(key)
            merged.append(row)
    # Then future rows (only add if not already present from historical)
    for row in future:
        key = (row["ticker"], row["report_date"])
        if key not in seen:
            seen.add(key)
            merged.append(row)

    merged.sort(key=lambda r: (r["ticker"], r["report_date"]))

    # Upsert into Supabase
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    db_rows = [
        (r["ticker"], r["report_date"], r.get("time", ""), r.get("fiscal_quarter_ending", ""))
        for r in merged
    ]
    batch_size = 2000
    for i in range(0, len(db_rows), batch_size):
        batch = db_rows[i : i + batch_size]
        execute_values(cur,
            """INSERT INTO earnings_calendar (ticker, report_date, time, fiscal_quarter_ending)
               VALUES %s
               ON CONFLICT (ticker, report_date) DO UPDATE SET
                   time = EXCLUDED.time,
                   fiscal_quarter_ending = EXCLUDED.fiscal_quarter_ending""",
            batch, page_size=batch_size,
        )

    cur.close()
    conn.close()

    unique_tickers = len({r["ticker"] for r in merged})
    hist_count = len(historical)
    future_only = len(merged) - hist_count
    print(f"Upserted {len(merged)} rows into earnings_calendar table "
          f"({unique_tickers} tickers, {hist_count} historical + "
          f"{future_only} new from Finnhub)")


# ---------------------------------------------------------------------------
# Phase 6 — Financial Statements (bulk query)
# ---------------------------------------------------------------------------

def fetch_financial_statements(tickers: list[str]) -> None:
    """Bulk-fetch all financial statements and upsert into Supabase.

    Queries the raw stock_statement parquet directly (6 queries total: one per
    finance_type + period_type combination) and upserts rows into the
    financial_metrics table.
    """
    print(f"Downloading financial statements for {len(tickers)} tickers "
          f"(6 bulk queries → Supabase)...")

    symbols_clause = _build_symbol_in_clause(tickers)
    url = _get_parquet_url("stock_statement")
    total_rows = 0

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    for finance_type, period_type, csv_name in STATEMENT_TYPES:
        sql = (
            f"SELECT symbol, item_name, report_date, item_value "
            f"FROM '{url}' "
            f"WHERE symbol IN ({symbols_clause}) "
            f"  AND finance_type = '{finance_type}' "
            f"  AND period_type = '{period_type}' "
            f"ORDER BY symbol, report_date, item_name"
        )
        df = _bulk_query(sql)

        rows = []
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                val = row["item_value"]
                if pd.isna(val):
                    continue
                date_str = str(row["report_date"])[:10]
                if date_str == "TTM":
                    continue
                rows.append((
                    from_api_ticker(str(row["symbol"])),
                    str(row["item_name"]),
                    date_str,
                    period_type,
                    float(val),
                ))

        if rows:
            execute_values(cur,
                """INSERT INTO financial_metrics (ticker, metric_name, period_end, period_type, value)
                   VALUES %s
                   ON CONFLICT (ticker, metric_name, period_end, period_type)
                   DO UPDATE SET value = EXCLUDED.value""",
                rows, page_size=1000,
            )

        unique = df["symbol"].nunique() if df is not None and not df.empty else 0
        label = f"{finance_type}/{period_type}"
        print(f"  {label}: {len(rows)} rows upserted ({unique} tickers)")
        total_rows += len(rows)

    cur.close()
    conn.close()
    print(f"Total financial statement rows upserted: {total_rows}")


# ---------------------------------------------------------------------------
# Phase 7 — Stock Beta (bulk query + local computation)
# ---------------------------------------------------------------------------

BETA_PERIOD_YEARS = 5
BETA_BENCHMARK = "SPY"


def _compute_beta(stock_prices: pd.DataFrame, bench_prices: pd.DataFrame) -> float | None:
    """Compute 5-year monthly beta from two DataFrames of (report_date, close).

    Uses monthly returns and cov/var, matching the Ticker.beta() algorithm.
    """
    if stock_prices.empty or bench_prices.empty:
        return None

    # Merge on date, resample to monthly
    merged = stock_prices.merge(bench_prices, on="report_date", suffixes=("_stock", "_bench"))
    if len(merged) < 2:
        return None

    merged["report_date"] = pd.to_datetime(merged["report_date"])
    merged = merged.set_index("report_date").sort_index()
    monthly = merged.resample("ME").last().dropna()
    if len(monthly) < 3:
        return None

    monthly["stock_return"] = monthly["close_stock"].pct_change()
    monthly["bench_return"] = monthly["close_bench"].pct_change()
    monthly = monthly.dropna()
    if len(monthly) < 2:
        return None

    cov = np.cov(monthly["stock_return"], monthly["bench_return"])[0, 1]
    var = np.var(monthly["bench_return"], ddof=1)
    if var == 0:
        return None
    return round(float(cov / var), 4)


def fetch_betas(tickers: list[str]) -> None:
    """Bulk-fetch prices for all tickers + benchmark, compute beta locally.

    One DuckDB query fetches 5 years of prices for all symbols at once,
    then beta is computed per-ticker in Python.
    """
    # Determine date range matching Ticker.beta("5y") logic
    end_date_str = HuggingFaceClient().get_data_update_time()
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
    start_date = end_date - timedelta(days=BETA_PERIOD_YEARS * 365)
    start_str = start_date.strftime("%Y-%m-%d")

    # Build symbol list including benchmark
    all_symbols = [to_api_ticker(t) for t in tickers] + [BETA_BENCHMARK]
    symbols_clause = ", ".join(f"'{s}'" for s in all_symbols)
    url = _get_parquet_url("stock_prices")

    print(f"Downloading prices for beta computation "
          f"({len(tickers)} tickers + {BETA_BENCHMARK}, single bulk query)...")

    sql = (
        f"SELECT symbol, report_date, close "
        f"FROM '{url}' "
        f"WHERE symbol IN ({symbols_clause}) "
        f"  AND report_date >= '{start_str}' "
        f"  AND report_date <= '{end_date_str}' "
        f"ORDER BY symbol, report_date"
    )
    df = _bulk_query(sql)

    if df is None or df.empty:
        print("WARNING: No price data returned for beta", file=sys.stderr)
        return

    # Extract benchmark prices
    bench_df = df[df["symbol"] == BETA_BENCHMARK][["report_date", "close"]].copy()

    # Compute beta per ticker
    print(f"Computing beta for {len(tickers)} tickers...")
    rows: list[dict[str, str]] = []
    failed: list[str] = []
    for ticker in tickers:
        api_sym = to_api_ticker(ticker)
        stock_df = df[df["symbol"] == api_sym][["report_date", "close"]].copy()
        try:
            beta_val = _compute_beta(stock_df, bench_df)
            if beta_val is not None:
                rows.append({"ticker": ticker, "beta": str(beta_val)})
            else:
                failed.append(ticker)
        except Exception:
            failed.append(ticker)

    if failed:
        print(f"WARNING: {len(failed)} tickers had insufficient data for beta: "
              f"{', '.join(sorted(failed)[:20])}", file=sys.stderr)

    rows.sort(key=lambda r: r["ticker"])

    # Upsert into Supabase
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    db_rows = [(r["ticker"], r["beta"]) for r in rows]
    if db_rows:
        execute_values(cur,
            """INSERT INTO stock_betas (ticker, beta)
               VALUES %s
               ON CONFLICT (ticker) DO UPDATE SET beta = EXCLUDED.beta""",
            db_rows, page_size=1000,
        )

    cur.close()
    conn.close()
    print(f"Upserted {len(rows)} rows into stock_betas table")


# ---------------------------------------------------------------------------
# Phase 3 — Update stocks.csv with computed financial values
# ---------------------------------------------------------------------------

def update_stocks_financials(
    price_rows: list[tuple[str, str, float]],
    eps_lookup: dict[str, dict[str, tuple[float, float]]],
) -> None:
    """Update the stocks Supabase table with computed financial values.

    Computes from price_rows: price (latest close), 52w_high, 52w_low
    Computes from eps_lookup: eps (TTM), pe_ratio (price / TTM EPS)
    Clears dividend_yield (no dividend data available from stock history)
    """
    # Build per-ticker sorted price lists
    ticker_prices: dict[str, list[tuple[str, float]]] = {}
    for date_str, ticker, close in price_rows:
        ticker_prices.setdefault(ticker, []).append((date_str, close))
    for prices in ticker_prices.values():
        prices.sort(key=lambda x: x[0])

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    updated = 0
    for ticker, prices in ticker_prices.items():
        latest_close = prices[-1][1]
        price_str = str(round(latest_close, 2))

        recent = [p for _, p in prices[-252:]]
        high_52w = str(round(max(recent), 2))
        low_52w = str(round(min(recent), 2))

        ticker_eps = eps_lookup.get(ticker, {})
        if ticker_eps:
            sorted_dates = sorted(ticker_eps.keys(), reverse=True)
            last_4 = sorted_dates[:4]
            ttm_eps = sum(ticker_eps[d][1] for d in last_4)
            eps_str = str(round(ttm_eps, 2))
            if ttm_eps > 0:
                pe_str = str(round(latest_close / ttm_eps, 1))
            else:
                pe_str = ""
        else:
            eps_str = ""
            pe_str = ""

        cur.execute(
            """UPDATE stocks SET
                   price = %s, "52w_high" = %s, "52w_low" = %s,
                   eps = %s, pe_ratio = %s, dividend_yield = ''
               WHERE ticker = %s""",
            (price_str, high_52w, low_52w, eps_str, pe_str, ticker),
        )
        updated += 1

    cur.close()
    conn.close()
    print(f"Updated stocks table — {updated} tickers with computed financials")


# ---------------------------------------------------------------------------
# Write output
# ---------------------------------------------------------------------------

def write_stock_history(
    price_rows: list[tuple[str, str, float]],
    eps_lookup: dict[str, dict[str, tuple[float, float]]],
) -> None:
    """Upsert stock_history rows into Supabase."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    db_rows = []
    for date_str, ticker, close in price_rows:
        ticker_eps = eps_lookup.get(ticker, {})
        eps_entry = ticker_eps.get(date_str)
        if eps_entry:
            db_rows.append((date_str, ticker, str(close), str(eps_entry[0]), str(eps_entry[1])))
        else:
            db_rows.append((date_str, ticker, str(close), "", ""))

    # Bulk upsert in batches
    batch_size = 5000
    for i in range(0, len(db_rows), batch_size):
        batch = db_rows[i : i + batch_size]
        execute_values(cur,
            """INSERT INTO stock_history (date, ticker, close, eps_estimate, eps_actual)
               VALUES %s
               ON CONFLICT (date, ticker) DO UPDATE SET
                   close = EXCLUDED.close,
                   eps_estimate = EXCLUDED.eps_estimate,
                   eps_actual = EXCLUDED.eps_actual""",
            batch, page_size=batch_size,
        )
        if len(db_rows) > batch_size:
            print(f"  ... stock_history: upserted {min(i + batch_size, len(db_rows))}/{len(db_rows)} rows")

    cur.close()
    conn.close()

    unique_tickers = {r[1] for r in price_rows}
    dates = {r[0] for r in price_rows}
    print(f"\nUpserted {len(price_rows)} rows into stock_history table")
    print(f"Tickers: {len(unique_tickers)}, Date range: {min(dates)} to {max(dates)}")


# ---------------------------------------------------------------------------
# Phase 0 — Load tickers into Supabase
# ---------------------------------------------------------------------------

def load_tickers_to_db(tickers_list: list[str]) -> None:
    """Verify tickers exist in the Supabase stocks table.

    Previously this read from stocks.csv and upserted into Supabase.
    Now that data lives in Supabase natively, this just verifies the table.
    """
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM stocks")
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    print(f"Verified {count} tickers in Supabase stocks table")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download stock prices and EPS data into stock_history.csv"
    )
    parser.add_argument("--fresh", action="store_true",
                        help="Re-fetch all EPS (ignore checkpoint)")
    parser.add_argument("--synthetic-only", action="store_true",
                        help="Skip real EPS fetches, use synthetic EPS only")
    parser.add_argument("--prices-only", action="store_true",
                        help="Skip EPS entirely (empty EPS columns)")
    parser.add_argument("--skip-calendar", action="store_true",
                        help="Skip earnings calendar phase")
    parser.add_argument("--skip-statements", action="store_true",
                        help="Skip financial statements phase")
    parser.add_argument("--skip-beta", action="store_true",
                        help="Skip stock beta phase")
    parser.add_argument("--skip-tickers", action="store_true",
                        help="Skip tickers DB upsert phase")
    parser.add_argument("--start-date", default="2015-01-01",
                        help="Price history start date (default: 2015-01-01)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # --- Phase 0: Load tickers into Supabase ---
    tickers = load_tickers()
    print(f"Found {len(tickers)} tickers in stocks.csv")

    if args.skip_tickers:
        print("\n--skip-tickers: skipping tickers DB upsert")
    else:
        print("=" * 60)
        print("Phase 0: Loading tickers into Supabase")
        print("=" * 60)
        load_tickers_to_db(tickers)

    # --- Phase 1: Prices ---
    print("\n" + "=" * 60)
    print("Phase 1: Downloading prices")
    print("=" * 60)
    price_rows = fetch_prices(tickers, args.start_date)

    # --- Phase 2: EPS ---
    eps_lookup: dict[str, dict[str, tuple[float, float]]] = {}

    if args.prices_only:
        print("\n--prices-only: skipping EPS")
    elif args.synthetic_only:
        print("\n" + "=" * 60)
        print("Phase 2: Generating synthetic EPS (--synthetic-only)")
        print("=" * 60)
        sectors = load_sectors()
        eps_lookup = generate_synthetic_eps(price_rows, sectors)
    else:
        print("\n" + "=" * 60)
        print("Phase 2: Fetching real EPS from defeatbeta-api")
        print("=" * 60)
        sectors = load_sectors()
        eps_actuals, failed = fetch_real_eps(tickers, args.fresh)

        # Build lookup with real actuals and synthetic estimates
        eps_lookup = build_eps_lookup(eps_actuals, price_rows, sectors)

        # Fall back to synthetic EPS for failed tickers and those without data
        tickers_without_eps = {t for t in tickers if t not in eps_actuals}
        tickers_without_eps.update(failed)
        if tickers_without_eps:
            print(f"\nGenerating synthetic EPS for {len(tickers_without_eps)} "
                  f"tickers without real data...")
            synthetic = generate_synthetic_eps(price_rows, sectors, tickers_without_eps)
            for ticker, dates in synthetic.items():
                if ticker not in eps_lookup:
                    eps_lookup[ticker] = dates

        # Clean up checkpoint if all tickers succeeded
        if not failed and len(eps_actuals) >= len(tickers) and CHECKPOINT.exists():
            CHECKPOINT.unlink()
            print("Checkpoint removed (all tickers complete)")

    # --- Write output ---
    print("\n" + "=" * 60)
    print("Phase 3: Writing stock_history to Supabase")
    print("=" * 60)
    write_stock_history(price_rows, eps_lookup)

    # --- Update stocks table with computed financials ---
    print("\n" + "=" * 60)
    print("Phase 4: Updating stocks table with computed financials")
    print("=" * 60)
    update_stocks_financials(price_rows, eps_lookup)

    # --- Phase 5: Earnings Calendar ---
    if args.skip_calendar:
        print("\n--skip-calendar: skipping earnings calendar")
    else:
        print("\n" + "=" * 60)
        print("Phase 5: Downloading earnings calendar")
        print("=" * 60)
        fetch_earnings_calendars(tickers)

    # --- Phase 6: Financial Statements (Supabase upsert) ---
    if args.skip_statements:
        print("\n--skip-statements: skipping financial statements")
    else:
        print("\n" + "=" * 60)
        print("Phase 6: Downloading financial statements → Supabase")
        print("=" * 60)
        fetch_financial_statements(tickers)

    # --- Phase 7: Stock Beta ---
    if args.skip_beta:
        print("\n--skip-beta: skipping stock beta")
    else:
        print("\n" + "=" * 60)
        print("Phase 7: Downloading stock beta")
        print("=" * 60)
        fetch_betas(tickers)

    print("\nDone!")


if __name__ == "__main__":
    main()
