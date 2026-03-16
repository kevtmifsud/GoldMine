#!/usr/bin/env python3
"""CLI entry point for Mode 1 pipeline."""
import sys
from pathlib import Path

# Add backend to path so pipeline package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.pipeline.orchestrator import run_pipeline


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run Mode 1 document processing pipeline")
    parser.add_argument("--tickers", nargs="*", help="Only process these tickers")
    parser.add_argument("--limit", type=int, help="Max documents to process")
    args = parser.parse_args()

    result = run_pipeline(
        test_tickers=args.tickers,
        test_limit=args.limit,
    )

    if result.get("failed", 0) > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
