#!/usr/bin/env python3
"""Daily portfolio risk job.

Runs after concentration_job. Joins portfolio_concentration with stock_betas
to calculate weighted beta contributions per position.
Writes to portfolio_risk (insert-only).

Usage:
    python scripts/risk_job.py
    python scripts/risk_job.py --date 2026-03-19
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
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

logger = structlog.get_logger(__name__)


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def run(target_date: date) -> int:
    """Calculate beta risk for all positions as of target_date.

    Returns the number of rows inserted into portfolio_risk.
    """
    logger.info("risk_job_start", target_date=str(target_date))

    conn = get_conn()
    conn.autocommit = False
    cur = conn.cursor()
    inserted = 0

    try:
        # Join portfolio_concentration for target_date with stock_betas
        cur.execute("""
            SELECT pc.ticker, pc.portfolio, pc.side, pc.sector,
                   pc.position_weight, sb.beta
            FROM portfolio_concentration pc
            JOIN stock_betas sb ON sb.ticker = pc.ticker
            WHERE pc.date = %s
        """, (str(target_date),))

        rows_data = cur.fetchall()
        if not rows_data:
            logger.info("no_concentration_data", target_date=str(target_date))
            conn.commit()
            return 0

        logger.info("concentration_rows_joined", count=len(rows_data))

        rows = []
        for ticker, portfolio, side, sector, position_weight, beta in rows_data:
            pw = float(position_weight) if position_weight else 0
            b = float(beta) if beta else 0
            weighted_beta = pw * b

            rows.append((
                str(target_date),
                ticker,
                portfolio,
                b,
                round(weighted_beta, 6),
                sector,
                side,
            ))

        if rows:
            execute_values(cur, """
                INSERT INTO portfolio_risk
                    (date, ticker, portfolio, beta, weighted_beta_contribution,
                     sector, side)
                VALUES %s
                ON CONFLICT (date, ticker, portfolio) DO NOTHING
            """, rows)
            inserted = len(rows)
            logger.info("risk_rows_inserted", count=inserted)

            # Log portfolio-level beta summary
            portfolio_betas = {}
            for _, _, portfolio, _, weighted_beta, _, _ in rows:
                portfolio_betas[portfolio] = portfolio_betas.get(portfolio, 0) + weighted_beta
            for portfolio, total_beta in portfolio_betas.items():
                logger.info("portfolio_beta_summary",
                            portfolio=portfolio,
                            total_weighted_beta=round(total_beta, 4))

        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("risk_job_failed")
        raise
    finally:
        cur.close()
        conn.close()

    logger.info("risk_job_done", inserted=inserted)
    return inserted


def main():
    parser = argparse.ArgumentParser(description="Daily risk calculation job")
    parser.add_argument("--date", type=str, default=None,
                        help="Target date (YYYY-MM-DD). Defaults to today.")
    args = parser.parse_args()

    target = date.fromisoformat(args.date) if args.date else date.today()
    inserted = run(target)
    print(f"Risk job finished: {inserted} rows inserted")


if __name__ == "__main__":
    main()
