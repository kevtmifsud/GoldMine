#!/usr/bin/env python3
"""One-time migration: read transcript .txt files from disk and store in Supabase.

Reads all 780 .txt files from data/structured/transcripts/{TICKER}/{YYYY}_Q{N}.txt
and UPDATEs the `transcripts` column in `transcripts_list` for matching rows
(matched by symbol + fiscal_year + fiscal_quarter). For files without a matching
row, INSERTs a new row with a generated transcripts_id.

Usage:
    python scripts/migrate_transcripts_to_supabase.py
    python scripts/migrate_transcripts_to_supabase.py --dry-run
"""
from __future__ import annotations

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

TRANSCRIPTS_DIR = ROOT / "data" / "structured" / "transcripts"


def _parse_dsn(dsn: str) -> str:
    """Re-encode the DSN so psycopg2 handles special-char passwords."""
    import re
    m = re.match(r"postgresql://([^:]+):(.+)@([^:]+):(\d+)/(.+)", dsn)
    if not m:
        return dsn
    user, password, host, port, dbname = m.groups()
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"


def main() -> None:
    dry_run = "--dry-run" in sys.argv

    if not TRANSCRIPTS_DIR.exists():
        print(f"ERROR: Transcripts directory not found: {TRANSCRIPTS_DIR}")
        sys.exit(1)

    # Collect all transcript files
    files: list[tuple[str, int, int, Path]] = []  # (ticker, year, quarter, path)
    for ticker_dir in sorted(TRANSCRIPTS_DIR.iterdir()):
        if not ticker_dir.is_dir():
            continue
        ticker = ticker_dir.name
        for txt_file in sorted(ticker_dir.glob("*.txt")):
            # Parse filename: {YYYY}_Q{N}.txt
            stem = txt_file.stem  # e.g. "2024_Q4"
            parts = stem.split("_Q")
            if len(parts) != 2:
                print(f"  SKIP (bad filename): {txt_file}")
                continue
            try:
                year = int(parts[0])
                quarter = int(parts[1])
            except ValueError:
                print(f"  SKIP (bad filename): {txt_file}")
                continue
            files.append((ticker, year, quarter, txt_file))

    print(f"Found {len(files)} transcript files across "
          f"{len(set(t for t, _, _, _ in files))} tickers")

    if dry_run:
        print("DRY RUN — no changes will be made")

    conn = psycopg2.connect(_parse_dsn(DATABASE_URL))
    conn.autocommit = True
    cur = conn.cursor()

    updated = 0
    inserted = 0
    skipped = 0

    for ticker, year, quarter, path in files:
        content = path.read_text(encoding="utf-8")
        if not content.strip():
            skipped += 1
            print(f"  SKIP (empty): {ticker} {year} Q{quarter}")
            continue

        if dry_run:
            # Check if row exists
            cur.execute(
                "SELECT transcripts_id FROM transcripts_list "
                "WHERE symbol = %s AND fiscal_year = %s AND fiscal_quarter = %s",
                (ticker, str(year), str(quarter)),
            )
            row = cur.fetchone()
            if row:
                updated += 1
            else:
                inserted += 1
            continue

        # Try to UPDATE existing row
        cur.execute(
            "UPDATE transcripts_list SET transcripts = %s "
            "WHERE symbol = %s AND fiscal_year = %s AND fiscal_quarter = %s",
            (content, ticker, str(year), str(quarter)),
        )

        if cur.rowcount > 0:
            updated += 1
        else:
            # No matching row — INSERT a new one
            transcripts_id = f"{ticker}-{year}-Q{quarter}"
            cur.execute(
                "INSERT INTO transcripts_list "
                "(transcripts_id, symbol, fiscal_year, fiscal_quarter, transcripts) "
                "VALUES (%s, %s, %s, %s, %s)",
                (transcripts_id, ticker, str(year), str(quarter), content),
            )
            inserted += 1

    cur.close()
    conn.close()

    print(f"\nMigration complete:")
    print(f"  Updated: {updated}")
    print(f"  Inserted: {inserted}")
    print(f"  Skipped (empty): {skipped}")
    print(f"  Total: {updated + inserted + skipped}")


if __name__ == "__main__":
    main()
