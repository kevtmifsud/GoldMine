#!/usr/bin/env python3
# ================================================
# TEST DATA ONLY — NOT REAL ESTIMATES
# Generated for development and testing purposes.
# Run with --clear --confirm-clear to remove.
# DO NOT use in production without real vendor data
# ================================================
"""Seed fake estimates into all four log tables for development/testing.

SQL-first approach: fetches all data upfront in parallel, builds all rows
in memory, then bulk-inserts with 4 total database round trips (one per table).

Usage:
    python scripts/seed_test_estimates.py --tickers AAPL
    python scripts/seed_test_estimates.py --tickers AAPL MSFT NVDA
    python scripts/seed_test_estimates.py --clear --confirm-clear --tickers AAPL
    python scripts/seed_test_estimates.py --dry-run --tickers AAPL
"""
from __future__ import annotations

import argparse
import random
import os
from datetime import date, timedelta
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")
DATABASE_URL = os.environ.get("SUPABASE_DATABASE_URL", "")

TARGET_METRICS = [
    "total_revenue", "diluted_eps", "ebitda",
    "gross_profit", "operating_income", "free_cash_flow",
]

# Historical + forward periods
QUARTERLY_HISTORICAL = [f"{y}Q{q}" for y in range(2023, 2026) for q in range(1, 5)]
ANNUAL_HISTORICAL = ["2023A", "2024A", "2025A"]
QUARTERLY_FORWARD = [f"{y}Q{q}" for y in range(2026, 2028) for q in range(1, 5)]
ANNUAL_FORWARD = ["2026A", "2027A", "2028A"]

ALL_PERIODS = QUARTERLY_HISTORICAL + ANNUAL_HISTORICAL + QUARTERLY_FORWARD + ANNUAL_FORWARD
PAST_PERIODS = set(QUARTERLY_HISTORICAL + ANNUAL_HISTORICAL)

VARIANCE = {
    "consensus": (0.97, 1.03),
    "buyside": (0.95, 1.05),
    "sellside": (0.94, 1.06),
    "internal": (0.93, 1.07),
}

TODAY = date.today()


def period_to_dates(period: str) -> tuple[date, date]:
    if "Q1" in period:
        y = int(period[:4])
        return date(y, 1, 1), date(y, 3, 31)
    elif "Q2" in period:
        y = int(period[:4])
        return date(y, 4, 1), date(y, 6, 30)
    elif "Q3" in period:
        y = int(period[:4])
        return date(y, 7, 1), date(y, 9, 30)
    elif "Q4" in period:
        y = int(period[:4])
        return date(y, 10, 1), date(y, 12, 31)
    elif period.endswith("A"):
        y = int(period[:4])
        return date(y, 1, 1), date(y, 12, 31)
    else:
        raise ValueError(f"Unknown period: {period}")


def apply_variance(base: float, source: str, ticker: str, metric: str, period: str, firm: str = "") -> float:
    seed = hash(f"{ticker}{metric}{period}{source}{firm}") % (2**32)
    rng = random.Random(seed)
    lo, hi = VARIANCE[source]
    return round(base * rng.uniform(lo, hi), 2)


def estimate_date_for(period: str) -> date:
    if period in PAST_PERIODS:
        _, end = period_to_dates(period)
        return end - timedelta(days=14)
    else:
        return TODAY - timedelta(days=random.Random(hash(period) % (2**32)).randint(0, 30))


