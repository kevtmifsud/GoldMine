#!/usr/bin/env python3
"""Daily estimates forward-fill job (hybrid: SQL fetch + Python fill + SQL insert).

Fetches all raw estimate events from the four log tables in one SQL query per
batch, does the forward-fill date expansion in Python (fast, local), then
bulk-inserts results.

Usage:
    python scripts/daily_estimates_job.py --tickers AAPL
    python scripts/daily_estimates_job.py --tickers AAPL MSFT --start-date 2023-01-01
    python scripts/daily_estimates_job.py  # all tickers with estimates
    python scripts/daily_estimates_job.py --batch-size 20
"""
from __future__ import annotations

import argparse
import os
import time
from datetime import date, timedelta
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")
DATABASE_URL = os.environ.get("SUPABASE_DATABASE_URL", "")

# Single query to fetch all raw events for a batch of tickers
FETCH_EVENTS_SQL = """
SELECT
  ticker, metric, period, source, firm, analyst_name,
  analyst_person_id, user_id, value, unit, estimate_date
FROM (
  SELECT ticker, metric, period,
    'consensus' as source, '' as firm, '' as analyst_name,
    NULL::varchar as analyst_person_id, NULL::text as user_id,
    value, unit, estimate_date
  FROM consensus_estimates WHERE ticker = ANY(%s)

  UNION ALL

  SELECT ticker, metric, period,
    'buyside', COALESCE(firm,''), COALESCE(analyst_name,''),
    analyst_person_id::varchar, NULL::text,
    value, unit, estimate_date
  FROM buyside_estimates WHERE ticker = ANY(%s)

  UNION ALL

  SELECT ticker, metric, period,
    'internal', '', '',
    NULL::varchar, user_id::text,
    value, unit, estimate_date
  FROM internal_estimates WHERE ticker = ANY(%s)

  UNION ALL

  SELECT ticker, metric, period,
    'sellside', COALESCE(firm,''), COALESCE(analysts[1],''),
    NULL::varchar, NULL::text,
    value, unit, estimate_date
  FROM sellside_estimates WHERE ticker = ANY(%s)
) combined
ORDER BY ticker, metric, period, source, firm, analyst_name, estimate_date
"""

SUMMARY_SQL = """
SELECT source, COUNT(*) as rows,
  MIN(as_of_date)::text as earliest,
  MAX(as_of_date)::text as latest,
  ROUND(AVG(staleness_days), 1) as avg_staleness
FROM daily_estimates
WHERE ticker = ANY(%s)
GROUP BY source
ORDER BY source;
"""


def period_to_dates(period: str) -> tuple[date, date] | None:
    try:
        if "Q1" in period:
            y = int(period[:4]); return date(y,1,1), date(y,3,31)
        elif "Q2" in period:
            y = int(period[:4]); return date(y,4,1), date(y,6,30)
        elif "Q3" in period:
            y = int(period[:4]); return date(y,7,1), date(y,9,30)
        elif "Q4" in period:
            y = int(period[:4]); return date(y,10,1), date(y,12,31)
        elif period.endswith("A"):
            y = int(period[:4]); return date(y,1,1), date(y,12,31)
    except (ValueError, IndexError):
        pass
    return None


