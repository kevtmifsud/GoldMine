#!/usr/bin/env python3
"""Unified data update script for GoldMine.

Phases (weekly, default):
  1. Prices           — Bulk DuckDB query → stock_history
  2. EPS              — Bulk DuckDB query → stock_history
  3. Write stock_history — Upsert combined prices + EPS
  4. Update stocks    — Derived from latest prices/EPS
  5. Earnings Calendar — Bulk DuckDB + Finnhub
  6. Financial Stmts  — 6 bulk DuckDB queries → financial_metrics
  7. Stock Beta       — Bulk DuckDB + local computation → stock_betas
  8. SEC Filings      — Per-ticker threaded (all tickers) → sec_filings
  9. Transcripts      — Per-ticker sequential + checkpoint → transcripts_list

Phases (monthly, --include-profiles):
  10. Company Info    — Per-ticker threaded → stocks
  11. Officers        — Per-ticker threaded → people

CLI:
  python scripts/update_all_data.py                          # Weekly incremental
  python scripts/update_all_data.py --full                   # Full backfill
  python scripts/update_all_data.py --include-profiles       # Also run info + officers
  python scripts/update_all_data.py --only prices            # Single phase
  python scripts/update_all_data.py --only transcripts       # Single phase
  python scripts/update_all_data.py --only filings           # Single phase
  python scripts/update_all_data.py --only statements        # Single phase
  python scripts/update_all_data.py --workers 20             # Thread pool size
  python scripts/update_all_data.py --fresh                  # Ignore all checkpoints
  python scripts/update_all_data.py --start-date 2020-01-01  # Override history start
"""

from __future__ import annotations

import argparse
import bisect
import json
import logging
import math
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

import finnhub
import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from defeatbeta_api.client.duckdb_client import get_duckdb_client
from defeatbeta_api.client.hugging_face_client import HuggingFaceClient
from defeatbeta_api.data.ticker import Ticker
from dotenv import load_dotenv
from tabulate import tabulate

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")

DATABASE_URL = os.environ.get(
    "SUPABASE_DATABASE_URL",
    "postgresql://postgres:sC.g6Wf#9h.Bf_f@db.ybjvfeevaxujenwvoewg.supabase.co:5432/postgres",
)

FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
FINNHUB_LOOKAHEAD_DAYS = 90
FINNHUB_CHUNK_DAYS = 7

BETA_PERIOD_YEARS = 5
BETA_BENCHMARK = "SPY"

DEFAULT_START_DATE = "2015-01-01"
DEFAULT_WORKERS = 10
DEFAULT_MIN_YEAR = 2015

CHECKPOINT_DIR = ROOT / "scripts"
INFO_CHECKPOINT = CHECKPOINT_DIR / ".info_checkpoint.json"
OFFICERS_CHECKPOINT = CHECKPOINT_DIR / ".officers_checkpoint.json"

STATEMENT_TYPES = [
    ("income_statement", "quarterly"),
    ("income_statement", "annual"),
    ("balance_sheet", "quarterly"),
    ("balance_sheet", "annual"),
    ("cash_flow", "quarterly"),
    ("cash_flow", "annual"),
]

ALLOWED_FORM_TYPES = {
    "10-K", "10-K/A", "10-Q", "10-Q/A",
    "8-K", "8-K/A", "DEF 14A", "DEFA14A",
}

SECTOR_PE = {
    "Technology": 25, "Healthcare": 22, "Financials": 14,
    "Consumer Discretionary": 20, "Communication Services": 18,
    "Industrials": 18, "Consumer Staples": 22, "Energy": 12,
    "Utilities": 16, "Materials": 15, "Real Estate": 35,
}
DEFAULT_PE = 20

INFO_COLUMNS = [
    "address", "city", "phone", "zip",
    "long_business_summary", "full_time_employees", "web_site", "report_date",
]

OFFICERS_API_FIELDS = ["name", "title", "age", "born", "pay", "exercised", "unexercised"]

PEOPLE_COLUMNS = [
    "person_id", "name", "title", "organization", "type", "tickers",
    "age", "born", "pay", "exercised", "unexercised",
]

_TL_COLS = [
    "transcripts_id", "symbol", "fiscal_year", "fiscal_quarter",
    "report_date", "transcripts",
]

_SEC_COLS = [
    "accession_number", "symbol", "cik", "company_name", "form_type",
    "form_type_description", "filing_date", "report_date",
    "acceptance_date_time", "filing_url", "primary_document",
]

_EDGAR_UA = "GoldMine admin@goldmine.dev"

VALID_PHASES = [
    "prices", "calendar", "statements", "beta",
    "filings", "transcripts", "info", "officers",
    "consensus_estimates", "buyside_estimates",
]

random.seed(42)
_checkpoint_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Shared infrastructure
# ---------------------------------------------------------------------------

