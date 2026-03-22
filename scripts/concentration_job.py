#!/usr/bin/env python3
"""Daily portfolio concentration job.

Runs after pnl_calculation_job. Calculates position, sector, industry,
and geography weights per ticker per portfolio. Checks market neutrality
compliance for flagship portfolio. Writes to portfolio_concentration
(insert-only).

Usage:
    python scripts/concentration_job.py
    python scripts/concentration_job.py --date 2026-03-19
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

MARKET_NEUTRAL_TOLERANCE = 0.02  # 2%

logger = structlog.get_logger(__name__)


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def run(target_date: date) -> int:
    """Calculate portfolio concentration for target_date.

    Returns the number of rows inserted into portfolio_concentration.
    """
    logger.info("concentration_job_start", target_date=str(target_date))

    conn = get_conn()
    conn.autocommit = False
    cur = conn.cursor()
    inserted = 0

    try:
        # Build position ledger: net shares per (ticker, portfolio, side)
        cur.execute("""
            SELECT ticker, portfolio, side,
                   SUM(CASE WHEN action = 'buy' THEN shares::numeric
                            ELSE -shares::numeric END) AS net_shares
            FROM portfolio_trades
            WHERE date <= %s
            GROUP BY ticker, portfolio, side
            HAVING SUM(CASE WHEN action = 'buy' THEN shares::numeric
                            ELSE -shares::numeric END) <> 0
        """, (str(target_date),))

        positions = cur.fetchall()
        if not positions:
            logger.info("no_positions_found", target_date=str(target_date))
            conn.commit()
            return 0

        logger.info("positions_found", count=len(positions))

        # Get current prices
        tickers = list({row[0] for row in positions})
        cur.execute("""
            SELECT ticker, close::numeric
            FROM stock_history
            WHERE date = %s AND ticker = ANY(%s)
        """, (str(target_date), tickers))
        prices = dict(cur.fetchall())

        # Get stock metadata (sector, industry, country)
        cur.execute("""
            SELECT ticker, sector, industry, country
            FROM stocks
            WHERE ticker = ANY(%s)
        """, (tickers,))
        stock_info = {}
        for row in cur.fetchall():
            stock_info[row[0]] = {
                "sector": row[1],
                "industry": row[2],
                "geography": row[3],
            }

        # Compute position market values and portfolio totals
        position_values = {}  # (ticker, portfolio, side) -> market_value
        portfolio_totals = {}  # portfolio -> total_value
        portfolio_long_values = {}  # portfolio -> total long value
        portfolio_short_values = {}  # portfolio -> total short value

        for ticker, portfolio, side, net_shares in positions:
            net = float(net_shares)
            price = float(prices.get(ticker, 0))
            if price == 0:
                continue
            mv = abs(net * price)
            key = (ticker, portfolio, side)
            position_values[key] = mv

            portfolio_totals[portfolio] = portfolio_totals.get(portfolio, 0) + mv
            if side == "long":
                portfolio_long_values[portfolio] = portfolio_long_values.get(portfolio, 0) + mv
            else:
                portfolio_short_values[portfolio] = portfolio_short_values.get(portfolio, 0) + mv

        # Compute sector, industry, geo weights per portfolio
        sector_weights = {}   # (portfolio, sector) -> weight
        industry_weights = {} # (portfolio, industry) -> weight
        geo_weights = {}      # (portfolio, geography) -> weight

        for ticker, portfolio, side, net_shares in positions:
            key = (ticker, portfolio, side)
            mv = position_values.get(key, 0)
            total = portfolio_totals.get(portfolio, 1)
            if mv == 0 or total == 0:
                continue

            info = stock_info.get(ticker, {})
            weight = mv / total

            sector = info.get("sector")
            if sector:
                sk = (portfolio, sector)
                sector_weights[sk] = sector_weights.get(sk, 0) + weight

            industry = info.get("industry")
            if industry:
                ik = (portfolio, industry)
                industry_weights[ik] = industry_weights.get(ik, 0) + weight

            geo = info.get("geography")
            if geo:
                gk = (portfolio, geo)
                geo_weights[gk] = geo_weights.get(gk, 0) + weight

        # Compute market neutrality compliance per portfolio
        neutrality = {}
        for portfolio in portfolio_totals:
            total = portfolio_totals[portfolio]
            long_val = portfolio_long_values.get(portfolio, 0)
            short_val = portfolio_short_values.get(portfolio, 0)
            if total > 0:
                imbalance = abs(long_val - short_val) / total
                neutrality[portfolio] = imbalance < MARKET_NEUTRAL_TOLERANCE
            else:
                neutrality[portfolio] = True

        # Build rows
        rows = []
        for ticker, portfolio, side, net_shares in positions:
            key = (ticker, portfolio, side)
            mv = position_values.get(key, 0)
            total = portfolio_totals.get(portfolio, 1)
            if mv == 0:
                continue

            info = stock_info.get(ticker, {})
            sector = info.get("sector")
            industry = info.get("industry")
            geo = info.get("geography")

            position_weight = round(mv / total, 6) if total > 0 else 0
            s_weight = round(sector_weights.get((portfolio, sector), 0), 6) if sector else None
            i_weight = round(industry_weights.get((portfolio, industry), 0), 6) if industry else None
            g_weight = round(geo_weights.get((portfolio, geo), 0), 6) if geo else None

            # Market neutrality only applies to flagship
            is_compliant = neutrality.get(portfolio) if portfolio.lower() == "flagship" else None

            rows.append((
                str(target_date),
                ticker,
                portfolio,
                side,
                sector,
                industry,
                geo,
                position_weight,
                s_weight,
                i_weight,
                g_weight,
                is_compliant,
                round(mv, 2),
                round(total, 2),
            ))

        if rows:
            execute_values(cur, """
                INSERT INTO portfolio_concentration
                    (date, ticker, portfolio, side, sector, industry, geography,
                     position_weight, sector_weight, industry_weight, geo_weight,
                     is_market_neutral_compliant, market_value, portfolio_market_value)
                VALUES %s
                ON CONFLICT (date, ticker, portfolio) DO NOTHING
            """, rows)
            inserted = len(rows)
            logger.info("concentration_rows_inserted", count=inserted)

            # Log neutrality status
            for portfolio, compliant in neutrality.items():
                long_val = portfolio_long_values.get(portfolio, 0)
                short_val = portfolio_short_values.get(portfolio, 0)
                total = portfolio_totals.get(portfolio, 0)
                logger.info("market_neutrality_check",
                            portfolio=portfolio,
                            long_value=round(long_val, 2),
                            short_value=round(short_val, 2),
                            imbalance_pct=round(abs(long_val - short_val) / total * 100, 2) if total > 0 else 0,
                            compliant=compliant)

        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("concentration_job_failed")
        raise
    finally:
        cur.close()
        conn.close()

    logger.info("concentration_job_done", inserted=inserted)
    return inserted


def main():
    parser = argparse.ArgumentParser(description="Daily concentration job")
    parser.add_argument("--date", type=str, default=None,
                        help="Target date (YYYY-MM-DD). Defaults to today.")
    args = parser.parse_args()

    target = date.fromisoformat(args.date) if args.date else date.today()
    inserted = run(target)
    print(f"Concentration job finished: {inserted} rows inserted")


if __name__ == "__main__":
    main()
