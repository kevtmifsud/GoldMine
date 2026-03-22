#!/usr/bin/env python3
"""Seed workflow_registry with all defined workflows.

Uses INSERT ... ON CONFLICT DO UPDATE so it is safe to run multiple times.

Usage:
    python scripts/seed_workflow_registry.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")

DATABASE_URL = os.environ.get(
    "SUPABASE_DATABASE_URL",
    "postgresql://postgres:sC.g6Wf#9h.Bf_f@db.ybjvfeevaxujenwvoewg.supabase.co:5432/postgres",
)

WORKFLOWS = [
    {
        "workflow_name": "earnings_preview",
        "display_name": "Earnings Preview",
        "description": (
            "Full pre-earnings briefing covering estimates, actuals, price, "
            "portfolio position, and alt data signals"
        ),
        "required_inputs": json.dumps({
            "ticker": "required",
            "reporting_period": "required",
            "forward_period": "required",
        }),
        "output_table": "workflow_outputs_earnings_preview",
        "trigger_type": "both",
        "schedule_rule": (
            "7 days before earnings_calendar.report_date "
            "for all portfolio tickers"
        ),
    },
    {
        "workflow_name": "financial_model_generation",
        "display_name": "Financial Model Generation",
        "description": (
            "Generates a standardized 3-statement financial model for a ticker "
            "following the canonical template in instructions/domain/models.md. "
            "Pulls historical financials, consensus estimates, peer comps, and "
            "prior model assumptions. Uploads versioned Excel to Supabase S3 "
            "storage bucket financial_model_outputs. Triggers model processing "
            "job to extract structured outputs into model_outputs and "
            "internal_estimates."
        ),
        "required_inputs": json.dumps({
            "ticker": "required",
            "key_kpis": "optional",
            "base_assumptions": "optional",
        }),
        "output_table": "workflow_outputs_financial_model",
        "trigger_type": "on_demand",
        "schedule_rule": None,
    },
    {
        "workflow_name": "docs_sync",
        "display_name": "Documentation Sync",
        "description": (
            "Scans codebase and infrastructure, compares against markdown "
            "documentation, reconciles gaps, and produces a sync report. "
            "Runs automatically after significant build sessions."
        ),
        "required_inputs": json.dumps({}),
        "output_table": "workflow_outputs_docs_sync",
        "trigger_type": "both",
        "schedule_rule": "on_demand or after major build sessions",
    },
]


def main():
    print("Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    for wf in WORKFLOWS:
        cur.execute(
            """INSERT INTO workflow_registry
               (workflow_name, display_name, description,
                required_inputs, output_table, trigger_type, schedule_rule)
               VALUES (%(workflow_name)s, %(display_name)s, %(description)s,
                       %(required_inputs)s::jsonb, %(output_table)s,
                       %(trigger_type)s, %(schedule_rule)s)
               ON CONFLICT (workflow_name) DO UPDATE SET
                   display_name = EXCLUDED.display_name,
                   description = EXCLUDED.description,
                   required_inputs = EXCLUDED.required_inputs,
                   output_table = EXCLUDED.output_table,
                   trigger_type = EXCLUDED.trigger_type,
                   schedule_rule = EXCLUDED.schedule_rule""",
            wf,
        )
        print(f"  Seeded: {wf['workflow_name']}")

    # Verify
    cur.execute("SELECT workflow_name, display_name, trigger_type FROM workflow_registry ORDER BY workflow_name")
    rows = cur.fetchall()
    print(f"\nworkflow_registry ({len(rows)} rows):")
    for name, display, trigger in rows:
        print(f"  {name}: {display} ({trigger})")

    cur.close()
    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
