#!/usr/bin/env python3
"""One-time migration: merge stock_info.csv fields into stocks.csv.

Matches by ticker (stocks.csv) = symbol (stock_info.csv).
Adds 8 new fields: address, city, phone, zip, long_business_summary,
full_time_employees, web_site, report_date.
Skips overlapping fields (sector, industry, country) already in stocks.csv.
"""

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STOCKS_CSV = ROOT / "data" / "structured" / "stocks.csv"
INFO_CSV = ROOT / "data" / "structured" / "stock_info.csv"

NEW_FIELDS = [
    "address", "city", "phone", "zip",
    "long_business_summary", "full_time_employees", "web_site", "report_date",
]


def main() -> None:
    # Read stock_info.csv into a dict keyed by symbol
    info_by_symbol: dict[str, dict] = {}
    with open(INFO_CSV, newline="") as f:
        for row in csv.DictReader(f):
            symbol = row.get("symbol", "").strip()
            if symbol:
                info_by_symbol[symbol] = row

    print(f"Loaded {len(info_by_symbol)} rows from {INFO_CSV}")

    # Read stocks.csv
    stocks: list[dict] = []
    with open(STOCKS_CSV, newline="") as f:
        reader = csv.DictReader(f)
        stock_fields = list(reader.fieldnames or [])
        for row in reader:
            stocks.append(row)

    print(f"Loaded {len(stocks)} rows from {STOCKS_CSV}")

    # Merge
    merged_fields = stock_fields + NEW_FIELDS
    matched = 0
    unmatched: list[str] = []

    for stock in stocks:
        ticker = stock["ticker"].strip()
        info = info_by_symbol.get(ticker)
        if info:
            matched += 1
            for field in NEW_FIELDS:
                stock[field] = info.get(field, "")
        else:
            unmatched.append(ticker)
            for field in NEW_FIELDS:
                stock[field] = ""

    # Write merged stocks.csv
    with open(STOCKS_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=merged_fields)
        writer.writeheader()
        for stock in stocks:
            writer.writerow({col: stock.get(col, "") for col in merged_fields})

    print(f"\nMerged {matched}/{len(stocks)} stocks with info data")
    if unmatched:
        print(f"Unmatched tickers ({len(unmatched)}): {', '.join(unmatched[:20])}")
    print(f"Wrote {len(stocks)} rows with {len(merged_fields)} columns to {STOCKS_CSV}")
    print(f"New columns: {', '.join(NEW_FIELDS)}")


if __name__ == "__main__":
    main()
