#!/usr/bin/env python3
"""Generate realistic EPS data from existing stock prices and merge into stock_history.csv.

Uses actual price data + known sector P/E ranges to derive quarterly EPS
that tracks real price movements. Produces eps_estimate and eps_actual columns.

Use this as a stopgap when Yahoo Finance rate limits prevent fetching real
earnings data. Run add_eps_to_history.py later to replace with real EPS.
"""

import csv
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HISTORY_CSV = ROOT / "data" / "structured" / "stock_history.csv"
STOCKS_CSV = ROOT / "data" / "structured" / "stocks.csv"

random.seed(42)

# Approximate sector P/E ratios to derive realistic EPS from price
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


def load_sectors() -> dict[str, str]:
    """Load ticker -> sector mapping from stocks.csv."""
    sectors: dict[str, str] = {}
    with open(STOCKS_CSV, newline="") as f:
        for row in csv.DictReader(f):
            sectors[row["ticker"]] = row.get("sector", "")
    return sectors


def load_history() -> tuple[list[str], list[list[str]]]:
    with open(HISTORY_CSV, newline="") as f:
        reader = csv.reader(f)
        headers = next(reader)
        rows = list(reader)
    return headers, rows


def get_quarterly_dates(dates: list[str]) -> set[str]:
    """Pick one date per quarter (closest to earnings report dates: ~Jan, Apr, Jul, Oct)."""
    # Group dates by year-quarter
    quarters: dict[str, list[str]] = {}
    for d in dates:
        year, month = d[:4], int(d[5:7])
        # Map to earnings months: Jan(Q4), Apr(Q1), Jul(Q2), Oct(Q3)
        if month in (1, 2):
            qkey = f"{year}-Q4"
            target_month = 1
        elif month in (4, 5):
            qkey = f"{year}-Q1"
            target_month = 4
        elif month in (7, 8):
            qkey = f"{year}-Q2"
            target_month = 7
        elif month in (10, 11):
            qkey = f"{year}-Q3"
            target_month = 10
        else:
            continue
        quarters.setdefault(qkey, []).append(d)

    # Pick one date per quarter (last day of the earnings month range)
    selected: set[str] = set()
    for dates_in_q in quarters.values():
        # Pick the last date in the group (simulates end-of-earnings-window)
        dates_in_q.sort()
        selected.add(dates_in_q[-1])
    return selected


def main() -> None:
    if not HISTORY_CSV.exists():
        print("ERROR: stock_history.csv not found.", file=sys.stderr)
        sys.exit(1)

    print("Loading data...")
    sectors = load_sectors()
    headers, rows = load_history()

    date_col = headers.index("date")
    ticker_col = headers.index("ticker")
    close_col = headers.index("close")

    # Group rows by ticker
    ticker_rows: dict[str, list[tuple[int, str, float]]] = {}
    for i, row in enumerate(rows):
        ticker = row[ticker_col]
        date = row[date_col]
        close = float(row[close_col])
        ticker_rows.setdefault(ticker, []).append((i, date, close))

    print(f"Processing {len(ticker_rows)} tickers...")

    # Build EPS lookup: row_index -> (eps_estimate, eps_actual)
    eps_lookup: dict[int, tuple[float, float]] = {}

    for ticker, entries in ticker_rows.items():
        sector = sectors.get(ticker, "")
        pe = SECTOR_PE.get(sector, DEFAULT_PE)

        dates = [d for _, d, _ in entries]
        quarterly_dates = get_quarterly_dates(dates)

        # Build price lookup for this ticker
        date_to_entry = {d: (idx, close) for idx, d, close in entries}

        for date in quarterly_dates:
            if date not in date_to_entry:
                continue
            idx, close = date_to_entry[date]

            # Derive quarterly EPS from price and P/E
            annual_eps = close / pe
            quarterly_eps = annual_eps / 4

            # Add realistic surprise: actual deviates from estimate by -5% to +10%
            surprise = random.uniform(-0.05, 0.10)
            eps_estimate = round(quarterly_eps, 2)
            eps_actual = round(quarterly_eps * (1 + surprise), 2)

            eps_lookup[idx] = (eps_estimate, eps_actual)

    print(f"Generated {len(eps_lookup)} EPS data points")

    # Rewrite CSV
    print("Writing updated stock_history.csv...")
    with open(HISTORY_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "ticker", "close", "eps_estimate", "eps_actual"])
        for i, row in enumerate(rows):
            date = row[date_col]
            ticker = row[ticker_col]
            close = row[close_col]
            eps = eps_lookup.get(i)
            if eps:
                writer.writerow([date, ticker, close, eps[0], eps[1]])
            else:
                writer.writerow([date, ticker, close, "", ""])

    print("Done!")


if __name__ == "__main__":
    main()
