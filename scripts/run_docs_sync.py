#!/usr/bin/env python3
"""Run the documentation sync workflow.

Compares codebase state against markdown documentation, auto-fixes
minor gaps, and reports items needing human review.

Exit codes:
    0 — all gaps auto-fixed (or no gaps)
    1 — items needing human review remain

Usage:
    python scripts/run_docs_sync.py
    python scripts/run_docs_sync.py --triggered-by scheduler
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Ensure backend is importable when run from repo root
_backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(_backend_dir))


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run documentation sync workflow")
    parser.add_argument(
        "--triggered-by", default="manual",
        help="Who triggered this run (default: manual)",
    )
    args = parser.parse_args()

    from app.workflows.qa.docs_sync import DocsSyncWorkflow

    wf = DocsSyncWorkflow()

    print("=" * 60)
    print("Documentation Sync")
    print("=" * 60)

    try:
        result = await wf.run(
            inputs={},
            triggered_by=args.triggered_by,
            user_id=args.triggered_by,
        )
    except Exception as exc:
        print(f"\nERROR: Workflow failed — {exc}")
        return 1

    # Print summary
    print(f"\n{result['summary']}")

    # Print all gaps
    gaps = result.get("gaps_found", [])
    if gaps:
        print(f"\n--- Gaps ({len(gaps)}) ---")
        for i, gap in enumerate(gaps, 1):
            status = "AUTO-FIXED" if gap.get("auto_fixed") else "OPEN"
            print(f"  [{i}] [{status}] {gap['file']}")
            print(f"      {gap['description']}")

    # Print files updated
    files_updated = result.get("files_updated", [])
    if files_updated:
        print(f"\n--- Files updated ({len(files_updated)}) ---")
        for f in files_updated:
            print(f"  {f}")

    # Print human review items
    human_items = result.get("items_needing_human_review", [])
    if human_items:
        print(f"\n--- Items needing human review ({len(human_items)}) ---")
        for i, item in enumerate(human_items, 1):
            print(f"\n  [{i}] {item['file']}")
            print(f"      {item['description']}")
            print(f"      FIX: {item['suggested_fix']}")

    print()
    if human_items:
        print(f"EXIT 1 — {len(human_items)} items need human review.")
        return 1
    else:
        print("EXIT 0 — all gaps resolved.")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
