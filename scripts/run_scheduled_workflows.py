#!/usr/bin/env python3
"""Run scheduled workflows.

Queries earnings_calendar for tickers with report_date = today + 7 days.
For each ticker held in any active portfolio, triggers the earnings_preview
workflow with triggered_by='scheduler'.

Also supports running the docs_sync workflow on demand or as a weekly check.

Usage:
    python scripts/run_scheduled_workflows.py
    python scripts/run_scheduled_workflows.py --lookahead-days 7
    python scripts/run_scheduled_workflows.py --docs-sync
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import structlog
from dotenv import load_dotenv

# Add backend to path for app imports
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

load_dotenv(ROOT / "backend" / ".env")

logger = structlog.get_logger(__name__)


async def run_earnings_previews(lookahead_days: int = 7) -> int:
    """Find portfolio tickers with earnings in lookahead_days and run previews.

    Returns the number of workflows triggered.
    """
    from app.mode2.db import get_conn
    from app.workflows.registry import get_workflow
    from app.mode2.steps import StepCollector

    target_date = date.today() + timedelta(days=lookahead_days)
    logger.info("scheduled_workflows_start", target_earnings_date=str(target_date))

    async with get_conn() as conn:
        # Find tickers reporting on target_date that are in active portfolios
        rows = await conn.fetch(
            """SELECT DISTINCT ec.ticker
               FROM earnings_calendar ec
               JOIN daily_pnl dp ON dp.ticker = ec.ticker
               WHERE ec.report_date = $1
                 AND dp.date = (SELECT MAX(date) FROM daily_pnl)
               ORDER BY ec.ticker""",
            str(target_date),
        )

    tickers = [r["ticker"] for r in rows]
    if not tickers:
        logger.info("no_portfolio_tickers_reporting",
                     target_date=str(target_date))
        return 0

    logger.info("tickers_to_preview", count=len(tickers), tickers=tickers)

    workflow = await get_workflow("earnings_preview")
    if workflow is None:
        logger.error("earnings_preview_workflow_not_found")
        return 0

    # Determine periods from target_date
    year = target_date.year
    quarter = (target_date.month - 1) // 3 + 1
    reporting_period = f"{year}Q{quarter}"
    next_q = quarter + 1 if quarter < 4 else 1
    next_y = year if quarter < 4 else year + 1
    forward_period = f"{next_y}Q{next_q}"

    triggered = 0
    for ticker in tickers:
        steps = StepCollector()
        try:
            result = await workflow.run(
                inputs={
                    "ticker": ticker,
                    "reporting_period": reporting_period,
                    "forward_period": forward_period,
                },
                triggered_by="scheduler",
                user_id="scheduler",
                steps=steps,
            )
            triggered += 1
            logger.info("scheduled_preview_completed", ticker=ticker,
                         run_id=result.get("run_id"),
                         kpis_need_user_input=result.get("kpis_need_user_input"))
        except Exception as exc:
            logger.error("scheduled_preview_failed", ticker=ticker,
                          error=str(exc))

    logger.info("scheduled_workflows_done", triggered=triggered,
                 total_tickers=len(tickers))
    return triggered


async def run_docs_sync() -> dict:
    """Run the documentation sync workflow.

    Returns the workflow result dict.
    """
    from app.workflows.qa.docs_sync import DocsSyncWorkflow

    logger.info("docs_sync_start")
    wf = DocsSyncWorkflow()
    result = await wf.run(
        inputs={},
        triggered_by="scheduler",
        user_id="scheduler",
    )
    logger.info("docs_sync_done", summary=result.get("summary"))
    return result


def run_cost_report():
    """Run the daily cost report and send email."""
    from send_cost_report import fetch_report_data, build_html, build_text, send_report, _fmt_cost
    from datetime import date, timedelta

    report_date = date.today() - timedelta(days=1)
    logger.info("cost_report_start", report_date=str(report_date))
    data = fetch_report_data(report_date)
    html = build_html(data)
    text = build_text(data)
    subject = f"GoldMine Usage Report — {report_date} | {_fmt_cost(data['total_cost'])} yesterday | {_fmt_cost(data['ytd_cost'])} YTD"
    try:
        send_report(html, text, subject)
        logger.info("cost_report_sent", report_date=str(report_date))
    except Exception:
        logger.exception("cost_report_failed")


def main():
    parser = argparse.ArgumentParser(description="Run scheduled workflows")
    parser.add_argument("--lookahead-days", type=int, default=7,
                        help="Days ahead to check earnings_calendar (default: 7)")
    parser.add_argument("--docs-sync", action="store_true",
                        help="Run the documentation sync workflow")
    parser.add_argument("--cost-report", action="store_true",
                        help="Send the daily usage & cost report")
    args = parser.parse_args()

    start = time.monotonic()

    if args.docs_sync:
        result = asyncio.run(run_docs_sync())
        elapsed = round(time.monotonic() - start, 2)
        print(f"Docs sync: {result.get('summary', 'done')} ({elapsed}s)")
    elif args.cost_report:
        run_cost_report()
        elapsed = round(time.monotonic() - start, 2)
        print(f"Cost report sent ({elapsed}s)")
    else:
        triggered = asyncio.run(run_earnings_previews(args.lookahead_days))
        elapsed = round(time.monotonic() - start, 2)
        print(f"Scheduled workflows: {triggered} earnings previews triggered "
              f"in {elapsed}s")


if __name__ == "__main__":
    main()
