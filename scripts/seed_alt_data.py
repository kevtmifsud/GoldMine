#!/usr/bin/env python3
# ================================================
# TEST DATA ONLY — NOT REAL ALT DATA
# Generated for development and testing purposes.
# Run with --clear --confirm-clear to remove.
# DO NOT use in production without real vendor data
# ================================================
"""Seed fake alt data signals for restaurant tickers.

Usage:
    python scripts/seed_alt_data.py --tickers CMG DPZ SBUX
    python scripts/seed_alt_data.py --clear --confirm-clear --tickers CMG
    python scripts/seed_alt_data.py --dry-run --tickers CMG
"""
from __future__ import annotations

import argparse
import math
import os
import random
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")
DATABASE_URL = os.environ.get("SUPABASE_DATABASE_URL", "")

START_DATE = date(2021, 1, 1)
TODAY = date.today()
END_DATE = TODAY - timedelta(days=3)

# ---------------------------------------------------------------------------
# Signal definitions
# ---------------------------------------------------------------------------
SIGNALS = [
    {"data_type": "credit_card_sss_yoy", "freq": "daily", "unit": "%", "vendor": "Second Measure", "lag": 3, "noise": 1.0},
    {"data_type": "credit_card_txn_yoy", "freq": "daily", "unit": "%", "vendor": "Second Measure", "lag": 3, "noise": 1.2},
    {"data_type": "credit_card_spv_yoy", "freq": "daily", "unit": "%", "vendor": "Second Measure", "lag": 3, "noise": 0.8},
    {"data_type": "foot_traffic_yoy", "freq": "weekly", "unit": "%", "vendor": "Placer.ai", "lag": 7, "noise": 1.5},
    {"data_type": "app_downloads_yoy", "freq": "weekly", "unit": "%", "vendor": "Sensor Tower", "lag": 7, "noise": 2.0},
    {"data_type": "web_traffic_yoy", "freq": "weekly", "unit": "%", "vendor": "SimilarWeb", "lag": 7, "noise": 1.3},
    {"data_type": "reservations_yoy", "freq": "weekly", "unit": "%", "vendor": "OpenTable", "lag": 14, "noise": 1.4, "tickers": ["CMG", "SBUX"]},
    {"data_type": "job_postings_yoy", "freq": "monthly", "unit": "%", "vendor": "Revelio Labs", "lag": 14, "noise": 0.6},
]

# ---------------------------------------------------------------------------
# Ticker trend profiles
# ---------------------------------------------------------------------------
TREND_PROFILES: dict[str, dict] = {
    "CMG": {
        "rates": [(2021, 0.08), (2022, 0.08), (2023, 0.08), (2024, 0.05), (2025, 0.05), (2026, 0.05)],
        "seasonal": {1: -0.02, 2: 0.03, 3: 0.03, 4: -0.01},
        "events": [
            (date(2021, 4, 1), date(2021, 6, 30), 0.15),   # COVID recovery
            (date(2021, 7, 1), date(2021, 9, 30), 0.08),   # Digital acceleration
        ],
        "first_year_est": 8.0,
    },
    "SBUX": {
        "rates": [(2021, 0.06), (2022, 0.06), (2023, -0.04), (2024, -0.02), (2025, 0.01), (2026, 0.01)],
        "seasonal": {1: 0.0, 2: -0.01, 3: -0.02, 4: 0.03},
        "events": [
            (date(2023, 1, 1), date(2023, 3, 31), 0.10),   # China reopening
            (date(2023, 4, 1), date(2023, 6, 30), -0.12),  # Labor headwinds
            (date(2024, 7, 1), date(2024, 9, 30), -0.05),  # CEO change
        ],
        "first_year_est": 6.0,
    },
    "DPZ": {
        "rates": [(2021, 0.04), (2022, 0.04), (2023, 0.02), (2024, 0.02), (2025, 0.03), (2026, 0.03)],
        "seasonal": {1: 0.0, 2: -0.01, 3: 0.0, 4: 0.02},
        "events": [
            (date(2022, 4, 1), date(2022, 6, 30), -0.08),  # Delivery competition
            (date(2023, 1, 1), date(2023, 3, 31), 0.06),   # Carryout recovery
        ],
        "first_year_est": 4.0,
    },
}


def _get_annual_rate(ticker: str, d: date) -> float:
    for year, rate in reversed(TREND_PROFILES[ticker]["rates"]):
        if d.year >= year:
            return rate
    return 0.03


def _get_seasonal(ticker: str, d: date) -> float:
    q = (d.month - 1) // 3 + 1
    return TREND_PROFILES[ticker]["seasonal"].get(q, 0.0)


def _get_event_shock(ticker: str, d: date) -> float:
    for start, end, shock in TREND_PROFILES[ticker]["events"]:
        if d == start:
            return shock
    return 0.0


