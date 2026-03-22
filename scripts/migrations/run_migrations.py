#!/usr/bin/env python3
"""Run SQL migration files from the migrations directory.

Executes all .sql files in sorted order. Each file runs in a single
transaction. Idempotent — uses IF NOT EXISTS / IF EXISTS throughout.

Usage:
    python scripts/migrations/run_migrations.py
    python scripts/migrations/run_migrations.py --only 020_alter_daily_pnl_add_columns.sql
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / "backend" / ".env")

DATABASE_URL = os.environ.get(
    "SUPABASE_DATABASE_URL",
    "postgresql://postgres:sC.g6Wf#9h.Bf_f@db.ybjvfeevaxujenwvoewg.supabase.co:5432/postgres",
)

MIGRATIONS_DIR = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description="Run SQL migrations")
    parser.add_argument("--only", type=str, default=None,
                        help="Run only this specific migration file")
    args = parser.parse_args()

    if args.only:
        files = [MIGRATIONS_DIR / args.only]
        if not files[0].exists():
            print(f"ERROR: Migration file not found: {files[0]}")
            sys.exit(1)
    else:
        files = sorted(MIGRATIONS_DIR.glob("*.sql"))

    if not files:
        print("No migration files found.")
        return

    print(f"Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True

    for sql_file in files:
        print(f"\nRunning: {sql_file.name}")
        sql = sql_file.read_text()
        cur = conn.cursor()
        try:
            cur.execute(sql)
            print(f"  OK")
        except Exception as exc:
            print(f"  FAILED: {exc}")
            sys.exit(1)
        finally:
            cur.close()

    conn.close()
    print(f"\nAll migrations complete ({len(files)} files).")


if __name__ == "__main__":
    main()
