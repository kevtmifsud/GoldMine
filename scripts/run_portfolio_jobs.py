#!/usr/bin/env python3
"""Master runner for the daily portfolio job pipeline.

Executes all four portfolio jobs in sequence:
  1. trade_completed_job  — executed trade_requests → portfolio_trades
  2. pnl_calculation_job  — portfolio_trades → daily_pnl
  3. concentration_job    — portfolio_trades → portfolio_concentration
  4. risk_job             — portfolio_concentration + stock_betas → portfolio_risk

Stops and alerts if any job fails. Logs total runtime.

Usage:
    python scripts/run_portfolio_jobs.py
    python scripts/run_portfolio_jobs.py --date 2026-03-19
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date

import structlog

from trade_completed_job import run as run_trade_completed
from pnl_calculation_job import run as run_pnl_calculation
from concentration_job import run as run_concentration
from risk_job import run as run_risk

logger = structlog.get_logger(__name__)

JOBS = [
    ("trade_completed_job", run_trade_completed),
    ("pnl_calculation_job", run_pnl_calculation),
    ("concentration_job", run_concentration),
    ("risk_job", run_risk),
]


def main():
    parser = argparse.ArgumentParser(description="Run all portfolio jobs in sequence")
    parser.add_argument("--date", type=str, default=None,
                        help="Target date (YYYY-MM-DD). Defaults to today.")
    args = parser.parse_args()

    target = date.fromisoformat(args.date) if args.date else date.today()

    logger.info("portfolio_pipeline_start", target_date=str(target))
    pipeline_start = time.monotonic()
    results = {}

    for job_name, job_fn in JOBS:
        logger.info("job_starting", job=job_name)
        job_start = time.monotonic()

        try:
            result = job_fn(target)
            elapsed = round(time.monotonic() - job_start, 2)
            results[job_name] = result
            logger.info("job_completed", job=job_name, result=result,
                        elapsed_seconds=elapsed)
        except Exception as exc:
            elapsed = round(time.monotonic() - job_start, 2)
            logger.error("job_failed", job=job_name, error=str(exc),
                         elapsed_seconds=elapsed)
            print(f"\nPIPELINE FAILED at {job_name}: {exc}", file=sys.stderr)
            sys.exit(1)

    total_elapsed = round(time.monotonic() - pipeline_start, 2)
    logger.info("portfolio_pipeline_done", total_elapsed_seconds=total_elapsed,
                results=results)

    print(f"\nPortfolio pipeline completed in {total_elapsed}s")
    for job_name, result in results.items():
        print(f"  {job_name}: {result}")


if __name__ == "__main__":
    main()