def get_db() -> psycopg2.extensions.connection:
    """Open a psycopg2 connection with autocommit."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn


def load_tickers(conn: psycopg2.extensions.connection) -> list[str]:
    """Read tickers from the stocks Supabase table."""
    cur = conn.cursor()
    cur.execute("SELECT ticker FROM stocks ORDER BY ticker")
    tickers = [row[0] for row in cur.fetchall()]
    cur.close()
    return tickers


def load_sectors(conn: psycopg2.extensions.connection) -> dict[str, str]:
    """Load ticker -> sector mapping."""
    cur = conn.cursor()
    cur.execute("SELECT ticker, sector FROM stocks")
    sectors = {row[0]: row[1] or "" for row in cur.fetchall()}
    cur.close()
    return sectors


def to_api_ticker(ticker: str) -> str:
    """defeatbeta-api uses Yahoo Finance format (dashes instead of dots)."""
    return ticker.replace(".", "-")


def from_api_ticker(symbol: str) -> str:
    """Convert API symbol (BRK-B) back to our ticker format (BRK.B)."""
    return symbol.replace("-", ".")


def _build_symbol_in_clause(tickers: list[str]) -> str:
    """Build a SQL IN clause with API-format ticker symbols."""
    return ", ".join(f"'{to_api_ticker(t)}'" for t in tickers)


def _get_parquet_url(table_name: str) -> str:
    """Get the HuggingFace parquet URL for a given table."""
    return HuggingFaceClient().get_url_path(table_name)


def _bulk_query(sql: str) -> pd.DataFrame:
    """Execute a SQL query against the DuckDB singleton."""
    db = get_duckdb_client(log_level=logging.WARNING)
    return db.query(sql)


def load_checkpoint(path: Path) -> dict:
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def save_checkpoint(path: Path, data: dict) -> None:
    with _checkpoint_lock:
        with open(path, "w") as f:
            json.dump(data, f)


@contextmanager
def phase_timer(name: str):
    """Context manager for timing and printing phase execution."""
    print(f"\n{'=' * 60}")
    print(f"Phase: {name}")
    print("=" * 60)
    start = time.time()
    yield
    elapsed = time.time() - start
    print(f"  [{name}] completed in {elapsed:.1f}s")


def _normalize_name(name: str) -> str:
    """Lowercase, collapse whitespace for name matching."""
    return re.sub(r"\s+", " ", name.strip().lower())


# ---------------------------------------------------------------------------
# Phases 1-2: Bulk prices + EPS
# ---------------------------------------------------------------------------

def fetch_bulk_prices(
    tickers: list[str],
    start_date: str,
    last_dates: dict[str, str] | None,
) -> list[tuple[str, str, float]]:
    """Bulk-fetch daily closing prices via single DuckDB query.

    Args:
        tickers: All ticker symbols.
        start_date: Global start date (for --full mode).
        last_dates: {ticker: max_date} from DB for incremental filtering.
                    If None, fetches all dates from start_date.
    """
    symbols_clause = _build_symbol_in_clause(tickers)
    url = _get_parquet_url("stock_prices")

    # For incremental: use the earliest last_date as the SQL filter
    # (we do per-ticker filtering client-side for precision)
    if last_dates:
        date_filter = min(last_dates.values()) if last_dates else start_date
    else:
        date_filter = start_date

    print(f"  Bulk query: prices from {date_filter} for {len(tickers)} tickers...")
    sql = (
        f"SELECT symbol, report_date, close "
        f"FROM '{url}' "
        f"WHERE symbol IN ({symbols_clause}) "
        f"  AND report_date >= '{date_filter}' "
        f"ORDER BY symbol, report_date"
    )
    df = _bulk_query(sql)

    if df is None or df.empty:
        print("  WARNING: No price data returned", file=sys.stderr)
        return []

    rows: list[tuple[str, str, float]] = []
    for _, row in df.iterrows():
        ticker = from_api_ticker(str(row["symbol"]))
        date_str = str(row["report_date"])[:10]

        # Incremental filter: skip rows already in DB for this ticker
        if last_dates and ticker in last_dates and date_str <= last_dates[ticker]:
            continue

        close = round(float(row["close"]), 2)
        rows.append((date_str, ticker, close))

    unique = len({r[1] for r in rows})
    print(f"  Got {len(rows)} new price rows for {unique} tickers")
    return rows


def fetch_bulk_eps(tickers: list[str]) -> dict[str, dict[str, float]]:
    """Bulk-fetch quarterly EPS actuals via single DuckDB query.

    Returns {ticker: {date_str: eps_actual}}.
    """
    symbols_clause = _build_symbol_in_clause(tickers)
    url = _get_parquet_url("stock_tailing_eps")

    print(f"  Bulk query: EPS for {len(tickers)} tickers...")
    sql = (
        f"SELECT symbol, report_date, eps "
        f"FROM '{url}' "
        f"WHERE symbol IN ({symbols_clause}) "
        f"ORDER BY symbol, report_date"
    )
    df = _bulk_query(sql)

    if df is None or df.empty:
        print("  WARNING: No EPS data returned", file=sys.stderr)
        return {}

    eps_actuals: dict[str, dict[str, float]] = {}
    for _, row in df.iterrows():
        ticker = from_api_ticker(str(row["symbol"]))
        date_str = str(row["report_date"])[:10]
        eps_val = row.get("eps")
        if eps_val is None or (isinstance(eps_val, float) and math.isnan(eps_val)):
            continue
        eps_actuals.setdefault(ticker, {})[date_str] = round(float(eps_val), 2)

    total = sum(len(v) for v in eps_actuals.values())
    print(f"  Got {total} EPS data points for {len(eps_actuals)} tickers")
    return eps_actuals


# ---------------------------------------------------------------------------
# Phase 2b/2c: EPS lookup + synthetic EPS (reused from existing)
# ---------------------------------------------------------------------------

def build_eps_lookup(
    eps_actuals: dict[str, dict[str, float]],
    price_rows: list[tuple[str, str, float]],
    sectors: dict[str, str],
) -> dict[str, dict[str, tuple[float, float]]]:
    """Combine real EPS actuals with synthetic EPS estimates.

    Returns {ticker: {date_str: (eps_estimate, eps_actual)}}.
    """
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
    print(f"  EPS lookup: {total} data points across {len(eps_lookup)} tickers")
    return eps_lookup


def _get_quarterly_dates(dates: list[str]) -> set[str]:
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
    """Derive EPS from prices and sector P/E ratios (fallback)."""
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
        quarterly_dates = _get_quarterly_dates(dates)
        date_to_close = {d: c for d, c in entries}
        ticker_eps: dict[str, tuple[float, float]] = {}
        for date in quarterly_dates:
            if date not in date_to_close:
                continue
            close = date_to_close[date]
            quarterly_eps = close / pe / 4
            surprise = random.uniform(-0.05, 0.10)
            eps_estimate = round(quarterly_eps, 2)
            eps_actual = round(quarterly_eps * (1 + surprise), 2)
            ticker_eps[date] = (eps_estimate, eps_actual)
        if ticker_eps:
            eps_lookup[ticker] = ticker_eps

    total = sum(len(v) for v in eps_lookup.values())
    print(f"  Synthetic EPS: {total} data points across {len(eps_lookup)} tickers")
    return eps_lookup


# ---------------------------------------------------------------------------
# Phase 3: Write stock_history
# ---------------------------------------------------------------------------

def write_stock_history(
    conn: psycopg2.extensions.connection,
    price_rows: list[tuple[str, str, float]],
    eps_lookup: dict[str, dict[str, tuple[float, float]]],
) -> None:
    """Upsert stock_history rows into Supabase."""
    cur = conn.cursor()
    db_rows = []
    for date_str, ticker, close in price_rows:
        ticker_eps = eps_lookup.get(ticker, {})
        eps_entry = ticker_eps.get(date_str)
        if eps_entry:
            db_rows.append((date_str, ticker, str(close), str(eps_entry[0]), str(eps_entry[1])))
        else:
            db_rows.append((date_str, ticker, str(close), "", ""))

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
            print(f"    stock_history: upserted {min(i + batch_size, len(db_rows))}"
                  f"/{len(db_rows)} rows")
    cur.close()

    unique_tickers = {r[1] for r in price_rows}
    dates = {r[0] for r in price_rows}
    if dates:
        print(f"  Upserted {len(price_rows)} rows ({len(unique_tickers)} tickers, "
              f"{min(dates)} to {max(dates)})")
    else:
        print("  No rows to upsert")


# ---------------------------------------------------------------------------
# Phase 4: Update stocks table
# ---------------------------------------------------------------------------

def update_stocks_financials(
    conn: psycopg2.extensions.connection,
    price_rows: list[tuple[str, str, float]],
    eps_lookup: dict[str, dict[str, tuple[float, float]]],
) -> None:
    """Update stocks table with computed financials."""
    ticker_prices: dict[str, list[tuple[str, float]]] = {}
    for date_str, ticker, close in price_rows:
        ticker_prices.setdefault(ticker, []).append((date_str, close))
    for prices in ticker_prices.values():
        prices.sort(key=lambda x: x[0])

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
            pe_str = str(round(latest_close / ttm_eps, 1)) if ttm_eps > 0 else ""
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
    print(f"  Updated {updated} tickers in stocks table")


# ---------------------------------------------------------------------------
# Phase 5: Earnings Calendar
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
    """Fetch upcoming earnings dates from Finnhub in weekly chunks."""
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
                print(f"  WARNING: {start_str} to {end_str} hit 1500-row cap",
                      file=sys.stderr)

            for e in entries:
                sym = e.get("symbol", "")
                if sym not in api_tickers:
                    continue
                hour = e.get("hour", "")
                if hour == "bmo":
                    time_str = "before-market-open"
                elif hour == "amc":
                    time_str = "after-market-close"
                else:
                    time_str = "time-not-supplied"

                quarter = e.get("quarter")
                year = e.get("year")
                if quarter and year:
                    q_month = {1: 3, 2: 6, 3: 9, 4: 12}.get(quarter, 12)
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
            print(f"  WARNING: Finnhub query {start_str}\u2013{end_str} failed: {exc}",
                  file=sys.stderr)

        chunk_start = chunk_end
        time.sleep(1)

    unique = len({r["ticker"] for r in all_rows})
    print(f"  Finnhub future: {len(all_rows)} rows ({unique} tickers)")
    return all_rows


def run_phase_calendar(conn: psycopg2.extensions.connection, tickers: list[str]) -> None:
    """Phase 5: Merge DefeatBeta historical + Finnhub future earnings calendars."""
    historical = _fetch_historical_calendar(tickers)
    future = _fetch_finnhub_calendar(tickers)

    seen: set[tuple[str, str]] = set()
    merged: list[dict[str, str]] = []
    for row in historical:
        key = (row["ticker"], row["report_date"])
        if key not in seen:
            seen.add(key)
            merged.append(row)
    for row in future:
        key = (row["ticker"], row["report_date"])
        if key not in seen:
            seen.add(key)
            merged.append(row)

    merged.sort(key=lambda r: (r["ticker"], r["report_date"]))

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

    unique_tickers = len({r["ticker"] for r in merged})
    print(f"  Upserted {len(merged)} rows ({unique_tickers} tickers)")


# ---------------------------------------------------------------------------
# Phase 6: Financial Statements
# ---------------------------------------------------------------------------

def run_phase_statements(
    conn: psycopg2.extensions.connection,
    tickers: list[str],
    incremental: bool,
) -> None:
    """Phase 6: Bulk-fetch financial statements and upsert."""
    symbols_clause = _build_symbol_in_clause(tickers)
    url = _get_parquet_url("stock_statement")

    # Get incremental bounds
    max_period_end: str | None = None
    if incremental:
        cur = conn.cursor()
        cur.execute("SELECT MAX(period_end) FROM financial_metrics")
        row = cur.fetchone()
        if row and row[0]:
            max_period_end = str(row[0])[:10]
        cur.close()
        if max_period_end:
            print(f"  Incremental: fetching statements after {max_period_end}")

    total_rows = 0
    cur = conn.cursor()

    for finance_type, period_type in STATEMENT_TYPES:
        date_clause = ""
        if max_period_end:
            date_clause = f" AND report_date > '{max_period_end}'"

        sql = (
            f"SELECT symbol, item_name, report_date, item_value "
            f"FROM '{url}' "
            f"WHERE symbol IN ({symbols_clause}) "
            f"  AND finance_type = '{finance_type}' "
            f"  AND period_type = '{period_type}'"
            f"{date_clause} "
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
                """INSERT INTO financial_metrics (ticker, metric_name, period_end,
                                                  period_type, value)
                   VALUES %s
                   ON CONFLICT (ticker, metric_name, period_end, period_type)
                   DO UPDATE SET value = EXCLUDED.value""",
                rows, page_size=1000,
            )

        unique = df["symbol"].nunique() if df is not None and not df.empty else 0
        label = f"{finance_type}/{period_type}"
        print(f"    {label}: {len(rows)} rows ({unique} tickers)")
        total_rows += len(rows)

    cur.close()
    print(f"  Total upserted: {total_rows} rows")


# ---------------------------------------------------------------------------
# Phase 7: Stock Beta
# ---------------------------------------------------------------------------

def _compute_beta(stock_prices: pd.DataFrame, bench_prices: pd.DataFrame) -> float | None:
    """Compute 5-year monthly beta from two DataFrames of (report_date, close)."""
    if stock_prices.empty or bench_prices.empty:
        return None
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


def run_phase_beta(conn: psycopg2.extensions.connection, tickers: list[str]) -> None:
    """Phase 7: Bulk-fetch prices, compute beta locally, upsert."""
    end_date_str = HuggingFaceClient().get_data_update_time()
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
    start_date = end_date - timedelta(days=BETA_PERIOD_YEARS * 365)
    start_str = start_date.strftime("%Y-%m-%d")

    all_symbols = [to_api_ticker(t) for t in tickers] + [BETA_BENCHMARK]
    symbols_clause = ", ".join(f"'{s}'" for s in all_symbols)
    url = _get_parquet_url("stock_prices")

    print(f"  Bulk query: {len(tickers)} tickers + {BETA_BENCHMARK} prices for beta...")

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
        print("  WARNING: No price data returned for beta", file=sys.stderr)
        return

    bench_df = df[df["symbol"] == BETA_BENCHMARK][["report_date", "close"]].copy()

    print(f"  Computing beta for {len(tickers)} tickers...")
    rows: list[tuple[str, float]] = []
    failed = 0
    for ticker in tickers:
        api_sym = to_api_ticker(ticker)
        stock_df = df[df["symbol"] == api_sym][["report_date", "close"]].copy()
        try:
            beta_val = _compute_beta(stock_df, bench_df)
            if beta_val is not None:
                rows.append((ticker, beta_val))
            else:
                failed += 1
        except Exception:
            failed += 1

    if failed:
        print(f"  WARNING: {failed} tickers had insufficient data for beta",
              file=sys.stderr)

    cur = conn.cursor()
    if rows:
        execute_values(cur,
            """INSERT INTO stock_betas (ticker, beta)
               VALUES %s
               ON CONFLICT (ticker) DO UPDATE SET beta = EXCLUDED.beta""",
            rows, page_size=1000,
        )
    cur.close()
    print(f"  Upserted {len(rows)} beta values")


# ---------------------------------------------------------------------------
# Phase 8: SEC Filings (all tickers — bulk DuckDB + EDGAR enrichment)
# ---------------------------------------------------------------------------

def _fetch_edgar_submissions(cik: str) -> dict[str, str]:
    """Fetch primaryDocument for all filings of a CIK from data.sec.gov."""
    cik_padded = cik.lstrip("0").zfill(10)
    base_url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    req = Request(base_url, headers={"User-Agent": _EDGAR_UA})
    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except Exception:
        return {}

    result: dict[str, str] = {}
    filings_obj = data.get("filings", {})
    recent = filings_obj.get("recent", {})
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    for acc, pdoc in zip(accessions, primary_docs):
        if acc and pdoc:
            result[acc] = pdoc

    for overflow in filings_obj.get("files", []):
        fname = overflow.get("name", "")
        if not fname:
            continue
        overflow_url = f"https://data.sec.gov/submissions/{fname}"
        overflow_req = Request(overflow_url, headers={"User-Agent": _EDGAR_UA})
        time.sleep(0.15)
        try:
            with urlopen(overflow_req, timeout=30) as resp:
                odata = json.loads(resp.read())
            o_acc = odata.get("accessionNumber", [])
            o_pdoc = odata.get("primaryDocument", [])
            for acc, pdoc in zip(o_acc, o_pdoc):
                if acc and pdoc:
                    result[acc] = pdoc
        except Exception:
            pass

    return result


def _enrich_filings_with_primary_doc(all_filings: list[dict]) -> None:
    """Add primary_document field to filings by querying EDGAR."""
    cik_set: dict[str, str] = {}
    for f in all_filings:
        cik = f.get("cik", "")
        if cik and cik not in cik_set:
            cik_set[cik] = f.get("symbol", "?")

    print(f"  Fetching primary documents from EDGAR for {len(cik_set)} CIKs...")

    all_lookups: dict[str, str] = {}
    for i, (cik, sym) in enumerate(cik_set.items(), 1):
        time.sleep(0.15)
        lookup = _fetch_edgar_submissions(cik)
        all_lookups.update(lookup)
        if i % 50 == 0 or i == len(cik_set):
            print(f"    [{i}/{len(cik_set)}] EDGAR lookups done...", flush=True)

    matched = 0
    for f in all_filings:
        acc = f.get("accession_number", "")
        pdoc = all_lookups.get(acc, "")
        f["primary_document"] = pdoc
        if pdoc:
            matched += 1
    print(f"  Matched primary documents for {matched}/{len(all_filings)} filings")


def run_phase_filings(
    conn: psycopg2.extensions.connection,
    tickers: list[str],
    workers: int,
    incremental: bool,
) -> None:
    """Phase 8: SEC filings via bulk DuckDB query + EDGAR enrichment."""
    symbols_clause = _build_symbol_in_clause(tickers)
    url = _get_parquet_url("stock_sec_filing")
    form_types_clause = ", ".join(f"'{ft}'" for ft in ALLOWED_FORM_TYPES)

    # Incremental: only fetch filings after the latest known filing date
    date_clause = ""
    if incremental:
        cur = conn.cursor()
        cur.execute("SELECT MAX(filing_date) FROM sec_filings")
        row = cur.fetchone()
        cur.close()
        if row and row[0]:
            max_date = str(row[0])[:10]
            date_clause = f" AND filing_date > '{max_date}'"
            print(f"  Incremental: fetching filings after {max_date}")

    print(f"  Bulk query: SEC filings for {len(tickers)} tickers...")
    sql = (
        f"SELECT symbol, cik, accession_number, company_name, form_type, "
        f"       form_type_description, filing_date, report_date, "
        f"       acceptance_date_time, filing_url "
        f"FROM '{url}' "
        f"WHERE symbol IN ({symbols_clause}) "
        f"  AND form_type IN ({form_types_clause})"
        f"{date_clause} "
        f"ORDER BY symbol, filing_date"
    )
    df = _bulk_query(sql)

    if df is None or df.empty:
        print("  No new filings data")
        return

    # Convert to list of dicts
    all_filings: list[dict] = []
    for _, row in df.iterrows():
        filing = {
            "symbol": from_api_ticker(str(row["symbol"])),
            "cik": str(row.get("cik", "")).strip(),
            "accession_number": str(row.get("accession_number", "")).strip(),
            "company_name": str(row.get("company_name", "")).strip(),
            "form_type": str(row.get("form_type", "")).strip(),
            "form_type_description": str(row.get("form_type_description", "")).strip(),
            "filing_date": str(row.get("filing_date", ""))[:10],
            "report_date": str(row.get("report_date", ""))[:10],
            "acceptance_date_time": str(row.get("acceptance_date_time", "")).strip(),
            "filing_url": str(row.get("filing_url", "")).strip(),
        }
        if filing["accession_number"]:
            all_filings.append(filing)

    unique = len({f["symbol"] for f in all_filings})
    print(f"  Got {len(all_filings)} filings for {unique} tickers from bulk query")

    # EDGAR enrichment for primary_document
    _enrich_filings_with_primary_doc(all_filings)

    # Append primary_document to filing_url so it points to the actual document
    for f in all_filings:
        pd_ = f.get("primary_document", "")
        base = f.get("filing_url", "")
        if pd_ and base and not base.endswith(pd_):
            f["filing_url"] = f"{base.rstrip('/')}/{pd_}"

    # Deduplicate by accession_number (parquet may have dupes)
    seen_acc: set[str] = set()
    deduped: list[dict] = []
    for f in all_filings:
        acc = f.get("accession_number", "")
        if acc and acc not in seen_acc:
            seen_acc.add(acc)
            deduped.append(f)
    all_filings = deduped

    # Upsert
    cur = conn.cursor()
    db_rows = [tuple(f.get(col, "") for col in _SEC_COLS) for f in all_filings]

    if db_rows:
        batch_size = 1000
        for i in range(0, len(db_rows), batch_size):
            batch = db_rows[i : i + batch_size]
            execute_values(cur,
                """INSERT INTO sec_filings (accession_number, symbol, cik, company_name,
                                            form_type, form_type_description, filing_date,
                                            report_date, acceptance_date_time, filing_url,
                                            primary_document)
                   VALUES %s
                   ON CONFLICT (accession_number) DO UPDATE SET
                       symbol = EXCLUDED.symbol, cik = EXCLUDED.cik,
                       company_name = EXCLUDED.company_name,
                       form_type = EXCLUDED.form_type,
                       form_type_description = EXCLUDED.form_type_description,
                       filing_date = EXCLUDED.filing_date,
                       report_date = EXCLUDED.report_date,
                       acceptance_date_time = EXCLUDED.acceptance_date_time,
                       filing_url = EXCLUDED.filing_url,
                       primary_document = EXCLUDED.primary_document""",
                batch, page_size=1000,
            )
    cur.close()
    print(f"  Upserted {len(db_rows)} filings ({unique} tickers)")


# ---------------------------------------------------------------------------
# Phase 9: Transcripts (all tickers — bulk DuckDB)
# ---------------------------------------------------------------------------

def _format_transcript(raw: object) -> str:
    """Format a raw transcript object (list of dicts / nested structure) to grid text."""
    if raw is None:
        return ""
    try:
        if hasattr(raw, 'tolist'):
            raw = raw.tolist()
        if not raw:
            return ""
        transcript_df = pd.DataFrame(raw)
        if transcript_df.empty:
            return ""
        return tabulate(transcript_df, headers="keys", tablefmt="grid", showindex=False)
    except Exception:
        return ""


def run_phase_transcripts(
    conn: psycopg2.extensions.connection,
    tickers: list[str],
    min_year: int,
    fresh: bool,
) -> None:
    """Phase 9: Bulk-fetch transcripts via DuckDB and upsert."""
    symbols_clause = _build_symbol_in_clause(tickers)
    url = _get_parquet_url("stock_earning_call_transcripts")

    # Incremental: find which tickers already have transcript text
    existing_ids: set[str] = set()
    if not fresh:
        cur = conn.cursor()
        cur.execute(
            "SELECT transcripts_id FROM transcripts_list "
            "WHERE transcripts IS NOT NULL AND transcripts != ''"
        )
        existing_ids = {row[0] for row in cur.fetchall()}
        cur.close()
        if existing_ids:
            print(f"  Incremental: {len(existing_ids)} transcript rows already populated")

    print(f"  Bulk query: transcripts for {len(tickers)} tickers "
          f"(min_year={min_year})...")
    sql = (
        f"SELECT symbol, fiscal_year, fiscal_quarter, report_date, "
        f"       transcripts, transcripts_id "
        f"FROM '{url}' "
        f"WHERE symbol IN ({symbols_clause}) "
        f"  AND fiscal_year >= {min_year} "
        f"ORDER BY symbol, fiscal_year, fiscal_quarter"
    )
    df = _bulk_query(sql)

    if df is None or df.empty:
        print("  No transcript data returned")
        return

    unique = df["symbol"].nunique()
    print(f"  Got {len(df)} transcript rows for {unique} tickers from bulk query")

    # Format and filter
    db_rows: list[tuple] = []
    formatted_count = 0

    for _, row in df.iterrows():
        ticker = from_api_ticker(str(row["symbol"]))
        fy = int(row["fiscal_year"])
        fq = int(row["fiscal_quarter"])
        report_date = str(row.get("report_date", ""))[:10]

        # Build transcript ID
        tid_raw = row.get("transcripts_id")
        if tid_raw is None or str(tid_raw) in ("", "<NA>", "nan"):
            tid = f"{ticker}-{fy}-Q{fq}"
        else:
            tid = str(tid_raw)

        # Skip if already populated in DB
        if tid in existing_ids:
            continue

        # Format transcript text
        raw = row.get("transcripts", None)
        formatted = _format_transcript(raw)
        if formatted:
            formatted_count += 1

        db_rows.append((tid, ticker, str(fy), str(fq), report_date, formatted))

    if not db_rows:
        print("  All transcripts already populated")
        return

    print(f"  Formatting complete: {formatted_count} transcripts with text, "
          f"{len(db_rows)} total rows to upsert")

    # Upsert in small batches with fresh connections (transcript blobs are
    # large and can cause remote connection timeouts on long runs)
    batch_size = 50
    for i in range(0, len(db_rows), batch_size):
        batch = db_rows[i : i + batch_size]
        batch_conn = get_db()
        cur = batch_conn.cursor()
        try:
            execute_values(cur,
                """INSERT INTO transcripts_list (transcripts_id, symbol, fiscal_year,
                                                 fiscal_quarter, report_date, transcripts)
                   VALUES %s
                   ON CONFLICT (transcripts_id) DO UPDATE SET
                       symbol = EXCLUDED.symbol, fiscal_year = EXCLUDED.fiscal_year,
                       fiscal_quarter = EXCLUDED.fiscal_quarter,
                       report_date = EXCLUDED.report_date,
                       transcripts = EXCLUDED.transcripts""",
                batch, page_size=50,
            )
        finally:
            cur.close()
            batch_conn.close()
        done = min(i + batch_size, len(db_rows))
        if done % 500 == 0 or done == len(db_rows):
            print(f"    transcripts: upserted {done}/{len(db_rows)} rows",
                  flush=True)

    unique_tickers = len({r[1] for r in db_rows})
    print(f"  Upserted {len(db_rows)} transcript rows ({unique_tickers} tickers, "
          f"{formatted_count} with text)")


# ---------------------------------------------------------------------------
# Phase 10: Company Info (--include-profiles)
# ---------------------------------------------------------------------------

def _fetch_info_for_ticker(ticker: str) -> dict | None:
    """Fetch company info fields for one ticker."""
    api_ticker = to_api_ticker(ticker)
    t = Ticker(api_ticker, log_level=logging.WARNING)
    df = t.info()
    if df is None or df.empty:
        return None
    row = df.iloc[0]
    info: dict = {}
    for col in INFO_COLUMNS:
        val = row.get(col, "")
        if val is None:
            val = ""
        info[col] = str(val).strip()
    return info


def _process_info_ticker(
    ticker: str,
    checkpoint: dict[str, dict],
) -> tuple[str, bool]:
    try:
        info = _fetch_info_for_ticker(ticker)
        if info:
            with _checkpoint_lock:
                checkpoint[ticker] = info
            save_checkpoint(INFO_CHECKPOINT, checkpoint)
            return ticker, True
        return ticker, False
    except Exception:
        return ticker, False


def run_phase_info(
    conn: psycopg2.extensions.connection,
    tickers: list[str],
    workers: int,
    fresh: bool,
) -> None:
    """Phase 10: Download stock info and update stocks table."""
    checkpoint: dict[str, dict] = {} if fresh else load_checkpoint(INFO_CHECKPOINT)
    if checkpoint and not fresh:
        print(f"  Resuming from checkpoint ({len(checkpoint)} tickers already fetched)")

    remaining = [t for t in tickers if t not in checkpoint]

    if not remaining:
        print("  All tickers already fetched (use --fresh to re-fetch)")
    else:
        print(f"  Fetching stock info for {len(remaining)} tickers "
              f"({workers} threads)...")

        completed = 0
        failed: list[str] = []

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_process_info_ticker, ticker, checkpoint): ticker
                for ticker in remaining
            }
            for future in as_completed(futures):
                ticker = futures[future]
                completed += 1
                try:
                    _, ok = future.result()
                    if not ok:
                        failed.append(ticker)
                    if completed % 50 == 0 or completed == len(remaining):
                        print(f"    [{completed}/{len(remaining)}] info fetched...",
                              flush=True)
                except Exception as e:
                    failed.append(ticker)
                    print(f"    [{completed}/{len(remaining)}] {ticker} -> "
                          f"ERROR: {e}", file=sys.stderr, flush=True)

        if failed:
            print(f"  WARNING: {len(failed)} tickers failed", file=sys.stderr)

    if not checkpoint:
        print("  No stock info data to merge")
        return

    cur = conn.cursor()
    merged_count = 0
    for ticker, info in checkpoint.items():
        cur.execute(
            """UPDATE stocks SET
                   address = %s, city = %s, phone = %s, zip = %s,
                   long_business_summary = %s, full_time_employees = %s,
                   web_site = %s, report_date = %s
               WHERE ticker = %s""",
            (
                info.get("address", ""), info.get("city", ""),
                info.get("phone", ""), info.get("zip", ""),
                info.get("long_business_summary", ""),
                info.get("full_time_employees", ""),
                info.get("web_site", ""), info.get("report_date", ""),
                ticker,
            ),
        )
        merged_count += 1
    cur.close()
    print(f"  Merged info for {merged_count} tickers into stocks table")

    if len(checkpoint) >= len(tickers) and INFO_CHECKPOINT.exists():
        INFO_CHECKPOINT.unlink()
        print("  Checkpoint removed (all tickers complete)")


# ---------------------------------------------------------------------------
# Phase 11: Officers (--include-profiles)
# ---------------------------------------------------------------------------

def _fetch_officers_for_ticker(ticker: str) -> list[dict] | None:
    """Fetch officers for one ticker."""
    api_ticker = to_api_ticker(ticker)
    t = Ticker(api_ticker, log_level=logging.WARNING)
    df = t.officers()
    if df is None or df.empty:
        return None
    officers: list[dict] = []
    for _, row in df.iterrows():
        officer: dict = {"symbol": ticker}
        for col in OFFICERS_API_FIELDS:
            val = row.get(col, "")
            if val is None:
                val = ""
            officer[col] = str(val).strip()
        officers.append(officer)
    return officers


def _process_officers_ticker(
    ticker: str,
    checkpoint: dict[str, list[dict]],
) -> tuple[str, int]:
    try:
        officers = _fetch_officers_for_ticker(ticker)
        if officers:
            with _checkpoint_lock:
                checkpoint[ticker] = officers
            save_checkpoint(OFFICERS_CHECKPOINT, checkpoint)
            return ticker, len(officers)
        return ticker, 0
    except Exception:
        return ticker, -1


def run_phase_officers(
    conn: psycopg2.extensions.connection,
    tickers: list[str],
    workers: int,
    fresh: bool,
) -> None:
    """Phase 11: Download stock officers and merge into people table."""
    checkpoint: dict[str, list[dict]] = {} if fresh else load_checkpoint(OFFICERS_CHECKPOINT)
    if checkpoint and not fresh:
        print(f"  Resuming from checkpoint ({len(checkpoint)} tickers already fetched)")

    remaining = [t for t in tickers if t not in checkpoint]

    if not remaining:
        print("  All tickers already fetched (use --fresh to re-fetch)")
    else:
        print(f"  Fetching officers for {len(remaining)} tickers "
              f"({workers} threads)...")

        completed = 0
        failed: list[str] = []

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_process_officers_ticker, ticker, checkpoint): ticker
                for ticker in remaining
            }
            for future in as_completed(futures):
                ticker = futures[future]
                completed += 1
                try:
                    _, count = future.result()
                    if count < 0:
                        failed.append(ticker)
                    if completed % 50 == 0 or completed == len(remaining):
                        print(f"    [{completed}/{len(remaining)}] officers fetched...",
                              flush=True)
                except Exception as e:
                    failed.append(ticker)
                    print(f"    [{completed}/{len(remaining)}] {ticker} -> "
                          f"ERROR: {e}", file=sys.stderr, flush=True)

        if failed:
            print(f"  WARNING: {len(failed)} tickers failed", file=sys.stderr)

    # Flatten all fetched officers
    all_officers: list[dict] = []
    for officers_list in checkpoint.values():
        all_officers.extend(officers_list)

    if not all_officers:
        print("  No officers data to merge")
        return

    cur = conn.cursor()
    cur.execute("SELECT person_id, name, title, organization, type, tickers, "
                "age, born, pay, exercised, unexercised FROM people")
    columns = [desc[0] for desc in cur.description]
    people: list[dict] = [
        {col: str(val) if val is not None else "" for col, val in zip(columns, row)}
        for row in cur.fetchall()
    ]

    name_to_person: dict[str, dict] = {}
    for p in people:
        name_to_person[_normalize_name(p["name"])] = p

    max_id = 0
    for p in people:
        pid = p.get("person_id", "")
        if pid.startswith("PER-"):
            try:
                max_id = max(max_id, int(pid.split("-")[1]))
            except ValueError:
                pass
    next_id = max_id + 1

    compensation_fields = ["age", "born", "pay", "exercised", "unexercised"]
    matched = 0
    new_records = 0

    for officer in all_officers:
        norm = _normalize_name(officer["name"])
        symbol = officer.get("symbol", "").strip()
        if norm in name_to_person:
            person = name_to_person[norm]
            matched += 1
            for field in compensation_fields:
                val = officer.get(field, "").strip()
                if val:
                    person[field] = val
            if symbol:
                existing = [
                    t.strip()
                    for t in person.get("tickers", "").split(";")
                    if t.strip()
                ]
                if symbol not in existing:
                    existing.append(symbol)
                    person["tickers"] = ";".join(existing)
        else:
            new_pid = f"PER-{next_id:04d}"
            next_id += 1
            new_records += 1
            new_person = {
                "person_id": new_pid,
                "name": officer["name"].strip(),
                "title": officer.get("title", "").strip(),
                "organization": "",
                "type": "executive",
                "tickers": symbol,
            }
            for field in compensation_fields:
                new_person[field] = officer.get(field, "").strip()
            people.append(new_person)
            name_to_person[norm] = new_person

    db_rows = [
        tuple(p.get(col, "") for col in PEOPLE_COLUMNS)
        for p in people
    ]
    if db_rows:
        execute_values(cur,
            """INSERT INTO people (person_id, name, title, organization, type,
                                   tickers, age, born, pay, exercised, unexercised)
               VALUES %s
               ON CONFLICT (person_id) DO UPDATE SET
                   name = EXCLUDED.name, title = EXCLUDED.title,
                   organization = EXCLUDED.organization, type = EXCLUDED.type,
                   tickers = EXCLUDED.tickers, age = EXCLUDED.age,
                   born = EXCLUDED.born, pay = EXCLUDED.pay,
                   exercised = EXCLUDED.exercised, unexercised = EXCLUDED.unexercised""",
            db_rows, page_size=1000,
        )

    cur.close()
    print(f"  Merged {matched} matched + {new_records} new officers "
          f"into {len(people)} total people rows")

    if len(checkpoint) >= len(tickers) and OFFICERS_CHECKPOINT.exists():
        OFFICERS_CHECKPOINT.unlink()
        print("  Checkpoint removed (all tickers complete)")


# ---------------------------------------------------------------------------
# CLI + Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Unified data update script for GoldMine"
    )
    parser.add_argument("--full", action="store_true",
                        help="Full backfill (ignore incremental bounds)")
    parser.add_argument("--include-profiles", action="store_true",
                        help="Also run company info + officers phases")
    parser.add_argument("--only", choices=VALID_PHASES,
                        help="Run only the specified phase")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"Thread pool size (default: {DEFAULT_WORKERS})")
    parser.add_argument("--fresh", action="store_true",
                        help="Ignore all checkpoints")
    parser.add_argument("--start-date", default=DEFAULT_START_DATE,
                        help=f"Price history start date (default: {DEFAULT_START_DATE})")
    parser.add_argument("--min-year", type=int, default=DEFAULT_MIN_YEAR,
                        help=f"Minimum transcript year (default: {DEFAULT_MIN_YEAR})")
    return parser.parse_args()


def _run_price_pipeline(
    conn: psycopg2.extensions.connection,
    tickers: list[str],
    args: argparse.Namespace,
    incremental: bool,
) -> None:
    """Run the tightly-coupled price/EPS/history/stocks pipeline."""
    sectors = load_sectors(conn)

    # Get incremental bounds
    last_dates: dict[str, str] | None = None
    if incremental:
        cur = conn.cursor()
        cur.execute("SELECT ticker, MAX(date) FROM stock_history GROUP BY ticker")
        last_dates = {
            row[0]: str(row[1])[:10] for row in cur.fetchall() if row[1]
        }
        cur.close()
        if last_dates:
            print(f"  Incremental: {len(last_dates)} tickers with existing data")

    price_rows = fetch_bulk_prices(tickers, args.start_date, last_dates)

    if not price_rows:
        print("  No new price data — skipping EPS/history/stocks phases")
        return

    # Bulk EPS
    eps_actuals = fetch_bulk_eps(tickers)
    eps_lookup = build_eps_lookup(eps_actuals, price_rows, sectors)

    # Synthetic fallback
    tickers_without_eps = {t for t in tickers if t not in eps_actuals}
    if tickers_without_eps:
        print(f"  Generating synthetic EPS for {len(tickers_without_eps)} tickers...")
        synthetic = generate_synthetic_eps(price_rows, sectors, tickers_without_eps)
        for ticker, dates in synthetic.items():
            if ticker not in eps_lookup:
                eps_lookup[ticker] = dates

    # Write stock_history
    write_stock_history(conn, price_rows, eps_lookup)

    # Update stocks table — needs full price history for 52w hi/lo
    if incremental:
        updated_tickers = sorted({r[1] for r in price_rows})
        cur = conn.cursor()
        cur.execute(
            "SELECT date, ticker, close::float FROM stock_history "
            "WHERE ticker = ANY(%s) ORDER BY date",
            (updated_tickers,)
        )
        all_price_rows = [(str(r[0])[:10], r[1], r[2]) for r in cur.fetchall()]
        cur.close()
        update_stocks_financials(conn, all_price_rows, eps_lookup)
    else:
        update_stocks_financials(conn, price_rows, eps_lookup)


def main() -> None:
    args = parse_args()
    incremental = not args.full

    conn = get_db()
    tickers = load_tickers(conn)
    print(f"Loaded {len(tickers)} tickers from stocks table")
    print(f"Mode: {'incremental' if incremental else 'full backfill'}")

    only = args.only

    # --- Phases 1-4: Prices + EPS -> stock_history + stocks ---
    if not only or only == "prices":
        with phase_timer("Prices + EPS + stock_history + stocks"):
            _run_price_pipeline(conn, tickers, args, incremental)

    # --- Phase 5: Earnings Calendar ---
    if not only or only == "calendar":
        with phase_timer("Earnings Calendar"):
            run_phase_calendar(conn, tickers)

    # --- Phase 6: Financial Statements ---
    if not only or only == "statements":
        with phase_timer("Financial Statements"):
            run_phase_statements(conn, tickers, incremental)

    # --- Phase 7: Stock Beta ---
    if not only or only == "beta":
        with phase_timer("Stock Beta"):
            run_phase_beta(conn, tickers)

    # --- Phase 8: SEC Filings ---
    if not only or only == "filings":
        with phase_timer("SEC Filings"):
            run_phase_filings(conn, tickers, args.workers, incremental)

    # --- Phase 9: Transcripts ---
    if not only or only == "transcripts":
        with phase_timer("Transcripts"):
            run_phase_transcripts(conn, tickers, args.min_year, not incremental)

    # --- Phases 10-11: Company Info + Officers (--include-profiles) ---
    if args.include_profiles or only in ("info", "officers"):
        if not only or only == "info":
            with phase_timer("Company Info"):
                run_phase_info(conn, tickers, args.workers, args.fresh)

        if not only or only == "officers":
            with phase_timer("Officers"):
                run_phase_officers(conn, tickers, args.workers, args.fresh)

    # --- Phase 12: Consensus Estimates ---
    if only == "consensus_estimates":
        with phase_timer("Consensus Estimates"):
            sys.path.insert(0, str(CHECKPOINT_DIR))
            from ingest_consensus_estimates import run as run_consensus
            run_consensus()

    # --- Phase 13: Buyside Estimates ---
    if only == "buyside_estimates":
        with phase_timer("Buyside Estimates"):
            sys.path.insert(0, str(CHECKPOINT_DIR))
            from ingest_buyside_estimates import run as run_buyside
            run_buyside()

    conn.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
