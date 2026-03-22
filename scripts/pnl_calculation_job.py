#!/usr/bin/env python3
"""Daily P&L calculation job.

Runs after trade_completed_job. Calculates unrealized/realized P&L,
daily/cumulative returns, and contribution to portfolio for each position.
Writes one row per ticker per portfolio per side per sector per date
to daily_pnl (insert-only).

Usage:
    python scripts/pnl_calculation_job.py
    python scripts/pnl_calculation_job.py --date 2026-03-19
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

logger = structlog.get_logger(__name__)


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def run(target_date: date) -> int:
    """Calculate daily P&L for all positions as of target_date.

    Returns the number of rows inserted into daily_pnl.
    """
    logger.info("pnl_calculation_job_start", target_date=str(target_date))

    conn = get_conn()
    conn.autocommit = False
    cur = conn.cursor()
    inserted = 0

    try:
        # Build position ledger: net shares per (ticker, portfolio, side)
        # from all portfolio_trades up to and including target_date
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

        # Collect all tickers we need prices for
        tickers = list({row[0] for row in positions})

        # Get today's closing prices; fall back to most recent prior date
        # so market_value is never null
        cur.execute("""
            SELECT DISTINCT ON (ticker) ticker, close::numeric
            FROM stock_history
            WHERE ticker = ANY(%s) AND date <= %s
            ORDER BY ticker, date DESC
        """, (tickers, str(target_date)))
        today_prices = dict(cur.fetchall())

        # Get yesterday's closing prices
        yesterday = target_date - timedelta(days=1)
        cur.execute("""
            SELECT ticker, close::numeric
            FROM stock_history
            WHERE date = %s AND ticker = ANY(%s)
        """, (str(yesterday), tickers))
        yesterday_prices = dict(cur.fetchall())

        # Get first purchase price per (ticker, portfolio, side)
        cur.execute("""
            SELECT DISTINCT ON (ticker, portfolio, side)
                   ticker, portfolio, side, price::numeric
            FROM portfolio_trades
            WHERE action = 'buy' AND date <= %s AND ticker = ANY(%s)
            ORDER BY ticker, portfolio, side, date ASC
        """, (str(target_date), tickers))
        first_prices = {}
        for row in cur.fetchall():
            first_prices[(row[0], row[1], row[2])] = float(row[3])

        # Get average cost basis per (ticker, portfolio, side)
        # Weighted average of buy prices
        cur.execute("""
            SELECT ticker, portfolio, side,
                   SUM(shares::numeric * price::numeric) / NULLIF(SUM(shares::numeric), 0) AS avg_cost
            FROM portfolio_trades
            WHERE action = 'buy' AND date <= %s AND ticker = ANY(%s)
            GROUP BY ticker, portfolio, side
        """, (str(target_date), tickers))
        avg_costs = {}
        for row in cur.fetchall():
            avg_costs[(row[0], row[1], row[2])] = float(row[3]) if row[3] else 0

        # Get realized P&L: sum of (sell_price - avg_cost_at_sell) * shares_sold
        # Simplified: sum of sell proceeds minus proportional cost basis
        cur.execute("""
            SELECT ticker, portfolio, side,
                   SUM(shares::numeric * price::numeric) AS total_sell_proceeds
            FROM portfolio_trades
            WHERE action = 'sell' AND date <= %s AND ticker = ANY(%s)
            GROUP BY ticker, portfolio, side
        """, (str(target_date), tickers))
        sell_proceeds = {}
        for row in cur.fetchall():
            sell_proceeds[(row[0], row[1], row[2])] = float(row[3]) if row[3] else 0

        cur.execute("""
            SELECT ticker, portfolio, side,
                   SUM(shares::numeric) AS total_shares_sold
            FROM portfolio_trades
            WHERE action = 'sell' AND date <= %s AND ticker = ANY(%s)
            GROUP BY ticker, portfolio, side
        """, (str(target_date), tickers))
        shares_sold = {}
        for row in cur.fetchall():
            shares_sold[(row[0], row[1], row[2])] = float(row[3]) if row[3] else 0

        # --- Daily realized P&L: sells on THIS date only ---
        cur.execute("""
            SELECT ticker, portfolio, side,
                   SUM(shares::numeric * price::numeric) AS day_sell_proceeds,
                   SUM(shares::numeric) AS day_shares_sold
            FROM portfolio_trades
            WHERE action = 'sell' AND date = %s AND ticker = ANY(%s)
            GROUP BY ticker, portfolio, side
        """, (str(target_date), tickers))
        day_sells: dict[tuple, tuple[float, float]] = {}
        for row in cur.fetchall():
            day_sells[(row[0], row[1], row[2])] = (
                float(row[3]) if row[3] else 0,
                float(row[4]) if row[4] else 0,
            )

        # --- Prior year-end unrealized P&L (for YTD calc) ---
        year_start = date(target_date.year, 1, 1)
        cur.execute("""
            SELECT ticker, portfolio, side, unrealized_pnl
            FROM daily_pnl
            WHERE date = (
                SELECT MAX(date) FROM daily_pnl
                WHERE date < %s
            )
            AND ticker = ANY(%s)
        """, (str(year_start), tickers))
        prior_year_unrealized: dict[tuple, float] = {}
        for row in cur.fetchall():
            prior_year_unrealized[(row[0], row[1], row[2])] = float(row[3]) if row[3] else 0

        # --- YTD realized sum (all daily_realized_pnl from Jan 1 to yesterday) ---
        cur.execute("""
            SELECT ticker, portfolio, side,
                   COALESCE(SUM(daily_realized_pnl), 0) AS ytd_realized
            FROM daily_pnl
            WHERE date >= %s AND date < %s AND ticker = ANY(%s)
            GROUP BY ticker, portfolio, side
        """, (str(year_start), str(target_date), tickers))
        ytd_realized_prior: dict[tuple, float] = {}
        for row in cur.fetchall():
            ytd_realized_prior[(row[0], row[1], row[2])] = float(row[3])

        # --- ITD realized sum (all daily_realized_pnl ever, up to yesterday) ---
        cur.execute("""
            SELECT ticker, portfolio, side,
                   COALESCE(SUM(daily_realized_pnl), 0) AS itd_realized
            FROM daily_pnl
            WHERE date < %s AND ticker = ANY(%s)
            GROUP BY ticker, portfolio, side
        """, (str(target_date), tickers))
        itd_realized_prior: dict[tuple, float] = {}
        for row in cur.fetchall():
            itd_realized_prior[(row[0], row[1], row[2])] = float(row[3])

        # Get sector and industry from stocks table
        cur.execute("""
            SELECT ticker, sector, industry
            FROM stocks
            WHERE ticker = ANY(%s)
        """, (tickers,))
        stock_info = {}
        for row in cur.fetchall():
            stock_info[row[0]] = {"sector": row[1], "industry": row[2]}

        # Compute total portfolio value for contribution calculation
        total_portfolio_value = {}
        for ticker, portfolio, side, net_shares in positions:
            net = float(net_shares)
            price = float(today_prices.get(ticker, 0))
            val = abs(net * price)
            key = portfolio
            total_portfolio_value[key] = total_portfolio_value.get(key, 0) + val

        # Build rows
        rows = []
        for ticker, portfolio, side, net_shares in positions:
            net = float(net_shares)
            current_price = float(today_prices.get(ticker, 0))
            if current_price == 0:
                logger.warning("no_current_price", ticker=ticker,
                               date=str(target_date), msg="Skipping position")
                continue

            key = (ticker, portfolio, side)
            info = stock_info.get(ticker, {"sector": None, "industry": None})

            # Unrealized P&L
            avg_cost = avg_costs.get(key, current_price)
            if side == "short":
                unrealized_pnl = (avg_cost - current_price) * abs(net)
            else:
                unrealized_pnl = (current_price - avg_cost) * abs(net)

            # Realized P&L
            proceeds = sell_proceeds.get(key, 0)
            sold = shares_sold.get(key, 0)
            realized_cost = avg_cost * sold if sold > 0 else 0
            if side == "short":
                realized_pnl = realized_cost - proceeds
            else:
                realized_pnl = proceeds - realized_cost

            # Daily return
            yest_price = float(yesterday_prices.get(ticker, 0))
            if yest_price > 0:
                daily_return = (current_price - yest_price) / yest_price
            else:
                daily_return = 0

            # Cumulative return
            first_price = first_prices.get(key, current_price)
            if first_price > 0:
                if side == "short":
                    cumulative_return = (first_price - current_price) / first_price
                else:
                    cumulative_return = (current_price - first_price) / first_price
            else:
                cumulative_return = 0

            # Contribution to portfolio
            position_value = abs(net * current_price)
            total_val = total_portfolio_value.get(portfolio, 1)
            contribution = position_value / total_val if total_val > 0 else 0

            shares_held = abs(net)
            pos_market_value = abs(net * current_price)
            pos_cost_basis = avg_cost * abs(net)

            # --- Daily realized P&L (sells on THIS date only) ---
            day_proceeds, day_sold = day_sells.get(key, (0, 0))
            if day_sold > 0:
                day_cost = avg_cost * day_sold
                if side == "short":
                    daily_realized = day_cost - day_proceeds
                else:
                    daily_realized = day_proceeds - day_cost
            else:
                daily_realized = 0.0

            # --- YTD P&L ---
            prior_yr_unreal = prior_year_unrealized.get(key, 0)
            ytd_real_prior = ytd_realized_prior.get(key, 0)
            ytd_pnl = (unrealized_pnl - prior_yr_unreal) + ytd_real_prior + daily_realized

            # --- ITD P&L ---
            itd_real_prior = itd_realized_prior.get(key, 0)
            itd_pnl = unrealized_pnl + itd_real_prior + daily_realized

            rows.append((
                str(target_date),
                ticker,
                portfolio,
                side,
                info["sector"],
                info["industry"],
                round(unrealized_pnl, 2),
                round(realized_pnl, 2),
                round(daily_return, 6),
                round(cumulative_return, 6),
                round(contribution, 6),
                round(shares_held, 2),
                round(pos_market_value, 2),
                round(pos_cost_basis, 2),
                round(daily_realized, 2),
                round(ytd_pnl, 2),
                round(itd_pnl, 2),
            ))

        if rows:
            execute_values(cur, """
                INSERT INTO daily_pnl
                    (date, ticker, portfolio, side, sector, industry,
                     unrealized_pnl, realized_pnl, daily_return,
                     cumulative_return, contribution_to_portfolio,
                     shares_held, market_value, cost_basis,
                     daily_realized_pnl, ytd_pnl, itd_pnl)
                VALUES %s
                ON CONFLICT (date, ticker, portfolio, side) DO UPDATE SET
                    shares_held = EXCLUDED.shares_held,
                    market_value = EXCLUDED.market_value,
                    cost_basis = EXCLUDED.cost_basis,
                    daily_realized_pnl = EXCLUDED.daily_realized_pnl,
                    ytd_pnl = EXCLUDED.ytd_pnl,
                    itd_pnl = EXCLUDED.itd_pnl
            """, rows)
            inserted = len(rows)
            logger.info("pnl_rows_inserted", count=inserted)

        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("pnl_calculation_job_failed")
        raise
    finally:
        cur.close()
        conn.close()

    logger.info("pnl_calculation_job_done", inserted=inserted)
    return inserted


def main():
    parser = argparse.ArgumentParser(description="Daily P&L calculation job")
    parser.add_argument("--date", type=str, default=None,
                        help="Target date (YYYY-MM-DD). Defaults to today.")
    args = parser.parse_args()

    target = date.fromisoformat(args.date) if args.date else date.today()
    inserted = run(target)
    print(f"P&L calculation job finished: {inserted} rows inserted")


if __name__ == "__main__":
    main()
