#!/usr/bin/env python3
# ================================================
# TEST DATA ONLY — NOT REAL ESTIMATES
# Generated for development and testing purposes.
# Run with --clear --confirm-clear to remove.
# DO NOT use in production without real vendor data
# ================================================
"""Seed fake estimates into all four log tables for development/testing.

Usage:
    python scripts/seed_test_estimates.py --tickers AAPL
    python scripts/seed_test_estimates.py --tickers AAPL MSFT NVDA
    python scripts/seed_test_estimates.py --clear --confirm-clear --tickers AAPL
    python scripts/seed_test_estimates.py --dry-run --tickers AAPL
"""
from __future__ import annotations

import argparse
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv
import os

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


def get_actual_value(cur, ticker: str, metric: str, period: str) -> float | None:
    """Fetch actual from financial_metrics for a given period."""
    start, end = period_to_dates(period)
    period_type = "annual" if period.endswith("A") else "quarterly"
    cur.execute(
        """SELECT value FROM financial_metrics
           WHERE ticker = %s AND metric_name = %s
           AND period_end BETWEEN %s AND %s
           AND period_type = %s
           ORDER BY period_end DESC LIMIT 1""",
        (ticker, metric, start, end, period_type),
    )
    row = cur.fetchone()
    return float(row[0]) if row else None


def get_latest_actual(cur, ticker: str, metric: str, period_type: str = "quarterly") -> float | None:
    """Fetch most recent actual for forward period base, matching period_type."""
    cur.execute(
        """SELECT value FROM financial_metrics
           WHERE ticker = %s AND metric_name = %s
           AND period_type = %s
           ORDER BY period_end DESC LIMIT 1""",
        (ticker, metric, period_type),
    )
    row = cur.fetchone()
    return float(row[0]) if row else None


def apply_variance(base: float, source: str, ticker: str, metric: str, period: str, firm: str = "") -> float:
    seed = hash(f"{ticker}{metric}{period}{source}{firm}") % (2**32)
    rng = random.Random(seed)
    lo, hi = VARIANCE[source]
    return round(base * rng.uniform(lo, hi), 2)


