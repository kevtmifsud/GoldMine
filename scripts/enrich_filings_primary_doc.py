#!/usr/bin/env python3
"""Enrich sec_filings.csv with primary_document field from EDGAR submissions API.

Reads the existing sec_filings.csv, fetches primaryDocument for each CIK from
data.sec.gov, and writes the enriched CSV back.

No external dependencies — uses only the Python standard library.
"""
from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
FILINGS_CSV = ROOT / "data" / "structured" / "sec_filings.csv"

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
    if not FILINGS_CSV.exists():
        print(f"ERROR: {FILINGS_CSV} not found")
        return

    # Read existing CSV
    rows: list[dict[str, str]] = []
    with open(FILINGS_CSV, newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        for row in reader:
            rows.append(row)

    print(f"Read {len(rows)} filings from {FILINGS_CSV}")

    # Collect unique CIKs
    cik_to_symbol: dict[str, str] = {}
    for row in rows:
        cik = row.get("cik", "")
        if cik and cik not in cik_to_symbol:
            cik_to_symbol[cik] = row.get("symbol", "?")

    print(f"Fetching primary documents from EDGAR for {len(cik_to_symbol)} CIKs...")

    # Fetch submissions for each CIK
    all_lookups: dict[str, str] = {}
    for i, (cik, sym) in enumerate(cik_to_symbol.items(), 1):
        time.sleep(0.15)  # respect SEC rate limit
        lookup = fetch_edgar_submissions(cik)
        all_lookups.update(lookup)
        print(f"  [{i}/{len(cik_to_symbol)}] {sym} (CIK {cik}) -> "
              f"{len(lookup)} filings indexed", flush=True)

    # Enrich rows
    matched = 0
    for row in rows:
        acc = row.get("accession_number", "")
        pdoc = all_lookups.get(acc, "")
        row["primary_document"] = pdoc
        if pdoc:
            matched += 1

    print(f"Matched primary documents for {matched}/{len(rows)} filings")

    # Write enriched CSV
    if "primary_document" not in fieldnames:
        fieldnames.append("primary_document")

    with open(FILINGS_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in fieldnames})

    print(f"Wrote enriched CSV to {FILINGS_CSV}")


if __name__ == "__main__":
    main()