def created_at_for(est_date: date) -> str:
    offset = random.randint(0, 3)
    d = est_date + timedelta(days=offset)
    return f"{d.isoformat()}T12:00:00+00:00"


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed test estimates")
    parser.add_argument("--tickers", nargs="+", default=["AAPL"])
    parser.add_argument("--clear", action="store_true")
    parser.add_argument("--confirm-clear", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.clear and not args.confirm_clear:
        print("ERROR: --clear requires --confirm-clear for safety")
        return

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Clear if requested
    if args.clear and args.confirm_clear:
        for table in ["consensus_estimates", "buyside_estimates", "internal_estimates", "sellside_estimates"]:
            cur.execute(f"DELETE FROM {table} WHERE ticker = ANY(%s)", (args.tickers,))
            print(f"Cleared {cur.rowcount} rows from {table}")
        conn.commit()

    # ------------------------------------------------------------------
    # STEP 1: Fetch all data upfront (3 queries total)
    # ------------------------------------------------------------------

    # All actuals for target tickers + metrics
    cur.execute(
        """SELECT ticker, metric_name, period_end, period_type, value
           FROM financial_metrics
           WHERE ticker = ANY(%s) AND metric_name = ANY(%s)
           ORDER BY ticker, metric_name, period_end DESC""",
        (args.tickers, TARGET_METRICS),
    )
    actuals_raw = cur.fetchall()

    # Build lookup: (ticker, metric, period_type) -> [(period_end, value), ...]
    actuals_by_key: dict[tuple[str, str, str], list[tuple[date, float]]] = {}
    for ticker, metric, period_end, period_type, value in actuals_raw:
        key = (ticker, metric, period_type)
        actuals_by_key.setdefault(key, []).append((period_end, float(value)))

    # Available metrics per ticker
    available_metrics: dict[str, list[str]] = {}
    for ticker, metric, _, _, _ in actuals_raw:
        available_metrics.setdefault(ticker, set()).add(metric)
    available_metrics = {t: sorted(m) for t, m in available_metrics.items()}

    # Ticker sectors
    cur.execute(
        "SELECT ticker, sector FROM stocks WHERE ticker = ANY(%s)",
        (args.tickers,),
    )
    ticker_sectors = dict(cur.fetchall())

    # All analysts
    cur.execute(
        """SELECT person_id, name, organization, type, sector_coverage
           FROM people
           WHERE type IN ('buyside_analyst', 'sellside_analyst')"""
    )
    all_analysts = cur.fetchall()

    # User profiles for internal estimates
    cur.execute(
        "SELECT user_id, display_name FROM user_profiles WHERE role = 'analyst' ORDER BY display_name"
    )
    user_profiles = cur.fetchall()

    # ------------------------------------------------------------------
    # STEP 2: Build all rows in memory (pure Python math, no DB calls)
    # ------------------------------------------------------------------

    def get_actual_value(ticker: str, metric: str, period: str) -> float | None:
        start, end = period_to_dates(period)
        pt = "annual" if period.endswith("A") else "quarterly"
        entries = actuals_by_key.get((ticker, metric, pt), [])
        for pe, val in entries:
            if start <= pe <= end:
                return val
        return None

    def get_latest_actual(ticker: str, metric: str, period_type: str) -> float | None:
        entries = actuals_by_key.get((ticker, metric, period_type), [])
        return entries[0][1] if entries else None  # already sorted DESC

    consensus_rows: list[tuple] = []
    buyside_rows: list[tuple] = []
    internal_rows: list[tuple] = []
    sellside_rows: list[tuple] = []

    for ticker in args.tickers:
        sector = ticker_sectors.get(ticker)
        if not sector:
            print(f"  WARNING: {ticker} not found in stocks table, skipping")
            continue

        metrics = available_metrics.get(ticker, [])
        if not metrics:
            print(f"  WARNING: No target metrics found for {ticker}, skipping")
            continue

        matching_buyside = [
            a for a in all_analysts
            if a[3] == "buyside_analyst" and sector in (a[4] or [])
        ]
        matching_sellside = [
            a for a in all_analysts
            if a[3] == "sellside_analyst" and sector in (a[4] or [])
        ]

        # Consensus
        for period in ALL_PERIODS:
            is_past = period in PAST_PERIODS
            for metric in metrics:
                base = get_actual_value(ticker, metric, period) if is_past else get_latest_actual(ticker, metric, "annual" if period.endswith("A") else "quarterly")
                if base is None:
                    continue
                val = apply_variance(base, "consensus", ticker, metric, period)
                est_date = estimate_date_for(period)
                consensus_rows.append((
                    ticker, period, metric, val, "USD",
                    est_date, created_at_for(est_date),
                ))

        # Buyside
        for analyst in matching_buyside:
            person_id, name, org, _, _ = analyst
            for period in ALL_PERIODS:
                is_past = period in PAST_PERIODS
                for metric in metrics:
                    base = get_actual_value(ticker, metric, period) if is_past else get_latest_actual(ticker, metric, "annual" if period.endswith("A") else "quarterly")
                    if base is None:
                        continue
                    val = apply_variance(base, "buyside", ticker, metric, period, f"{org}:{name}")
                    est_date = estimate_date_for(period)
                    buyside_rows.append((
                        ticker, org, name, person_id, period, metric, val, "USD",
                        est_date, created_at_for(est_date),
                    ))

        # Internal
        analysts_for_internal = user_profiles if user_profiles else [(None, None)]
        for period in ALL_PERIODS:
            is_past = period in PAST_PERIODS
            if len(analysts_for_internal) >= 2:
                if "Q" in period:
                    q_num = int(period[-1])
                    analyst_idx = 0 if q_num % 2 == 1 else 1
                else:
                    analyst_idx = 0
                uid = analysts_for_internal[analyst_idx][0]
            elif analysts_for_internal[0][0] is not None:
                uid = analysts_for_internal[0][0]
            else:
                uid = None

            for metric in metrics:
                base = get_actual_value(ticker, metric, period) if is_past else get_latest_actual(ticker, metric, "annual" if period.endswith("A") else "quarterly")
                if base is None:
                    continue
                val = apply_variance(base, "internal", ticker, metric, period)
                est_date = estimate_date_for(period)
                internal_rows.append((
                    ticker, period, metric, val, "USD",
                    est_date, str(uid) if uid else None, "seed_v1",
                    created_at_for(est_date),
                ))

        # Sellside
        for analyst in matching_sellside:
            _, name, org, _, _ = analyst
            for period in ALL_PERIODS:
                is_past = period in PAST_PERIODS
                for metric in metrics:
                    base = get_actual_value(ticker, metric, period) if is_past else get_latest_actual(ticker, metric, "annual" if period.endswith("A") else "quarterly")
                    if base is None:
                        continue
                    val = apply_variance(base, "sellside", ticker, metric, period, org)
                    est_date = estimate_date_for(period)
                    sellside_rows.append((
                        ticker, org, [name], period, metric, val, "USD",
                        est_date, created_at_for(est_date),
                    ))

    # ------------------------------------------------------------------
    # STEP 3: Bulk insert (4 DB round trips total)
    # ------------------------------------------------------------------
    if not args.dry_run:
        if consensus_rows:
            execute_values(cur,
                """INSERT INTO consensus_estimates
                   (ticker, period, metric, value, unit, estimate_date, created_at)
                   VALUES %s ON CONFLICT DO NOTHING""",
                consensus_rows)
        if buyside_rows:
            execute_values(cur,
                """INSERT INTO buyside_estimates
                   (ticker, firm, analyst_name, analyst_person_id, period, metric, value, unit, estimate_date, created_at)
                   VALUES %s ON CONFLICT DO NOTHING""",
                buyside_rows)
        if internal_rows:
            execute_values(cur,
                """INSERT INTO internal_estimates
                   (ticker, period, metric, value, unit, estimate_date, user_id, model_version, created_at)
                   VALUES %s ON CONFLICT DO NOTHING""",
                internal_rows)
        if sellside_rows:
            execute_values(cur,
                """INSERT INTO sellside_estimates
                   (ticker, firm, analysts, period, metric, value, unit, estimate_date, created_at)
                   VALUES %s ON CONFLICT DO NOTHING""",
                sellside_rows)
        conn.commit()

    # ------------------------------------------------------------------
    # STEP 4: Summary
    # ------------------------------------------------------------------
    if not args.dry_run:
        cur.execute("""
            SELECT 'consensus' as source, COUNT(*) FROM consensus_estimates WHERE ticker = ANY(%s)
            UNION ALL
            SELECT 'buyside', COUNT(*) FROM buyside_estimates WHERE ticker = ANY(%s)
            UNION ALL
            SELECT 'internal', COUNT(*) FROM internal_estimates WHERE ticker = ANY(%s)
            UNION ALL
            SELECT 'sellside', COUNT(*) FROM sellside_estimates WHERE ticker = ANY(%s)
        """, (args.tickers, args.tickers, args.tickers, args.tickers))
        summary_rows = cur.fetchall()
    else:
        summary_rows = [
            ("consensus", len(consensus_rows)),
            ("buyside", len(buyside_rows)),
            ("internal", len(internal_rows)),
            ("sellside", len(sellside_rows)),
        ]

    cur.close()
    conn.close()

    total = sum(r[1] for r in summary_rows)
    print()
    print("┌──────────────────────┬─────────┐")
    print("│ Table                │ Rows    │")
    print("├──────────────────────┼─────────┤")
    for source, count in summary_rows:
        print(f"│ {source + '_estimates':<20s} │ {count:>7,} │")
    print(f"│ {'TOTAL':<20s} │ {total:>7,} │")
    print("└──────────────────────┴─────────┘")
    if args.dry_run:
        print("\n(DRY RUN — no rows actually inserted)")


if __name__ == "__main__":
    main()
