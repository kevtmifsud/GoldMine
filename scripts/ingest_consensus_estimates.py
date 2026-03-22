#!/usr/bin/env python3
"""Ingest consensus (street) forward estimates into consensus_estimates.

Inserts today's snapshot of consensus forward estimates for all tickers in the
stocks table.  Insert-only — historical snapshots are preserved, never updated.

Usage:
  python scripts/ingest_consensus_estimates.py
  python scripts/ingest_consensus_estimates.py --workers 20
  python scripts/ingest_consensus_estimates.py --dry-run

Also runnable as an optional phase of update_all_data.py:
  python scripts/update_all_data.py --only consensus_estimates
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

# Next 4 quarters + next 2 annual periods are generated dynamically based on
# today's date.  See _build_periods().

BATCH_SIZE = 50  # tickers per batch

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
    """Build the next 4 quarterly + next 2 annual forward period labels.

    Returns labels like ['2026Q2', '2026Q3', '2026Q4', '2027Q1', '2026A', '2027A'].
    """
    year = today.year
    quarter = (today.month - 1) // 3 + 1

    periods: list[str] = []
    # Next 4 quarters
    q, y = quarter, year
    for _ in range(4):
        q += 1
        if q > 4:
            q = 1
            y += 1
        periods.append(f"{y}Q{q}")

    # Next 2 annual periods
    periods.append(f"{year}A")
    periods.append(f"{year + 1}A")

    return periods


# ---------------------------------------------------------------------------
# Data fetch
# ---------------------------------------------------------------------------

def fetch_consensus_estimates_for_tickers(
    tickers: list[str],
    periods: list[str],
) -> list[dict]:
    """Fetch consensus forward estimates for a batch of tickers.

    Returns a list of dicts with keys:
        ticker, period, metric, value, unit, as_of_date

    TODO: Replace this stub with the actual vendor API call once a consensus
    data provider is integrated.  defeatbeta-api does not currently expose
    a forward estimates / analyst consensus parquet table.  The available
    tables are limited to: stock_prices, stock_tailing_eps,
    stock_earning_calendar, stock_statement, stock_sec_filing,
    stock_earning_call_transcripts, stock_profile, stock_officers,
    stock_dividend_events, stock_split_events, exchange_rate,
    daily_treasury_yield, stock_news, stock_revenue_breakdown,
    stock_shares_outstanding.

    When a vendor feed becomes available, the implementation should:
    1. Query the vendor for all tickers in the batch
    2. Filter to METRICS and the requested periods
    3. Return one dict per ticker/period/metric combination
    """
    logger.warning(
        "consensus_estimates_stub",
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
) -> set[tuple[str, str, str]]:
    """Load (ticker, period, metric) keys that already exist for today."""
    cur = conn.cursor()
    cur.execute(
        "SELECT ticker, period, metric FROM consensus_estimates "
        "WHERE as_of_date = %s",
        (as_of,),
    )
    keys = {(row[0], row[1], row[2]) for row in cur.fetchall()}
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
        """INSERT INTO consensus_estimates
               (ticker, period, metric, value, unit, as_of_date)
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

    # Check what we already have for today
    existing = _load_existing_keys(conn, today)
    if existing:
        logger.info("existing_snapshot_rows", count=len(existing))

    total_inserted = 0
    start = time.time()

    # Process in batches of BATCH_SIZE tickers
    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (len(tickers) + BATCH_SIZE - 1) // BATCH_SIZE

        estimates = fetch_consensus_estimates_for_tickers(batch, periods)

        # Filter out already-existing rows (idempotent)
        new_rows: list[tuple] = []
        for est in estimates:
            key = (est["ticker"], est["period"], est["metric"])
            if key not in existing:
                new_rows.append((
                    est["ticker"],
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
        "consensus_estimates_complete",
        total_inserted=total_inserted,
        elapsed_s=round(elapsed, 1),
        dry_run=dry_run,
    )
    conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest consensus forward estimates"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Log what would be inserted without writing",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(dry_run=args.dry_run)
