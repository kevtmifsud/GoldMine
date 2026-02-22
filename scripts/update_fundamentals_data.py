#!/usr/bin/env python3
"""Download stock prices and EPS data, writing data/structured/stock_history.csv.

Runs two phases sequentially:
  Phase 1 — Prices: Per-ticker defeatbeta-api price() calls via ThreadPoolExecutor
  Phase 2 — EPS:    Per-ticker defeatbeta-api ttm_eps() calls with
                     checkpoint/resume. Synthetic EPS estimate derived from
                     price / sector P/E. Tickers that fail automatically fall
                     back to fully synthetic EPS.

Output CSV columns: date, ticker, close, eps_estimate, eps_actual

CLI flags:
  --fresh              Re-fetch all EPS (ignore checkpoint)
  --synthetic-only     Skip real EPS fetches, use synthetic EPS only
  --prices-only        Skip EPS entirely (empty EPS columns)
  --start-date DATE    Price history start date (default: 2015-01-01)
"""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import logging
import math
import random
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from defeatbeta_api.data.ticker import Ticker

ROOT = Path(__file__).resolve().parent.parent
STOCKS_CSV = ROOT / "data" / "structured" / "stocks.csv"
OUTPUT_CSV = ROOT / "data" / "structured" / "stock_history.csv"
CHECKPOINT = ROOT / "scripts" / ".eps_checkpoint.json"

PRICE_WORKERS = 10
EPS_WORKERS = 10

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
    """Read tickers from stocks.csv."""
    tickers: list[str] = []
    with open(STOCKS_CSV, newline="") as f:
        for row in csv.DictReader(f):
            ticker = row["ticker"].strip()
            if ticker:
                tickers.append(ticker)
    return tickers


def load_sectors() -> dict[str, str]:
    """Load ticker -> sector mapping from stocks.csv."""
    sectors: dict[str, str] = {}
    with open(STOCKS_CSV, newline="") as f:
        for row in csv.DictReader(f):
            sectors[row["ticker"].strip()] = row.get("sector", "")
    return sectors


def to_api_ticker(ticker: str) -> str:
    """defeatbeta-api data uses Yahoo Finance format (dashes instead of dots)."""
    return ticker.replace(".", "-")


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
# Phase 3 — Update stocks.csv with computed financial values
# ---------------------------------------------------------------------------

def update_stocks_csv(
    price_rows: list[tuple[str, str, float]],
    eps_lookup: dict[str, dict[str, tuple[float, float]]],
) -> None:
    """Update stocks.csv with financial values computed from stock_history data.

    Computes from price_rows: price (latest close), 52w_high, 52w_low
    Computes from eps_lookup: eps (TTM), pe_ratio (price / TTM EPS)
    Clears dividend_yield (no dividend data available from stock history)
    Preserves static fields: ticker, company_name, sector, industry, market_cap_b, etc.
    """
    # Build per-ticker sorted price lists
    ticker_prices: dict[str, list[tuple[str, float]]] = {}
    for date_str, ticker, close in price_rows:
        ticker_prices.setdefault(ticker, []).append((date_str, close))
    for prices in ticker_prices.values():
        prices.sort(key=lambda x: x[0])

    # Read existing stocks.csv
    rows: list[dict[str, str]] = []
    fieldnames: list[str] = []
    with open(STOCKS_CSV, newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        for row in reader:
            rows.append(dict(row))

    updated = 0
    for row in rows:
        ticker = row["ticker"]
        if ticker not in ticker_prices:
            continue

        prices = ticker_prices[ticker]

        # Latest price
        latest_close = prices[-1][1]
        row["price"] = str(round(latest_close, 2))

        # 52W High/Low (last 252 trading days ≈ 1 year)
        recent = [p for _, p in prices[-252:]]
        row["52w_high"] = str(round(max(recent), 2))
        row["52w_low"] = str(round(min(recent), 2))

        # TTM EPS: sum of last 4 quarterly eps_actual values
        ticker_eps = eps_lookup.get(ticker, {})
        if ticker_eps:
            sorted_dates = sorted(ticker_eps.keys(), reverse=True)
            last_4 = sorted_dates[:4]
            ttm_eps = sum(ticker_eps[d][1] for d in last_4)
            row["eps"] = str(round(ttm_eps, 2))

            # PE Ratio
            if ttm_eps > 0:
                row["pe_ratio"] = str(round(latest_close / ttm_eps, 1))
            elif ttm_eps < 0:
                row["pe_ratio"] = ""  # Negative earnings → no meaningful PE
            else:
                row["pe_ratio"] = ""
        else:
            # No EPS data — clear stale values
            row["eps"] = ""
            row["pe_ratio"] = ""

        # Clear dividend_yield — not available from stock history data
        row["dividend_yield"] = ""

        updated += 1

    # Write back
    with open(STOCKS_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Updated {STOCKS_CSV} — {updated} tickers with computed financials")


# ---------------------------------------------------------------------------
# Write output
# ---------------------------------------------------------------------------

def write_csv(
    price_rows: list[tuple[str, str, float]],
    eps_lookup: dict[str, dict[str, tuple[float, float]]],
) -> None:
    """Write the final stock_history.csv."""
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "ticker", "close", "eps_estimate", "eps_actual"])
        for date_str, ticker, close in price_rows:
            ticker_eps = eps_lookup.get(ticker, {})
            eps_entry = ticker_eps.get(date_str)
            if eps_entry:
                writer.writerow([date_str, ticker, close, eps_entry[0], eps_entry[1]])
            else:
                writer.writerow([date_str, ticker, close, "", ""])

    unique_tickers = {r[1] for r in price_rows}
    dates = {r[0] for r in price_rows}
    print(f"\nWrote {len(price_rows)} rows to {OUTPUT_CSV}")
    print(f"Tickers: {len(unique_tickers)}, Date range: {min(dates)} to {max(dates)}")


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
    parser.add_argument("--start-date", default="2015-01-01",
                        help="Price history start date (default: 2015-01-01)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # --- Phase 1: Prices ---
    print("=" * 60)
    print("Phase 1: Downloading prices")
    print("=" * 60)
    tickers = load_tickers()
    print(f"Found {len(tickers)} tickers in stocks.csv")
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
    print("Phase 3: Writing output")
    print("=" * 60)
    write_csv(price_rows, eps_lookup)

    # --- Update stocks.csv with computed financials ---
    print("\n" + "=" * 60)
    print("Phase 4: Updating stocks.csv with computed financials")
    print("=" * 60)
    update_stocks_csv(price_rows, eps_lookup)
    print("\nDone!")


if __name__ == "__main__":
    main()