def forward_fill(events: list[tuple], start_date: date, end_date: date) -> list[tuple]:
    """Group events by combo key, forward-fill across calendar dates.

    Returns list of tuples ready for INSERT.
    """
    # Group events by (ticker, metric, period, source, firm, analyst_name)
    combos: dict[tuple, list[dict]] = {}
    for row in events:
        ticker, metric, period, source, firm, analyst_name, \
            analyst_person_id, user_id, value, unit, estimate_date = row
        key = (ticker, metric, period, source, firm, analyst_name)
        if key not in combos:
            combos[key] = []
        combos[key].append({
            "analyst_person_id": analyst_person_id,
            "user_id": user_id,
            "value": value,
            "unit": unit,
            "estimate_date": estimate_date,
        })

    results: list[tuple] = []

    for key, events_list in combos.items():
        ticker, metric, period, source, firm, analyst_name = key

        dates = period_to_dates(period)
        if dates is None:
            continue
        period_start, period_end = dates

        # Sort events by estimate_date ascending
        events_list.sort(key=lambda e: e["estimate_date"])

        first_estimate_date = events_list[0]["estimate_date"]
        fill_start = max(start_date, first_estimate_date)
        fill_end = min(end_date, period_end + timedelta(days=90))

        if fill_start > fill_end:
            continue

        # Forward-fill: walk calendar dates, advance event pointer
        event_idx = 0
        cal_date = fill_start
        while cal_date <= fill_end:
            while (
                event_idx + 1 < len(events_list)
                and events_list[event_idx + 1]["estimate_date"] <= cal_date
            ):
                event_idx += 1

            active = events_list[event_idx]
            if active["estimate_date"] > cal_date:
                cal_date += timedelta(days=1)
                continue

            results.append((
                ticker, metric, period,
                period_start, period_end,
                source, firm, analyst_name,
                active["analyst_person_id"],
                active["user_id"],
                float(active["value"]) if active["value"] is not None else None,
                active["unit"],
                active["estimate_date"],
                cal_date,
            ))
            cal_date += timedelta(days=1)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily estimates forward-fill job")
    parser.add_argument("--tickers", nargs="+", default=None)
    parser.add_argument("--start-date", default="2023-01-01")
    parser.add_argument("--end-date", default=date.today().isoformat())
    parser.add_argument("--batch-size", type=int, default=1,
                        help="Tickers per batch (default 1)")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip tickers that already have rows in daily_estimates")
    parser.add_argument("--pause", type=float, default=2.0,
                        help="Seconds to pause between batches (default 2)")
    args = parser.parse_args()

    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date)

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SET statement_timeout = '0'")

    # Determine tickers
    if args.tickers:
        tickers = args.tickers
    else:
        cur.execute("""
            SELECT DISTINCT ticker FROM (
              SELECT ticker FROM consensus_estimates
              UNION SELECT ticker FROM buyside_estimates
              UNION SELECT ticker FROM internal_estimates
              UNION SELECT ticker FROM sellside_estimates
            ) t ORDER BY ticker
        """)
        tickers = [r[0] for r in cur.fetchall()]

    if not tickers:
        print("No tickers found with estimates.")
        return

    # Skip tickers already in daily_estimates
    if args.skip_existing:
        cur.execute("SELECT DISTINCT ticker FROM daily_estimates")
        existing = {r[0] for r in cur.fetchall()}
        before = len(tickers)
        tickers = [t for t in tickers if t not in existing]
        print(f"Skipping {before - len(tickers)} tickers already in daily_estimates")

    if not tickers:
        print("All tickers already processed.")
        return

    batches = [tickers[i:i + args.batch_size] for i in range(0, len(tickers), args.batch_size)]

    print(f"Processing {len(tickers)} ticker(s) in {len(batches)} batch(es) of {args.batch_size}")
    print(f"Date range: {start_date} to {end_date}", flush=True)

    t0 = time.monotonic()
    total_rows = 0

    for i, batch in enumerate(batches, 1):
        batch_preview = ", ".join(batch[:3]) + ("..." if len(batch) > 3 else "")
        print(f"\nBatch {i}/{len(batches)}: {batch_preview} ({len(batch)} tickers)", end="", flush=True)

        batch_t0 = time.monotonic()

        # 1. Fetch all raw events for this batch (one query)
        cur.execute("SET statement_timeout = '0'")
        cur.execute(FETCH_EVENTS_SQL, (batch, batch, batch, batch))
        events = cur.fetchall()

        # 2. Forward-fill in Python (fast, local)
        filled = forward_fill(events, start_date, end_date)

        # 3. Bulk insert in small chunks to avoid overwhelming remote DB
        INSERT_CHUNK = 10_000
        if filled:
            for chunk_start in range(0, len(filled), INSERT_CHUNK):
                chunk = filled[chunk_start:chunk_start + INSERT_CHUNK]
                cur.execute("SET statement_timeout = '0'")
                execute_values(
                    cur,
                    """INSERT INTO daily_estimates
                       (ticker, metric, period, period_start_date, period_end_date,
                        source, firm, analyst_name, analyst_person_id, user_id,
                        value, unit, estimate_date, as_of_date)
                       VALUES %s
                       ON CONFLICT ON CONSTRAINT daily_estimates_unique_key
                       DO NOTHING""",
                    chunk,
                    page_size=1000,
                )
                conn.commit()
                time.sleep(0.5)  # give the DB a breather

        batch_elapsed = round(time.monotonic() - batch_t0, 1)
        total_rows += len(filled)
        print(f"  {len(filled):,} rows ({batch_elapsed}s)", flush=True)

        # Pause between batches to reduce DB load
        if i < len(batches) and args.pause > 0:
            time.sleep(args.pause)

    elapsed = round(time.monotonic() - t0, 1)
    print(f"\nTotal: {total_rows:,} rows inserted in {elapsed}s")

    # Summary across all tickers
    cur.execute(SUMMARY_SQL, (tickers,))
    rows = cur.fetchall()

    print(f"\n{'Source':<12} {'Rows':>10} {'Earliest':>12} {'Latest':>12} {'Avg Stale':>10}")
    print("-" * 58)
    for source, count, earliest, latest, avg_stale in rows:
        print(f"{source:<12} {count:>10,} {earliest:>12} {latest:>12} {avg_stale:>10}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
