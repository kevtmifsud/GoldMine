#!/usr/bin/env python3
"""Seed fake analyst records into the people table.

Inserts buyside_analyst and sellside_analyst records for development
and testing. Uses next available PER-XXXX IDs after current max.

Idempotent: checks (name, organization) before inserting.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")

DATABASE_URL = os.environ.get("SUPABASE_DATABASE_URL", "")

ANALYSTS = [
    # Buyside analysts
    {"name": "James Wei", "organization": "Tiger Global Management", "title": "Senior Portfolio Manager", "type": "buyside_analyst", "sector_coverage": ["Technology", "Semiconductors"]},
    {"name": "Sarah Park", "organization": "Tiger Global Management", "title": "Portfolio Manager", "type": "buyside_analyst", "sector_coverage": ["Consumer", "Internet"]},
    {"name": "Michael Torres", "organization": "Coatue Management", "title": "Senior Portfolio Manager", "type": "buyside_analyst", "sector_coverage": ["Technology", "Software"]},
    {"name": "Emily Chen", "organization": "Coatue Management", "title": "Portfolio Manager", "type": "buyside_analyst", "sector_coverage": ["Healthcare", "Biotech"]},
    {"name": "David Kim", "organization": "D1 Capital Partners", "title": "Senior Portfolio Manager", "type": "buyside_analyst", "sector_coverage": ["Technology", "Financials"]},
    {"name": "Rachel Goldman", "organization": "D1 Capital Partners", "title": "Portfolio Manager", "type": "buyside_analyst", "sector_coverage": ["Consumer", "Retail"]},
    {"name": "Thomas Brennan", "organization": "Viking Global Investors", "title": "Senior Portfolio Manager", "type": "buyside_analyst", "sector_coverage": ["Technology", "Energy"]},
    {"name": "Lisa Nakamura", "organization": "Viking Global Investors", "title": "Portfolio Manager", "type": "buyside_analyst", "sector_coverage": ["Healthcare", "Industrials"]},
    {"name": "Andrew Scott", "organization": "Lone Pine Capital", "title": "Senior Portfolio Manager", "type": "buyside_analyst", "sector_coverage": ["Technology", "Media"]},
    {"name": "Jennifer Walsh", "organization": "Lone Pine Capital", "title": "Portfolio Manager", "type": "buyside_analyst", "sector_coverage": ["Consumer", "Real Estate"]},
    # Sellside analysts
    {"name": "Alex Rivera", "organization": "Goldman Sachs", "title": "Managing Director, Equity Research", "type": "sellside_analyst", "sector_coverage": ["Technology", "Semiconductors"]},
    {"name": "Megan Foster", "organization": "Goldman Sachs", "title": "Vice President, Equity Research", "type": "sellside_analyst", "sector_coverage": ["Consumer", "Retail"]},
    {"name": "Chris Hammond", "organization": "Morgan Stanley", "title": "Managing Director, Equity Research", "type": "sellside_analyst", "sector_coverage": ["Technology", "Software"]},
    {"name": "Diana Patel", "organization": "Morgan Stanley", "title": "Vice President, Equity Research", "type": "sellside_analyst", "sector_coverage": ["Healthcare", "Biotech"]},
    {"name": "Ryan O'Brien", "organization": "JPMorgan", "title": "Managing Director, Equity Research", "type": "sellside_analyst", "sector_coverage": ["Financials", "Banks"]},
    {"name": "Stephanie Liu", "organization": "JPMorgan", "title": "Vice President, Equity Research", "type": "sellside_analyst", "sector_coverage": ["Energy", "Industrials"]},
    {"name": "Marcus Johnson", "organization": "Bank of America", "title": "Managing Director, Equity Research", "type": "sellside_analyst", "sector_coverage": ["Technology", "Internet"]},
    {"name": "Karen White", "organization": "Bank of America", "title": "Vice President, Equity Research", "type": "sellside_analyst", "sector_coverage": ["Consumer", "Restaurants"]},
    {"name": "Tyler Brooks", "organization": "Jefferies", "title": "Managing Director, Equity Research", "type": "sellside_analyst", "sector_coverage": ["Technology", "Hardware"]},
    {"name": "Amanda Chen", "organization": "Jefferies", "title": "Vice President, Equity Research", "type": "sellside_analyst", "sector_coverage": ["Real Estate", "REITs"]},
]


def main() -> None:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Get current max person_id
    cur.execute(
        "SELECT MAX(CAST(REPLACE(person_id, 'PER-', '') AS INTEGER)) "
        "FROM people WHERE person_id ~ '^PER-[0-9]+$'"
    )
    max_id = cur.fetchone()[0] or 0
    next_id = max_id + 1

    buyside_count = 0
    sellside_count = 0
    first_id = None
    last_id = None

    for analyst in ANALYSTS:
        # Check if (name, organization) already exists
        cur.execute(
            "SELECT person_id FROM people WHERE name = %s AND organization = %s",
            (analyst["name"], analyst["organization"]),
        )
        if cur.fetchone():
            continue

        person_id = f"PER-{next_id:04d}"
        if first_id is None:
            first_id = person_id
        last_id = person_id

        cur.execute(
            """INSERT INTO people (person_id, name, title, organization, type, sector_coverage)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (person_id) DO NOTHING""",
            (
                person_id,
                analyst["name"],
                analyst["title"],
                analyst["organization"],
                analyst["type"],
                analyst["sector_coverage"],
            ),
        )

        if analyst["type"] == "buyside_analyst":
            buyside_count += 1
        else:
            sellside_count += 1
        next_id += 1

    conn.commit()
    cur.close()
    conn.close()

    print(f"Inserted {buyside_count} buyside analysts")
    print(f"Inserted {sellside_count} sellside analysts")
    if first_id and last_id:
        print(f"Sample person_ids: {first_id} through {last_id}")
    else:
        print("No new analysts inserted (all already exist)")


if __name__ == "__main__":
    main()
