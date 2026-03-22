#!/usr/bin/env python3
"""Combined runner for model jobs.

Runs generate_model_peers first (fast, idempotent), then model_processing_job
for all tickers with models in S3.

Usage:
    python scripts/run_model_jobs.py
    python scripts/run_model_jobs.py --tickers AAPL MSFT
    python scripts/run_model_jobs.py --batch-size 20
    python scripts/run_model_jobs.py --skip-peers
"""
from __future__ import annotations

import argparse
import sys

import structlog

from generate_model_peers import run as run_peers
from model_processing_job import run as run_model_processing

log = structlog.get_logger()


def main():
    parser = argparse.ArgumentParser(description="Run all model jobs")
    parser.add_argument("--tickers", nargs="*", help="Specific tickers for model processing")
    parser.add_argument("--batch-size", type=int, default=10, help="Batch size for model processing")
    parser.add_argument("--skip-peers", action="store_true", help="Skip peer generation")
    args = parser.parse_args()

    # Step 1: Generate peers (fast, idempotent)
    if not args.skip_peers:
        log.info("starting_peer_generation")
        peer_summary = run_peers()
        log.info("peer_generation_complete", **peer_summary)
    else:
        log.info("skipping_peer_generation")

    # Step 2: Process models from S3
    log.info("starting_model_processing")
    model_summary = run_model_processing(
        tickers=args.tickers,
        batch_size=args.batch_size,
    )
    log.info("model_processing_complete", **model_summary)

    if model_summary.get("failed", 0) > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
