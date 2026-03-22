#!/usr/bin/env python3
"""Ingest external buyside firm forward estimates into buyside_estimates.

Inserts today's snapshot of buyside forward estimates for all tickers in the
stocks table.  Insert-only — historical snapshots are preserved, never updated.

Schema (from data-schema.md):
  ticker, firm, period, metric, value, unit, as_of_date, created_at

Usage:
  python scripts/ingest_buyside_estimates.py
  python scripts/ingest_buyside_estimates.py --dry-run

Also runnable as an optional phase of update_all_data.py:
  python scripts/update_all_data.py --only buyside_estimates
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import date
from pathlib import Path

import psycopg2
import structlog
from psycopg2.extras import execute_values
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")

DATABASE_URL = os.environ.get(
    "SUPABASE_DATABASE_URL",
    "postgresql://postgres:sC.g6Wf#9h.Bf_f@db.ybjvfeevaxujenwvoewg.supabase.co:5432/postgres",
)

METRICS = [
    "revenue",
    "eps_diluted",
    "ebitda",
    "gross_profit",
    "net_income",
    "free_cash_flow",
]

BATCH_SIZE = 50

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Shared infrastructure (mirrors update_all_data.py)
# ---------------------------------------------------------------------------

def get_db() -> psycopg2.extensions.connection:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn


def load_tickers(conn: psycopg2.extensions.connection) -> list[str]:
    cur = conn.cursor()
    cur.execute("SELECT ticker FROM stocks ORDER BY ticker")
    tickers = [row[0] for row in cur.fetchall()]
    cur.close()
    return tickers


def _build_periods(today: date) -> list[str]:
    """Build the next 4 quarterly + next 2 annual forward period labels."""
    year = today.year
    quarter = (today.month - 1) // 3 + 1

    periods: list[str] = []
    q, y = quarter, year
    for _ in range(4):
        q += 1
        if q > 4:
            q = 1
            y += 1
        periods.append(f"{y}Q{q}")

    periods.append(f"{year}A")
    periods.append(f"{year + 1}A")
    return periods


# ---------------------------------------------------------------------------
# Data fetch
# ---------------------------------------------------------------------------

def fetch_buyside_estimates_for_tickers(
    tickers: list[str],
    periods: list[str],
) -> list[dict]:
    """Fetch buyside forward estimates for a batch of tickers.

    Returns a list of dicts with keys:
        ticker, firm, period, metric, value, unit, as_of_date

    TODO: Replace this stub with the actual vendor API call.  Buyside
    estimate feeds are typically delivered via:
      - Daily SFTP drop (CSV/Parquet) from the vendor
      - REST API pull with firm-level forward estimates

    The implementation should:
    1. Connect to the vendor feed / read the daily drop file
    2. Filter to tickers in the batch, METRICS, and requested periods
    3. Return one dict per ticker/firm/period/metric combination
    4. Include 'firm' field identifying the buyside firm source

    Until a vendor is contracted, this returns empty results.
    """
    logger.warning(
        "buyside_estimates_stub",
        msg="No vendor data source configured — returning empty results",
        ticker_count=len(tickers),
    )
    return []


# ---------------------------------------------------------------------------
# Idempotency check
# ---------------------------------------------------------------------------

def _load_existing_keys(
    conn: psycopg2.extensions.connection,
    as_of: date,
) -> set[tuple[str, str, str, str]]:
    """Load (ticker, firm, period, metric) keys that already exist for today."""
    cur = conn.cursor()
    cur.execute(
        "SELECT ticker, firm, period, metric FROM buyside_estimates "
        "WHERE as_of_date = %s",
        (as_of,),
    )
    keys = {(row[0], row[1], row[2], row[3]) for row in cur.fetchall()}
    cur.close()
    return keys


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def _insert_estimates(
    conn: psycopg2.extensions.connection,
    rows: list[tuple],
) -> int:
    """Batch-insert estimate rows.  Returns count inserted."""
    if not rows:
        return 0
    cur = conn.cursor()
    execute_values(
        cur,
        """INSERT INTO buyside_estimates
               (ticker, firm, period, metric, value, unit, as_of_date)
           VALUES %s
           ON CONFLICT DO NOTHING""",
        rows,
        page_size=1000,
    )
    cur.close()
    return len(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(*, dry_run: bool = False) -> None:
    today = date.today()
    periods = _build_periods(today)

    conn = get_db()
    tickers = load_tickers(conn)
    logger.info("loaded_tickers", count=len(tickers))
    logger.info("target_periods", periods=periods)

    existing = _load_existing_keys(conn, today)
    if existing:
        logger.info("existing_snapshot_rows", count=len(existing))

    total_inserted = 0
    start = time.time()

    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (len(tickers) + BATCH_SIZE - 1) // BATCH_SIZE

        estimates = fetch_buyside_estimates_for_tickers(batch, periods)

        new_rows: list[tuple] = []
        for est in estimates:
            key = (est["ticker"], est["firm"], est["period"], est["metric"])
            if key not in existing:
                new_rows.append((
                    est["ticker"],
                    est["firm"],
                    est["period"],
                    est["metric"],
                    est["value"],
                    est.get("unit", ""),
                    today,
                ))
                existing.add(key)

        if dry_run:
            logger.info(
                "dry_run_batch",
                batch=batch_num,
                total=total_batches,
                would_insert=len(new_rows),
            )
        else:
            inserted = _insert_estimates(conn, new_rows)
            total_inserted += inserted
            if batch_num % 5 == 0 or batch_num == total_batches:
                logger.info(
                    "progress",
                    batch=batch_num,
                    total=total_batches,
                    inserted_this_batch=inserted,
                    total_inserted=total_inserted,
                )

    elapsed = time.time() - start
    logger.info(
        "buyside_estimates_complete",
        total_inserted=total_inserted,
        elapsed_s=round(elapsed, 1),
        dry_run=dry_run,
    )
    conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest buyside forward estimates"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Log what would be inserted without writing",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(dry_run=args.dry_run)
