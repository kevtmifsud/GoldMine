#!/usr/bin/env python3
"""Fetch real EPS estimate/actual from Yahoo Finance and merge into stock_history.csv.

Reads the existing stock_history.csv, fetches earnings dates per ticker via
yfinance using a thread pool for parallel requests, and rewrites the CSV
replacing the eps_estimate and eps_actual columns with real data.

Minimizes wall-clock time:
  - Concurrent fetches via ThreadPoolExecutor (5 workers by default)
  - Exponential backoff with retry on rate limit errors
  - Saves progress to a JSON checkpoint so interrupted runs can resume

Run this once the Yahoo Finance rate limit has cleared:
    python3 scripts/add_eps_to_history.py

To force a full re-fetch (ignoring checkpoint):
    python3 scripts/add_eps_to_history.py --fresh
"""

import csv
import json
import math
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
HISTORY_CSV = ROOT / "data" / "structured" / "stock_history.csv"
CHECKPOINT = ROOT / "scripts" / ".eps_checkpoint.json"

MAX_WORKERS = 5      # Concurrent threads for EPS fetches
MAX_RETRIES = 3      # Retries per ticker on rate limit
RETRY_BACKOFF = 60   # Base seconds on rate limit (doubles each retry)

# Thread-safe checkpoint
_checkpoint_lock = threading.Lock()


def load_existing() -> tuple[list[str], list[list[str]]]:
    with open(HISTORY_CSV, newline="") as f:
        reader = csv.reader(f)
        headers = next(reader)
        rows = list(reader)
    return headers, rows


def get_unique_tickers(rows: list[list[str]], ticker_col: int) -> list[str]:
    return sorted({row[ticker_col] for row in rows})


def fetch_eps_for_ticker(yf_ticker: str) -> dict[str, tuple[float, float]]:
    """Fetch EPS for one ticker. Returns {date_str: (estimate, actual)}."""
    result: dict[str, tuple[float, float]] = {}
    t = yf.Ticker(yf_ticker)
    ed = t.get_earnings_dates(limit=50)
    if ed is None or ed.empty:
        return result
    for dt_idx, row in ed.iterrows():
        date_str = str(dt_idx).split(" ")[0]
        est = row.get("EPS Estimate")
        actual = row.get("Reported EPS")
        if actual is None or (isinstance(actual, float) and math.isnan(actual)):
            continue
        est_val = float(est) if est is not None and not (isinstance(est, float) and math.isnan(est)) else 0.0
        actual_val = float(actual)
        result[date_str] = (round(est_val, 2), round(actual_val, 2))
    return result


def fetch_with_retry(yf_ticker: str) -> dict[str, tuple[float, float]]:
    """Fetch EPS with exponential backoff on rate limit."""
    for attempt in range(MAX_RETRIES):
        try:
            return fetch_eps_for_ticker(yf_ticker)
        except Exception as e:
            err_str = str(e)
            if ("Rate" in err_str or "Too Many" in err_str) and attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF * (2 ** attempt)
                print(f"    {yf_ticker}: rate limited, retrying in {wait}s "
                      f"(attempt {attempt + 1}/{MAX_RETRIES})", flush=True)
                time.sleep(wait)
            else:
                raise
    return fetch_eps_for_ticker(yf_ticker)


def load_checkpoint() -> dict[str, dict[str, list[float]]]:
    if CHECKPOINT.exists():
        with open(CHECKPOINT) as f:
            return json.load(f)
    return {}


def save_checkpoint(data: dict[str, dict[str, list[float]]]) -> None:
    with _checkpoint_lock:
        with open(CHECKPOINT, "w") as f:
            json.dump(data, f)


def process_ticker(
    ticker: str,
    checkpoint: dict[str, dict[str, list[float]]],
) -> tuple[str, int]:
    """Fetch EPS for one ticker and update the checkpoint. Returns (ticker, count)."""
    yf_ticker = ticker.replace(".", "-")
    try:
        eps = fetch_with_retry(yf_ticker)
        with _checkpoint_lock:
            checkpoint[ticker] = {d: list(v) for d, v in eps.items()}
        save_checkpoint(checkpoint)
        return ticker, len(eps)
    except Exception as e:
        return ticker, -1  # signal failure


def main() -> None:
    fresh = "--fresh" in sys.argv

    if not HISTORY_CSV.exists():
        print("ERROR: stock_history.csv not found. Run pull_stock_history.py first.", file=sys.stderr)
        sys.exit(1)

    print("Loading existing stock_history.csv...")
    headers, rows = load_existing()

    try:
        date_col = headers.index("date")
        ticker_col = headers.index("ticker")
        close_col = headers.index("close")
    except ValueError as e:
        print(f"ERROR: Missing expected column: {e}", file=sys.stderr)
        sys.exit(1)

    tickers = get_unique_tickers(rows, ticker_col)
    print(f"Found {len(tickers)} tickers, {len(rows)} rows")

    # Load checkpoint (resume interrupted runs)
    checkpoint: dict[str, dict[str, list[float]]] = {} if fresh else load_checkpoint()
    if checkpoint and not fresh:
        print(f"Resuming from checkpoint ({len(checkpoint)} tickers already fetched)")

    remaining = [t for t in tickers if t not in checkpoint]
    if not remaining:
        print("All tickers already fetched (use --fresh to re-fetch)")
    else:
        print(f"\nFetching EPS data for {len(remaining)} tickers "
              f"({MAX_WORKERS} threads)...")

        failed: list[str] = []
        completed = 0

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
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
                        print(f"  [{completed}/{len(remaining)}] {ticker} -> FAILED",
                              flush=True)
                except Exception as e:
                    completed += 1
                    failed.append(ticker)
                    print(f"  [{completed}/{len(remaining)}] {ticker} -> ERROR: {e}",
                          file=sys.stderr, flush=True)

        if failed:
            print(f"\n{len(failed)} tickers failed: {', '.join(failed)}")
            print("Re-run to retry (checkpoint preserves successful fetches)")

    # Convert checkpoint to lookup format
    all_eps: dict[str, dict[str, tuple[float, float]]] = {}
    for ticker, dates in checkpoint.items():
        all_eps[ticker] = {d: (v[0], v[1]) for d, v in dates.items()}

    total_eps = sum(len(v) for v in all_eps.values())
    print(f"\nTotal EPS data points: {total_eps} across {len(all_eps)} tickers")

    if total_eps == 0:
        print("WARNING: No EPS data fetched. Keeping existing CSV as-is.", file=sys.stderr)
        return

    # Rewrite CSV with real EPS columns
    print("Writing updated stock_history.csv...")
    with open(HISTORY_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "ticker", "close", "eps_estimate", "eps_actual"])
        for row in rows:
            date_str = row[date_col]
            ticker = row[ticker_col]
            close = row[close_col]
            ticker_eps = all_eps.get(ticker, {})
            eps_entry = ticker_eps.get(date_str)
            if eps_entry:
                writer.writerow([date_str, ticker, close, eps_entry[0], eps_entry[1]])
            else:
                writer.writerow([date_str, ticker, close, "", ""])

    # Clean up checkpoint on full success
    all_done = len(all_eps) >= len(tickers)
    if all_done and CHECKPOINT.exists():
        CHECKPOINT.unlink()
        print("Checkpoint removed (all tickers complete)")

    print("Done!")


if __name__ == "__main__":
    main()
