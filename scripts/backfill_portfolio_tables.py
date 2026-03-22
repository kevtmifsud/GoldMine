#!/usr/bin/env python3
"""Backfill portfolio derivative tables for all historical trading days.

Iterates from the earliest date in portfolio_trades (or --start-date) to
today (or --end-date), calling the four portfolio jobs in sequence for
each trading day.  Skips weekends and dates where daily_pnl rows already
exist (idempotent — safe to re-run).

Usage:
    python scripts/backfill_portfolio_tables.py
    python scripts/backfill_portfolio_tables.py --start-date 2024-01-01
    python scripts/backfill_portfolio_tables.py --start-date 2024-01-01 --end-date 2024-12-31
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
import structlog

from trade_completed_job import run as run_trade_completed
from pnl_calculation_job import run as run_pnl_calculation
from concentration_job import run as run_concentration
from risk_job import run as run_risk

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")

DATABASE_URL = os.environ.get(
    "SUPABASE_DATABASE_URL",
    "postgresql://postgres:sC.g6Wf#9h.Bf_f@db.ybjvfeevaxujenwvoewg.supabase.co:5432/postgres",
)

logger = structlog.get_logger(__name__)

JOBS = [
    ("trade_completed_job", run_trade_completed),
    ("pnl_calculation_job", run_pnl_calculation),
    ("concentration_job", run_concentration),
    ("risk_job", run_risk),
]


def get_earliest_trade_date() -> date | None:
    """Query portfolio_trades for the earliest date."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT MIN(date) FROM portfolio_trades")
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row and row[0]:
        val = row[0]
        if isinstance(val, date):
            return val
        return date.fromisoformat(str(val))
    return None


def get_existing_pnl_dates() -> set[str]:
    """Return the set of dates that already have daily_pnl rows."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT date FROM daily_pnl")
    dates = {str(row[0]) for row in cur.fetchall()}
    cur.close()
    conn.close()
    return dates


def build_trading_days(start: date, end: date) -> list[date]:
    """Return weekdays between start and end (inclusive)."""
    days = []
    current = start
    while current <= end:
        if current.weekday() < 5:  # Mon-Fri
            days.append(current)
        current += timedelta(days=1)
    return days


def format_eta(seconds: float) -> str:
    """Format seconds into a human-readable ETA string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    hours = seconds / 3600
    return f"{hours:.1f}h"


