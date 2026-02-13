#!/usr/bin/env python3
"""Pull daily closing prices from Yahoo Finance for all tickers in stocks.csv.

Uses a single yfinance.download() call with threads=True to fetch all 76
tickers in one batch — most efficient approach.

Output: data/structured/stock_history.csv in long format:
    date, ticker, close, eps_estimate, eps_actual

Price columns are populated; EPS columns are left empty (run
add_eps_to_history.py separately to fill them with real data).

Idempotent — overwrites on re-run.
"""

import csv
import sys
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
STOCKS_CSV = ROOT / "data" / "structured" / "stocks.csv"
OUTPUT_CSV = ROOT / "data" / "structured" / "stock_history.csv"

# Yahoo Finance uses dashes instead of dots in tickers (e.g. BRK-B not BRK.B)
TICKER_MAP_FROM_YF: dict[str, str] = {}


def load_tickers() -> list[str]:
    """Read tickers from stocks.csv."""
    tickers: list[str] = []
    with open(STOCKS_CSV, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = row["ticker"].strip()
            if ticker:
                tickers.append(ticker)
    return tickers


def build_ticker_maps(tickers: list[str]) -> list[str]:
    """Build mappings between CSV tickers and Yahoo Finance tickers."""
    yf_tickers: list[str] = []
    for t in tickers:
        yf_t = t.replace(".", "-")
        TICKER_MAP_FROM_YF[yf_t] = t
        yf_tickers.append(yf_t)
    return yf_tickers


def main() -> None:
    print("Reading tickers from stocks.csv...")
    tickers = load_tickers()
    print(f"Found {len(tickers)} tickers")

    yf_tickers = build_ticker_maps(tickers)

    # Single batch download with threaded fetching
    print(f"Downloading price history for {len(yf_tickers)} tickers (threads=True)...")
    df = yf.download(
        tickers=yf_tickers,
        start="2015-01-01",
        auto_adjust=True,
        threads=True,
        progress=True,
    )

    if df.empty:
        print("ERROR: No data returned from Yahoo Finance", file=sys.stderr)
        sys.exit(1)

    # yf.download with multiple tickers returns MultiIndex columns: (Price, Ticker)
    # Extract only Close prices
    close = df["Close"]

    # Convert wide format to long format
    rows: list[tuple[str, str, float]] = []
    for yf_ticker in close.columns:
        csv_ticker = TICKER_MAP_FROM_YF.get(str(yf_ticker), str(yf_ticker))
        series = close[yf_ticker].dropna()
        for date, price in series.items():
            date_str = str(date).split(" ")[0]
            rows.append((date_str, csv_ticker, round(float(price), 2)))

    # Sort by date then ticker
    rows.sort(key=lambda r: (r[0], r[1]))

    # Write output with EPS columns (empty — use add_eps_to_history.py to fill)
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "ticker", "close", "eps_estimate", "eps_actual"])
        for date_str, csv_ticker, close_price in rows:
            writer.writerow([date_str, csv_ticker, close_price, "", ""])

    print(f"\nWrote {len(rows)} rows to {OUTPUT_CSV}")

    unique_tickers = {r[1] for r in rows}
    dates = {r[0] for r in rows}
    print(f"Tickers: {len(unique_tickers)}, Date range: {min(dates)} to {max(dates)}")
    print("\nNext step: run add_eps_to_history.py to populate EPS columns with real data")


if __name__ == "__main__":
    main()