def _generate_dates(freq: str, start: date, end: date) -> list[date]:
    dates = []
    d = start
    while d <= end:
        if freq == "daily":
            if d.weekday() < 5:  # weekdays only
                dates.append(d)
            d += timedelta(days=1)
        elif freq == "weekly":
            if d.weekday() == 0:  # Mondays
                dates.append(d)
            d += timedelta(days=1)
        elif freq == "monthly":
            dates.append(d.replace(day=1))
            if d.month == 12:
                d = d.replace(year=d.year + 1, month=1, day=1)
            else:
                d = d.replace(month=d.month + 1, day=1)
        else:
            d += timedelta(days=1)
    return sorted(set(dates))


def generate_signal(
    ticker: str,
    signal: dict,
    dates: list[date],
) -> list[tuple]:
    """Generate (ticker, data_type, freq, date, value, growth, unit, vendor, data_as_of, as_of)."""
    rng = random.Random(hash(f"{ticker}{signal['data_type']}") % (2**32))
    profile = TREND_PROFILES[ticker]
    noise_mult = signal["noise"]
    lag = signal["lag"]

    # Build values indexed from 100
    value = 100.0
    values: dict[date, float] = {}

    for d in dates:
        annual_rate = _get_annual_rate(ticker, d)
        daily_rate = (1 + annual_rate) ** (1 / 365) - 1
        seasonal = _get_seasonal(ticker, d) / 365
        noise = rng.gauss(0, 0.008 * noise_mult)
        shock = _get_event_shock(ticker, d)

        # Signal-specific adjustments
        dt = signal["data_type"]
        if "txn" in dt:
            # Transactions lead slightly
            daily_rate *= 1.05
        elif "spv" in dt:
            # Spend per visit lags slightly
            daily_rate *= 0.95
        elif "job_postings" in dt:
            # Leading indicator — use rate from 3 months ahead
            future = d + timedelta(days=90)
            daily_rate = ((1 + _get_annual_rate(ticker, future)) ** (1 / 365) - 1)

        value = value * (1 + daily_rate + seasonal + noise) * (1 + shock)
        value = max(value, 10.0)
        values[d] = round(value, 4)

    # Build rows with YoY growth
    rows = []
    for d in dates:
        v = values[d]
        # Find prior year value
        prior_d = None
        try:
            prior_d = d.replace(year=d.year - 1)
        except ValueError:
            pass  # Feb 29 in non-leap year
        prior_v = values.get(prior_d) if prior_d else None

        if prior_v and prior_v > 0:
            growth = round((v / prior_v - 1) * 100, 2)
        else:
            growth = round(rng.gauss(profile.get("first_year_est", 5.0), 2.0), 2)

        data_as_of = d
        as_of = d - timedelta(days=lag)

        rows.append((
            ticker, signal["data_type"], signal["freq"],
            d, v, growth, signal["unit"], signal["vendor"],
            data_as_of, as_of,
        ))

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed fake alt data")
    parser.add_argument("--tickers", nargs="+", default=["CMG", "DPZ", "SBUX"])
    parser.add_argument("--clear", action="store_true")
    parser.add_argument("--confirm-clear", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.clear and not args.confirm_clear:
        print("ERROR: --clear requires --confirm-clear")
        return

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    if args.clear and args.confirm_clear:
        cur.execute("DELETE FROM alt_data WHERE ticker = ANY(%s)", (args.tickers,))
        print(f"Cleared {cur.rowcount} rows from alt_data")
        conn.commit()

    all_rows: list[tuple] = []
    signal_counts: dict[str, int] = defaultdict(int)

    for ticker in args.tickers:
        if ticker not in TREND_PROFILES:
            print(f"WARNING: No trend profile for {ticker}, skipping")
            continue

        ticker_rows = 0
        for signal in SIGNALS:
            # Check ticker restriction
            allowed = signal.get("tickers")
            if allowed and ticker not in allowed:
                continue

            dates = _generate_dates(signal["freq"], START_DATE, END_DATE)
            rows = generate_signal(ticker, signal, dates)
            all_rows.extend(rows)
            signal_counts[signal["data_type"]] += len(rows)
            ticker_rows += len(rows)

        n_signals = sum(1 for s in SIGNALS if not s.get("tickers") or ticker in s.get("tickers", []))
        print(f"{ticker}: {n_signals} signals × {ticker_rows // max(n_signals, 1)} avg dates = {ticker_rows} rows")

    if all_rows and not args.dry_run:
        execute_values(
            cur,
            """INSERT INTO alt_data
               (ticker, data_type, date_frequency, date, value, growth, unit,
                source_vendor, data_as_of_date, as_of_date)
               VALUES %s
               ON CONFLICT DO NOTHING""",
            all_rows,
            page_size=5000,
        )
        conn.commit()

    cur.close()
    conn.close()

    total = sum(signal_counts.values())
    print()
    print("┌──────────────────────────┬────────┐")
    print("│ Signal                   │ Rows   │")
    print("├──────────────────────────┼────────┤")
    for sig, cnt in sorted(signal_counts.items()):
        print(f"│ {sig:<24s} │ {cnt:>6,} │")
    print(f"│ {'TOTAL':<24s} │ {total:>6,} │")
    print("└──────────────────────────┴────────┘")
    if args.dry_run:
        print("\n(DRY RUN — no rows inserted)")


if __name__ == "__main__":
    main()