def backfill_concentration_market_values():
    """Backfill market_value, portfolio_market_value, and is_market_neutral_compliant
    for all existing portfolio_concentration rows using daily_pnl data."""
    print("Backfilling portfolio_concentration market values...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        # Step 1: Copy market_value from daily_pnl
        cur.execute("""
            UPDATE portfolio_concentration pc
            SET market_value = dp.market_value
            FROM daily_pnl dp
            WHERE dp.ticker = pc.ticker
              AND dp.portfolio = pc.portfolio
              AND dp.side = pc.side
              AND dp.date = pc.date
              AND pc.market_value IS NULL
        """)
        mv_updated = cur.rowcount
        print(f"  market_value backfilled: {mv_updated} rows")

        # Step 2: Calculate portfolio_market_value per (date, portfolio)
        cur.execute("""
            UPDATE portfolio_concentration pc
            SET portfolio_market_value = sub.total_mv
            FROM (
                SELECT date, portfolio, SUM(market_value) AS total_mv
                FROM portfolio_concentration
                WHERE market_value IS NOT NULL
                GROUP BY date, portfolio
            ) sub
            WHERE sub.date = pc.date
              AND sub.portfolio = pc.portfolio
              AND pc.portfolio_market_value IS NULL
        """)
        pmv_updated = cur.rowcount
        print(f"  portfolio_market_value backfilled: {pmv_updated} rows")

        # Step 3: Recalculate is_market_neutral_compliant from dollar values
        cur.execute("""
            UPDATE portfolio_concentration pc
            SET is_market_neutral_compliant = sub.is_compliant
            FROM (
                SELECT
                    date,
                    portfolio,
                    ABS(
                        SUM(CASE WHEN side = 'long' THEN market_value ELSE 0 END) -
                        SUM(CASE WHEN side = 'short' THEN market_value ELSE 0 END)
                    ) / NULLIF(SUM(market_value), 0) < 0.02 AS is_compliant
                FROM portfolio_concentration
                WHERE market_value IS NOT NULL
                GROUP BY date, portfolio
            ) sub
            WHERE sub.date = pc.date
              AND sub.portfolio = pc.portfolio
              AND pc.portfolio = 'Flagship'
        """)
        compliance_updated = cur.rowcount
        print(f"  is_market_neutral_compliant recalculated (Flagship): {compliance_updated} rows")

        # Step 4: Set Long Only compliance to NULL
        cur.execute("""
            UPDATE portfolio_concentration
            SET is_market_neutral_compliant = NULL
            WHERE portfolio = 'Long Only'
              AND is_market_neutral_compliant IS NOT NULL
        """)
        lo_nulled = cur.rowcount
        print(f"  Long Only compliance set to NULL: {lo_nulled} rows")

        conn.commit()
        print(f"  Backfill complete.")
    except Exception:
        conn.rollback()
        logger.exception("concentration_backfill_failed")
        raise
    finally:
        cur.close()
        conn.close()


def backfill_pnl_columns():
    """Backfill daily_realized_pnl, ytd_pnl, itd_pnl for all historical daily_pnl rows.

    Re-runs pnl_calculation_job for each date in chronological order (oldest first)
    so that ytd_pnl and itd_pnl accumulate correctly from prior rows.
    """
    print("Backfilling daily_pnl P&L columns (daily_realized_pnl, ytd_pnl, itd_pnl)...")
    print("This re-runs pnl_calculation_job for each date chronologically.")
    print()

    # Get all distinct dates from daily_pnl in chronological order
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT date FROM daily_pnl ORDER BY date ASC")
    all_dates = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()

    total = len(all_dates)
    print(f"Total dates to process: {total}")

    if total == 0:
        print("No dates found in daily_pnl.")
        return

    import time as _time
    pipeline_start = _time.monotonic()
    completed = 0
    errors = 0
    current_month = None

    for i, d in enumerate(all_dates, 1):
        # Convert if needed
        if isinstance(d, str):
            d = date.fromisoformat(d)

        # Log progress per month
        month_key = d.strftime("%Y-%m")
        if month_key != current_month:
            if current_month is not None:
                print(f"  {current_month} done")
            current_month = month_key
            print(f"  Processing {month_key}...", end="", flush=True)

        try:
            run_pnl_calculation(d)
            completed += 1
        except Exception as exc:
            errors += 1
            logger.error("pnl_backfill_failed", date=str(d), error=str(exc))

    # Final month
    if current_month:
        print(f"  {current_month} done")

    elapsed = _time.monotonic() - pipeline_start
    print(f"\nBackfill complete: {completed} dates processed, "
          f"{errors} errors, {elapsed:.1f}s total")


def main():
    parser = argparse.ArgumentParser(
        description="Backfill portfolio derivative tables"
    )
    parser.add_argument(
        "--start-date", type=str, default=None,
        help="Start date (YYYY-MM-DD). Defaults to MIN(date) from portfolio_trades.",
    )
    parser.add_argument(
        "--end-date", type=str, default=None,
        help="End date (YYYY-MM-DD). Defaults to today.",
    )
    parser.add_argument(
        "--fix-concentration", action="store_true",
        help="Backfill market_value and portfolio_market_value columns in portfolio_concentration.",
    )
    parser.add_argument(
        "--fix-pnl-columns", action="store_true",
        help="Backfill daily_realized_pnl, ytd_pnl, itd_pnl in daily_pnl.",
    )
    args = parser.parse_args()

    if args.fix_concentration:
        backfill_concentration_market_values()
        return

    if args.fix_pnl_columns:
        backfill_pnl_columns()
        return

    # Determine date range
    if args.start_date:
        start = date.fromisoformat(args.start_date)
    else:
        start = get_earliest_trade_date()
        if start is None:
            print("ERROR: portfolio_trades is empty — nothing to backfill.")
            sys.exit(1)

    end = date.fromisoformat(args.end_date) if args.end_date else date.today()

    # Build list of trading days and filter out already-processed dates
    all_days = build_trading_days(start, end)
    existing = get_existing_pnl_dates()
    days_to_process = [d for d in all_days if d.isoformat() not in existing]

    total_all = len(all_days)
    skipped = total_all - len(days_to_process)
    total = len(days_to_process)

    print(f"Backfill range: {start} to {end}")
    print(f"Total trading days: {total_all}")
    print(f"Already processed (skipping): {skipped}")
    print(f"Days to process: {total}")
    print()

    if total == 0:
        print("Nothing to do — all dates already backfilled.")
        return

    logger.info("backfill_start", start=str(start), end=str(end),
                total_days=total, skipped=skipped)

    pipeline_start = time.monotonic()
    completed = 0
    errors = 0
    elapsed_times: list[float] = []

    for i, target_date in enumerate(days_to_process, 1):
        day_start = time.monotonic()

        # Progress + ETA
        if elapsed_times:
            avg_per_day = sum(elapsed_times) / len(elapsed_times)
            remaining = (total - completed) * avg_per_day
            eta_str = format_eta(remaining)
        else:
            eta_str = "calculating..."

        print(
            f"Processing {target_date} ({i} of {total}) "
            f"[ETA: {eta_str}]",
            end="",
            flush=True,
        )

        day_results = {}
        day_failed = False

        for job_name, job_fn in JOBS:
            try:
                result = job_fn(target_date)
                day_results[job_name] = result
            except Exception as exc:
                logger.error("backfill_job_failed", date=str(target_date),
                             job=job_name, error=str(exc))
                day_failed = True
                errors += 1
                print(f"  FAILED at {job_name}: {exc}")
                break

        day_elapsed = time.monotonic() - day_start
        elapsed_times.append(day_elapsed)

        if not day_failed:
            completed += 1
            pnl_rows = day_results.get("pnl_calculation_job", 0)
            conc_rows = day_results.get("concentration_job", 0)
            risk_rows = day_results.get("risk_job", 0)
            print(
                f"  OK ({day_elapsed:.1f}s) "
                f"pnl={pnl_rows} conc={conc_rows} risk={risk_rows}"
            )
        else:
            print(f"  SKIPPED remaining jobs ({day_elapsed:.1f}s)")

    total_elapsed = time.monotonic() - pipeline_start
    print()
    print(f"Backfill complete: {completed} days processed, "
          f"{errors} errors, {total_elapsed:.1f}s total")

    logger.info("backfill_done", completed=completed, errors=errors,
                total_elapsed_seconds=round(total_elapsed, 2))


if __name__ == "__main__":
    main()
