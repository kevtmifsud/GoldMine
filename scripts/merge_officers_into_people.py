#!/usr/bin/env python3
"""One-time migration: merge stock_officers.csv into people.csv.

Produces a unified people.csv with columns:
  person_id, name, title, organization, type, tickers,
  age, born, pay, exercised, unexercised

Merge logic:
  - Match officers to existing people by normalized name.
  - For matches: add compensation fields, ensure ticker is in tickers list.
  - For unmatched officers: create new person record with generated person_id,
    type="executive", tickers derived from symbol.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PEOPLE_CSV = ROOT / "data" / "structured" / "people.csv"
OFFICERS_CSV = ROOT / "data" / "structured" / "stock_officers.csv"
OUTPUT_CSV = PEOPLE_CSV  # overwrite in place

MERGED_COLUMNS = [
    "person_id", "name", "title", "organization", "type", "tickers",
    "age", "born", "pay", "exercised", "unexercised",
]

COMPENSATION_FIELDS = ["age", "born", "pay", "exercised", "unexercised"]


def normalize_name(name: str) -> str:
    """Lowercase, collapse whitespace, strip suffixes like Ph.D./C.F.A./Esq."""
    n = name.strip().lower()
    n = re.sub(r"\s+", " ", n)
    return n


def parse_tickers(tickers_str: str) -> list[str]:
    """Split semicolon-delimited tickers, stripping whitespace."""
    return [t.strip() for t in tickers_str.split(";") if t.strip()]


def main() -> None:
    # 1. Read people.csv
    people: list[dict] = []
    with open(PEOPLE_CSV, newline="") as f:
        for row in csv.DictReader(f):
            people.append(row)
    print(f"Read {len(people)} people from {PEOPLE_CSV}")

    # 2. Read stock_officers.csv
    officers: list[dict] = []
    with open(OFFICERS_CSV, newline="") as f:
        for row in csv.DictReader(f):
            officers.append(row)
    print(f"Read {len(officers)} officers from {OFFICERS_CSV}")

    # 3. Build name -> people index (one name can map to one person)
    name_to_person: dict[str, dict] = {}
    for p in people:
        norm = normalize_name(p["name"])
        name_to_person[norm] = p

    # 4. Find max person_id for generating new IDs
    max_id = 0
    for p in people:
        pid = p.get("person_id", "")
        if pid.startswith("PER-"):
            try:
                num = int(pid.split("-")[1])
                if num > max_id:
                    max_id = num
            except ValueError:
                pass
    next_id = max_id + 1

    # 5. Merge officers into people
    matched = 0
    new_records = 0

    for officer in officers:
        norm = normalize_name(officer["name"])
        symbol = officer.get("symbol", "").strip()

        if norm in name_to_person:
            # Match found — add compensation fields and ensure ticker coverage
            person = name_to_person[norm]
            matched += 1

            # Add compensation data (prefer non-empty values)
            for field in COMPENSATION_FIELDS:
                val = officer.get(field, "").strip()
                if val and not person.get(field):
                    person[field] = val

            # Ensure the officer's symbol is in the person's tickers list
            if symbol:
                existing_tickers = parse_tickers(person.get("tickers", ""))
                if symbol not in existing_tickers:
                    existing_tickers.append(symbol)
                    person["tickers"] = ";".join(existing_tickers)
        else:
            # No match — create new person record
            new_pid = f"PER-{next_id:04d}"
            next_id += 1
            new_records += 1

            new_person = {
                "person_id": new_pid,
                "name": officer["name"].strip(),
                "title": officer.get("title", "").strip(),
                "organization": "",
                "type": "executive",
                "tickers": symbol,
            }
            for field in COMPENSATION_FIELDS:
                new_person[field] = officer.get(field, "").strip()

            people.append(new_person)
            name_to_person[norm] = new_person

    # 6. Write merged people.csv
    people.sort(key=lambda p: p.get("name", "").strip().lower())

    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MERGED_COLUMNS)
        writer.writeheader()
        for p in people:
            writer.writerow({col: p.get(col, "") for col in MERGED_COLUMNS})

    print(f"\nMerge summary:")
    print(f"  Matched (officer -> existing person): {matched}")
    print(f"  New records (officer-only):            {new_records}")
    print(f"  Total people records:                  {len(people)}")
    print(f"Wrote {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
