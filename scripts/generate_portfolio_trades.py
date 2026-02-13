#!/usr/bin/env python3
"""Generate simulated portfolio trades using real prices from stock_history.csv.

Picks 18 diversified tickers, simulates initial buys in Jan 2015, then 5-10
random trades per ticker over time.  Uses random.seed(42) for reproducibility.

Output: data/structured/portfolio_trades.csv — columns: date, ticker, action, shares, price
"""

import csv
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HISTORY_CSV = ROOT / "data" / "structured" / "stock_history.csv"
OUTPUT_CSV = ROOT / "data" / "structured" / "portfolio_trades.csv"

PORTFOLIO_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "JPM", "JNJ", "XOM", "PG", "V",
    "UNH", "HD", "BA", "NEE", "DIS", "KO", "BLK", "PLD", "FCX",
]


def load_prices() -> dict[str, list[tuple[str, float]]]:
    """Load price history keyed by ticker → [(date, close), ...]."""
    prices: dict[str, list[tuple[str, float]]] = {}
    with open(HISTORY_CSV, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = row["ticker"]
            if ticker in PORTFOLIO_TICKERS:
                prices.setdefault(ticker, []).append(
                    (row["date"], float(row["close"]))
                )
    # Ensure chronological order
    for ticker in prices:
        prices[ticker].sort(key=lambda x: x[0])
    return prices


def generate_trades(prices: dict[str, list[tuple[str, float]]]) -> list[dict]:
    """Generate simulated trades."""
    random.seed(42)
    trades: list[dict] = []

    for ticker in PORTFOLIO_TICKERS:
        if ticker not in prices:
            print(f"WARNING: No price data for {ticker}, skipping")
            continue

        history = prices[ticker]

        # Initial buy: first available trading day in Jan 2015
        jan_prices = [(d, p) for d, p in history if d.startswith("2015-01")]
        if not jan_prices:
            # Fall back to first available date
            jan_prices = [history[0]]

        init_date, init_price = jan_prices[0]
        init_shares = random.choice([50, 100, 150, 200])
        trades.append({
            "date": init_date,
            "ticker": ticker,
            "action": "buy",
            "shares": init_shares,
            "price": round(init_price, 2),
        })

        # Random subsequent trades: 5-10 per ticker
        num_trades = random.randint(5, 10)
        # Pick random indices from history (excluding first few days)
        if len(history) > 20:
            indices = sorted(random.sample(range(10, len(history)), min(num_trades, len(history) - 10)))
        else:
            indices = sorted(random.sample(range(len(history)), min(num_trades, len(history))))

        holdings = init_shares
        for idx in indices:
            date, price = history[idx]
            # Decide buy or sell (biased toward buy if holdings low)
            if holdings <= 20:
                action = "buy"
            elif random.random() < 0.55:
                action = "buy"
            else:
                action = "sell"

            if action == "buy":
                shares = random.choice([10, 20, 25, 50])
                holdings += shares
            else:
                max_sell = min(holdings, 50)
                if max_sell <= 0:
                    continue
                shares = random.randint(5, max_sell)
                holdings -= shares

            trades.append({
                "date": date,
                "ticker": ticker,
                "action": action,
                "shares": shares,
                "price": round(price, 2),
            })

    # Sort by date then ticker
    trades.sort(key=lambda t: (t["date"], t["ticker"]))
    return trades


def main() -> None:
    print("Loading price history...")
    prices = load_prices()
    print(f"Loaded prices for {len(prices)} tickers")

    print("Generating trades...")
    trades = generate_trades(prices)

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "ticker", "action", "shares", "price"])
        writer.writeheader()
        writer.writerows(trades)

    print(f"Wrote {len(trades)} trades to {OUTPUT_CSV}")

    # Summary
    unique_tickers = {t["ticker"] for t in trades}
    buys = sum(1 for t in trades if t["action"] == "buy")
    sells = sum(1 for t in trades if t["action"] == "sell")
    print(f"Tickers: {len(unique_tickers)}, Buys: {buys}, Sells: {sells}")


if __name__ == "__main__":
    main()