def estimate_date_for(period: str) -> date:
    """Generate estimate_date based on period type."""
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

    # Get analysts by sector
    cur.execute(
        """SELECT person_id, name, organization, type, sector_coverage
           FROM people
           WHERE type IN ('buyside_analyst', 'sellside_analyst')"""
    )
    all_analysts = cur.fetchall()

    # Get user_profiles for internal estimates
    cur.execute("SELECT user_id, display_name FROM user_profiles WHERE role = 'analyst' ORDER BY display_name")
    user_profiles = cur.fetchall()

    summary = {
        "consensus_estimates": 0,
        "buyside_estimates": 0,
        "internal_estimates": 0,
        "sellside_estimates": 0,
    }

    for ticker in args.tickers:
        print(f"\n--- Processing {ticker} ---")

        # Get ticker sector
        cur.execute("SELECT sector FROM stocks WHERE ticker = %s", (ticker,))
        row = cur.fetchone()
        if not row:
            print(f"  WARNING: {ticker} not found in stocks table, skipping")
            continue
        ticker_sector = row[0]

        # Find analysts covering this sector
        matching_buyside = [
            a for a in all_analysts
            if a[3] == "buyside_analyst" and ticker_sector in (a[4] or [])
        ]
        matching_sellside = [
            a for a in all_analysts
            if a[3] == "sellside_analyst" and ticker_sector in (a[4] or [])
        ]

        # Get available metrics for this ticker
        cur.execute(
            """SELECT DISTINCT metric_name FROM financial_metrics
               WHERE ticker = %s AND metric_name = ANY(%s)""",
            (ticker, TARGET_METRICS),
        )
        available_metrics = [r[0] for r in cur.fetchall()]
        if not available_metrics:
            print(f"  WARNING: No target metrics found for {ticker}, skipping")
            continue

        print(f"  Sector: {ticker_sector}")
        print(f"  Metrics: {available_metrics}")
        print(f"  Buyside analysts: {len(matching_buyside)}")
        print(f"  Sellside analysts: {len(matching_sellside)}")

        # --- CONSENSUS ESTIMATES ---
        consensus_rows = []
        for period in ALL_PERIODS:
            is_past = period in PAST_PERIODS
            for metric in available_metrics:
                if is_past:
                    base = get_actual_value(cur, ticker, metric, period)
                else:
                    base = get_latest_actual(cur, ticker, metric, "annual" if period.endswith("A") else "quarterly")
                if base is None:
                    continue
                val = apply_variance(base, "consensus", ticker, metric, period)
                est_date = estimate_date_for(period)
                consensus_rows.append((
                    ticker, period, metric, val, "USD",
                    est_date, created_at_for(est_date),
                ))
        if consensus_rows and not args.dry_run:
            execute_values(
                cur,
                """INSERT INTO consensus_estimates
                   (ticker, period, metric, value, unit, estimate_date, created_at)
                   VALUES %s
                   ON CONFLICT DO NOTHING""",
                consensus_rows,
            )
        summary["consensus_estimates"] += len(consensus_rows)
        print(f"  consensus_estimates: {len(consensus_rows)} rows")

        # --- BUYSIDE ESTIMATES ---
        buyside_rows = []
        for analyst in matching_buyside:
            person_id, name, org, _, _ = analyst
            for period in ALL_PERIODS:
                is_past = period in PAST_PERIODS
                for metric in available_metrics:
                    if is_past:
                        base = get_actual_value(cur, ticker, metric, period)
                    else:
                        base = get_latest_actual(cur, ticker, metric, "annual" if period.endswith("A") else "quarterly")
                    if base is None:
                        continue
                    # Use analyst name in seed for unique per-analyst values
                    val = apply_variance(base, "buyside", ticker, metric, period, f"{org}:{name}")
                    est_date = estimate_date_for(period)
                    buyside_rows.append((
                        ticker, org, name, person_id, period, metric, val, "USD",
                        est_date, created_at_for(est_date),
                    ))
        if buyside_rows and not args.dry_run:
            execute_values(
                cur,
                """INSERT INTO buyside_estimates
                   (ticker, firm, analyst_name, analyst_person_id, period, metric, value, unit, estimate_date, created_at)
                   VALUES %s
                   ON CONFLICT DO NOTHING""",
                buyside_rows,
            )
        summary["buyside_estimates"] += len(buyside_rows)
        print(f"  buyside_estimates: {len(buyside_rows)} rows")

        # --- INTERNAL ESTIMATES ---
        internal_rows = []
        analysts_for_internal = user_profiles if user_profiles else [(None, None)]
        for period in ALL_PERIODS:
            is_past = period in PAST_PERIODS
            # Determine which analyst
            if len(analysts_for_internal) >= 2:
                # Parse quarter number for alternation
                if "Q" in period:
                    q_num = int(period[-1])
                    analyst_idx = 0 if q_num % 2 == 1 else 1
                else:
                    analyst_idx = 0
                uid, _ = analysts_for_internal[analyst_idx]
            elif analysts_for_internal[0][0] is not None:
                uid = analysts_for_internal[0][0]
            else:
                uid = None

            for metric in available_metrics:
                if is_past:
                    base = get_actual_value(cur, ticker, metric, period)
                else:
                    base = get_latest_actual(cur, ticker, metric, "annual" if period.endswith("A") else "quarterly")
                if base is None:
                    continue
                val = apply_variance(base, "internal", ticker, metric, period)
                est_date = estimate_date_for(period)
                internal_rows.append((
                    ticker, period, metric, val, "USD",
                    est_date, str(uid) if uid else None, "seed_v1",
                    created_at_for(est_date),
                ))
        if internal_rows and not args.dry_run:
            execute_values(
                cur,
                """INSERT INTO internal_estimates
                   (ticker, period, metric, value, unit, estimate_date, user_id, model_version, created_at)
                   VALUES %s
                   ON CONFLICT DO NOTHING""",
                internal_rows,
            )
        summary["internal_estimates"] += len(internal_rows)
        print(f"  internal_estimates: {len(internal_rows)} rows")

        # --- SELLSIDE ESTIMATES ---
        sellside_rows = []
        for analyst in matching_sellside:
            _, name, org, _, _ = analyst
            for period in ALL_PERIODS:
                is_past = period in PAST_PERIODS
                for metric in available_metrics:
                    if is_past:
                        base = get_actual_value(cur, ticker, metric, period)
                    else:
                        base = get_latest_actual(cur, ticker, metric, "annual" if period.endswith("A") else "quarterly")
                    if base is None:
                        continue
                    val = apply_variance(base, "sellside", ticker, metric, period, org)
                    est_date = estimate_date_for(period)
                    sellside_rows.append((
                        ticker, org, [name], period, metric, val, "USD",
                        est_date, created_at_for(est_date),
                    ))
        if sellside_rows and not args.dry_run:
            execute_values(
                cur,
                """INSERT INTO sellside_estimates
                   (ticker, firm, analysts, period, metric, value, unit, estimate_date, created_at)
                   VALUES %s
                   ON CONFLICT DO NOTHING""",
                sellside_rows,
            )
        summary["sellside_estimates"] += len(sellside_rows)
        print(f"  sellside_estimates: {len(sellside_rows)} rows")

    if not args.dry_run:
        conn.commit()

    cur.close()
    conn.close()

    # Final summary
    total = sum(summary.values())
    print()
    print("┌──────────────────────┬───────┐")
    print("│ Table                │ Rows  │")
    print("├──────────────────────┼───────┤")
    for table, count in summary.items():
        print(f"│ {table:<20s} │ {count:>5d} │")
    print(f"│ {'TOTAL':<20s} │ {total:>5d} │")
    print("└──────────────────────┴───────┘")
    if args.dry_run:
        print("\n(DRY RUN — no rows actually inserted)")


if __name__ == "__main__":
    main()
