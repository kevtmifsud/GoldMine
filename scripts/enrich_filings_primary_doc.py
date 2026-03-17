#!/usr/bin/env python3
"""Enrich sec_filings Supabase table with primary_document field from EDGAR submissions API.

Reads existing sec_filings from Supabase, fetches primaryDocument for each CIK from
data.sec.gov, and updates the table.

No external dependencies beyond psycopg2 — uses only the Python standard library
for HTTP calls.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib.request import Request, urlopen

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")

DATABASE_URL = os.environ.get(
    "SUPABASE_DATABASE_URL",
    "postgresql://postgres:sC.g6Wf#9h.Bf_f@db.ybjvfeevaxujenwvoewg.supabase.co:5432/postgres",
)

EDGAR_UA = "GoldMine admin@goldmine.dev"


def fetch_edgar_submissions(cik: str) -> dict[str, str]:
    """Fetch primaryDocument for all filings of a CIK from data.sec.gov.

    Returns {accession_number: primary_document_filename}.
    """
    cik_padded = cik.lstrip("0").zfill(10)
    base_url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    req = Request(base_url, headers={"User-Agent": EDGAR_UA})

    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"    ERROR fetching {base_url}: {e}")
        return {}

    result: dict[str, str] = {}
    filings_obj = data.get("filings", {})

    # Process the "recent" filings block
    recent = filings_obj.get("recent", {})
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    for acc, pdoc in zip(accessions, primary_docs):
        if acc and pdoc:
            result[acc] = pdoc

    # Process overflow files (older filings)
    for overflow in filings_obj.get("files", []):
        fname = overflow.get("name", "")
        if not fname:
            continue
        overflow_url = f"https://data.sec.gov/submissions/{fname}"
        overflow_req = Request(overflow_url, headers={"User-Agent": EDGAR_UA})
        time.sleep(0.15)  # respect rate limit
        try:
            with urlopen(overflow_req, timeout=30) as resp:
                odata = json.loads(resp.read())
            o_acc = odata.get("accessionNumber", [])
            o_pdoc = odata.get("primaryDocument", [])
            for acc, pdoc in zip(o_acc, o_pdoc):
                if acc and pdoc:
                    result[acc] = pdoc
        except Exception as e:
            print(f"    WARNING: failed overflow {fname}: {e}")

    return result


def main() -> None:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    # Read existing filings from Supabase
    cur.execute("SELECT accession_number, cik, symbol FROM sec_filings")
    rows = cur.fetchall()
    print(f"Read {len(rows)} filings from sec_filings table")

    # Collect unique CIKs
    cik_to_symbol: dict[str, str] = {}
    for acc, cik, sym in rows:
        if cik and cik not in cik_to_symbol:
            cik_to_symbol[cik] = sym or "?"

    print(f"Fetching primary documents from EDGAR for {len(cik_to_symbol)} CIKs...")

    # Fetch submissions for each CIK
    all_lookups: dict[str, str] = {}
    for i, (cik, sym) in enumerate(cik_to_symbol.items(), 1):
        time.sleep(0.15)  # respect SEC rate limit
        lookup = fetch_edgar_submissions(cik)
        all_lookups.update(lookup)
        print(f"  [{i}/{len(cik_to_symbol)}] {sym} (CIK {cik}) -> "
              f"{len(lookup)} filings indexed", flush=True)

    # Update rows in Supabase
    matched = 0
    for acc, cik, sym in rows:
        pdoc = all_lookups.get(acc, "")
        if pdoc:
            cur.execute(
                "UPDATE sec_filings SET primary_document = %s "
                "WHERE accession_number = %s",
                (pdoc, acc),
            )
            matched += 1

    cur.close()
    conn.close()
    print(f"Updated primary_document for {matched}/{len(rows)} filings in sec_filings table")


if __name__ == "__main__":
    main()
