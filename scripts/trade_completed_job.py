#!/usr/bin/env python3
"""EOD job: move executed trade_requests into portfolio_trades.

Queries trade_requests WHERE status='pending' AND created_at::date = target_date - 1.
For each row, inserts into portfolio_trades using closing price from stock_history.
Updates trade_requests status to 'executed'.

Usage:
    python scripts/trade_completed_job.py
    python scripts/trade_completed_job.py --date 2026-03-19
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv
import structlog

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")

DATABASE_URL = os.environ.get(
    "SUPABASE_DATABASE_URL",
    "postgresql://postgres:sC.g6Wf#9h.Bf_f@db.ybjvfeevaxujenwvoewg.supabase.co:5432/postgres",
)

DEFAULT_AUM = 600_000_000  # Fallback AUM if daily_pnl is empty

logger = structlog.get_logger(__name__)


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def get_aum(cur) -> float:
    """Compute AUM from most recent daily_pnl, or fall back to constant."""
    cur.execute("""
        SELECT COALESCE(SUM(sh.close * pt_agg.total_shares), 0)
        FROM (
            SELECT ticker, portfolio, side,
                   SUM(CASE WHEN action = 'buy' THEN shares::numeric
                            ELSE -shares::numeric END) AS total_shares
            FROM portfolio_trades
            GROUP BY ticker, portfolio, side
        ) pt_agg
        JOIN LATERAL (
            SELECT close FROM stock_history
            WHERE ticker = pt_agg.ticker
            ORDER BY date DESC LIMIT 1
        ) sh ON true
    """)
    row = cur.fetchone()
    aum = float(row[0]) if row and row[0] and float(row[0]) > 0 else DEFAULT_AUM
    return aum


def run(target_date: date) -> int:
    """Process pending trade_requests for the day before target_date.

    Returns the number of trades processed.
    """
    request_date = target_date - timedelta(days=1)
    logger.info("trade_completed_job_start", target_date=str(target_date),
                request_date=str(request_date))

    conn = get_conn()
    conn.autocommit = False
    cur = conn.cursor()
    processed = 0

    try:
        # Fetch pending requests from the prior day
        cur.execute("""
            SELECT id, user_id, ticker, portfolio, action, side, target_pct
            FROM trade_requests
            WHERE status = 'pending'
              AND created_at::date = %s
            ORDER BY created_at
        """, (str(request_date),))

        requests = cur.fetchall()
        if not requests:
            logger.info("no_pending_requests", request_date=str(request_date))
            conn.commit()
            return 0

        logger.info("pending_requests_found", count=len(requests))

        # Compute AUM for share calculation
        aum = get_aum(cur)
        logger.info("aum_computed", aum=aum)

        trades_to_insert = []
        request_ids_to_update = []

        for req_id, user_id, ticker, portfolio, action, side, target_pct in requests:
            # Get closing price from stock_history for the request date
            cur.execute("""
                SELECT close FROM stock_history
                WHERE ticker = %s AND date = %s
                LIMIT 1
            """, (ticker, str(request_date)))
            price_row = cur.fetchone()

            if not price_row:
                logger.warning("no_price_found", ticker=ticker,
                               date=str(request_date),
                               msg="Skipping trade request — no closing price")
                continue

            price = float(price_row[0])
            # Derive shares from target_pct * AUM / price
            target_value = float(target_pct) / 100.0 * aum
            shares = int(target_value / price) if price > 0 else 0

            if shares <= 0:
                logger.warning("zero_shares", ticker=ticker,
                               target_pct=float(target_pct), price=price,
                               msg="Skipping — computed zero shares")
                continue

            trades_to_insert.append((
                str(request_date),  # date
                ticker,
                action,
                str(shares),
                str(round(price, 2)),
                portfolio,
                side,
            ))
            request_ids_to_update.append(req_id)

            logger.info("trade_prepared", ticker=ticker, action=action,
                        side=side, shares=shares, price=round(price, 2),
                        portfolio=portfolio)

        # Batch insert into portfolio_trades
        if trades_to_insert:
            execute_values(cur, """
                INSERT INTO portfolio_trades (date, ticker, action, shares, price, portfolio, side)
                VALUES %s
                ON CONFLICT (date, ticker, portfolio, action) DO NOTHING
            """, trades_to_insert)

            # Update trade_requests status
            cur.execute("""
                UPDATE trade_requests
                SET status = 'executed', executed_at = NOW()
                WHERE id = ANY(%s)
            """, (request_ids_to_update,))

            processed = len(trades_to_insert)
            logger.info("trades_inserted", count=processed)

        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("trade_completed_job_failed")
        raise
    finally:
        cur.close()
        conn.close()

    logger.info("trade_completed_job_done", processed=processed)
    return processed


def main():
    parser = argparse.ArgumentParser(description="EOD trade completion job")
    parser.add_argument("--date", type=str, default=None,
                        help="Target date (YYYY-MM-DD). Defaults to today.")
    args = parser.parse_args()

    target = date.fromisoformat(args.date) if args.date else date.today()
    processed = run(target)
    print(f"Trade completed job finished: {processed} trades processed")


if __name__ == "__main__":
    main()
