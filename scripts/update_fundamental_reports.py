#!/usr/bin/env python3
"""Download fundamental reports: company info, officers, SEC filings, transcripts.

Runs four phases:
  Phase 1 — Stock Info:     Company profile data merged into stocks.csv
  Phase 2 — Stock Officers: Executive officer data merged into people.csv
  Phase 3 — SEC Filings:    US domestic filings for whitelist tickers
  Phase 4 — Transcripts:    Earnings call transcripts for whitelist tickers

Output:
  Supabase tables: stocks, people, sec_filings, transcripts_list

CLI flags:
  --info-only              Only run Phase 1 (stock info)
  --officers-only          Only run Phase 2 (stock officers)
  --filings-only           Only run Phase 3 (SEC filings, whitelist)
  --transcripts-only       Only run Phase 4 (transcripts, whitelist)
  --whitelist TICKER ...   Override default whitelist
  --workers N              Thread pool size (default 10)
  --fresh                  Ignore checkpoints, re-fetch all
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen

import psycopg2
from psycopg2.extras import execute_values
from tabulate import tabulate

from defeatbeta_api.data.ticker import Ticker
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")

STRUCTURED_DIR = ROOT / "data" / "structured"

DATABASE_URL = os.environ.get(
    "SUPABASE_DATABASE_URL",
    "postgresql://postgres:sC.g6Wf#9h.Bf_f@db.ybjvfeevaxujenwvoewg.supabase.co:5432/postgres",
)

INFO_CHECKPOINT = ROOT / "scripts" / ".info_checkpoint.json"
OFFICERS_CHECKPOINT = ROOT / "scripts" / ".officers_checkpoint.json"

DEFAULT_WORKERS = 10

DEFAULT_WHITELIST = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "JPM",
    "JNJ", "XOM", "NVDA", "UNH", "META", "CVNA",
]

ALLOWED_FORM_TYPES = {
    "10-K", "10-K/A", "10-Q", "10-Q/A",
    "8-K", "8-K/A", "DEF 14A", "DEFA14A",
}

INFO_COLUMNS = [
    "address", "city", "phone", "zip",
    "long_business_summary", "full_time_employees", "web_site", "report_date",
]

PEOPLE_COLUMNS = [
    "person_id", "name", "title", "organization", "type", "tickers",
    "age", "born", "pay", "exercised", "unexercised",
]

OFFICERS_API_FIELDS = ["name", "title", "age", "born", "pay", "exercised", "unexercised"]

# Thread-safe checkpoint access
_checkpoint_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Ticker helpers
# ---------------------------------------------------------------------------

def load_tickers() -> list[str]:
    """Read tickers from the stocks Supabase table."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT ticker FROM stocks ORDER BY ticker")
    tickers = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return tickers


def to_api_ticker(ticker: str) -> str:
    """defeatbeta-api uses Yahoo Finance format (dashes instead of dots)."""
    return ticker.replace(".", "-")


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------

def load_checkpoint(path: Path) -> dict:
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def save_checkpoint(path: Path, data: dict) -> None:
    with _checkpoint_lock:
        with open(path, "w") as f:
            json.dump(data, f)


# ---------------------------------------------------------------------------
# Phase 1 — Stock Info (all tickers)
# ---------------------------------------------------------------------------

def fetch_info_for_ticker(ticker: str) -> dict | None:
    """Fetch company info fields for one ticker.

    Returns a dict with only the INFO_COLUMNS fields (no symbol/sector/industry/country
    since those already exist in stocks.csv).
    """
    api_ticker = to_api_ticker(ticker)
    t = Ticker(api_ticker, log_level=logging.WARNING)
    df = t.info()
    if df is None or df.empty:
        return None

    row = df.iloc[0]
    info: dict = {}
    for col in INFO_COLUMNS:
        val = row.get(col, "")
        if val is None:
            val = ""
        info[col] = str(val).strip()
    return info


def process_info_ticker(
    ticker: str,
    checkpoint: dict[str, dict],
) -> tuple[str, bool]:
    """Fetch info for one ticker and update checkpoint."""
    try:
        info = fetch_info_for_ticker(ticker)
        if info:
            with _checkpoint_lock:
                checkpoint[ticker] = info
            save_checkpoint(INFO_CHECKPOINT, checkpoint)
            return ticker, True
        return ticker, False
    except Exception:
        return ticker, False


def run_phase_info(tickers: list[str], workers: int, fresh: bool) -> None:
    """Phase 1: Download stock info and merge into stocks.csv."""
    print("=" * 60)
    print("Phase 1: Stock Info (merge into stocks.csv)")
    print("=" * 60)

    checkpoint: dict[str, dict] = {} if fresh else load_checkpoint(INFO_CHECKPOINT)
    if checkpoint and not fresh:
        print(f"Resuming from checkpoint ({len(checkpoint)} tickers already fetched)")

    remaining = [t for t in tickers if t not in checkpoint]

    if not remaining:
        print("All tickers already fetched (use --fresh to re-fetch)")
    else:
        print(f"Fetching stock info for {len(remaining)} tickers "
              f"({workers} threads)...")

        completed = 0
        failed: list[str] = []

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(process_info_ticker, ticker, checkpoint): ticker
                for ticker in remaining
            }
            for future in as_completed(futures):
                ticker = futures[future]
                completed += 1
                try:
                    _, ok = future.result()
                    if not ok:
                        failed.append(ticker)
                    if completed % 50 == 0 or completed == len(remaining):
                        print(f"  [{completed}/{len(remaining)}] info fetched...",
                              flush=True)
                except Exception as e:
                    failed.append(ticker)
                    print(f"  [{completed}/{len(remaining)}] {ticker} -> "
                          f"ERROR: {e}", file=sys.stderr, flush=True)

        if failed:
            print(f"WARNING: {len(failed)} tickers failed info fetch: "
                  f"{', '.join(sorted(failed)[:20])}", file=sys.stderr)

    if not checkpoint:
        print("No stock info data to merge")
        return

    # Update stocks table in Supabase with info fields
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    merged_count = 0
    for ticker, info in checkpoint.items():
        cur.execute(
            """UPDATE stocks SET
                   address = %s, city = %s, phone = %s, zip = %s,
                   long_business_summary = %s, full_time_employees = %s,
                   web_site = %s, report_date = %s
               WHERE ticker = %s""",
            (
                info.get("address", ""), info.get("city", ""),
                info.get("phone", ""), info.get("zip", ""),
                info.get("long_business_summary", ""),
                info.get("full_time_employees", ""),
                info.get("web_site", ""), info.get("report_date", ""),
                ticker,
            ),
        )
        merged_count += 1

    cur.close()
    conn.close()
    print(f"Merged info for {merged_count} tickers into stocks table")

    # Clean up checkpoint if all tickers done
    if len(checkpoint) >= len(tickers) and INFO_CHECKPOINT.exists():
        INFO_CHECKPOINT.unlink()
        print("Checkpoint removed (all tickers complete)")


# ---------------------------------------------------------------------------
# Phase 2 — Stock Officers (all tickers)
# ---------------------------------------------------------------------------

def fetch_officers_for_ticker(ticker: str) -> list[dict] | None:
    """Fetch officers for one ticker."""
    api_ticker = to_api_ticker(ticker)
    t = Ticker(api_ticker, log_level=logging.WARNING)
    df = t.officers()
    if df is None or df.empty:
        return None

    officers: list[dict] = []
    for _, row in df.iterrows():
        officer: dict = {"symbol": ticker}
        for col in OFFICERS_API_FIELDS:
            val = row.get(col, "")
            if val is None:
                val = ""
            officer[col] = str(val).strip()
        officers.append(officer)
    return officers


def process_officers_ticker(
    ticker: str,
    checkpoint: dict[str, list[dict]],
) -> tuple[str, int]:
    """Fetch officers for one ticker and update checkpoint."""
    try:
        officers = fetch_officers_for_ticker(ticker)
        if officers:
            with _checkpoint_lock:
                checkpoint[ticker] = officers
            save_checkpoint(OFFICERS_CHECKPOINT, checkpoint)
            return ticker, len(officers)
        return ticker, 0
    except Exception:
        return ticker, -1


def _normalize_name(name: str) -> str:
    """Lowercase, collapse whitespace for name matching."""
    import re
    return re.sub(r"\s+", " ", name.strip().lower())


def run_phase_officers(tickers: list[str], workers: int, fresh: bool) -> None:
    """Phase 2: Download stock officers and merge into people.csv."""
    print("\n" + "=" * 60)
    print("Phase 2: Stock Officers (merge into people.csv)")
    print("=" * 60)

    checkpoint: dict[str, list[dict]] = {} if fresh else load_checkpoint(OFFICERS_CHECKPOINT)
    if checkpoint and not fresh:
        print(f"Resuming from checkpoint ({len(checkpoint)} tickers already fetched)")

    remaining = [t for t in tickers if t not in checkpoint]

    if not remaining:
        print("All tickers already fetched (use --fresh to re-fetch)")
    else:
        print(f"Fetching officers for {len(remaining)} tickers "
              f"({workers} threads)...")

        completed = 0
        failed: list[str] = []

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(process_officers_ticker, ticker, checkpoint): ticker
                for ticker in remaining
            }
            for future in as_completed(futures):
                ticker = futures[future]
                completed += 1
                try:
                    _, count = future.result()
                    if count < 0:
                        failed.append(ticker)
                    if completed % 50 == 0 or completed == len(remaining):
                        print(f"  [{completed}/{len(remaining)}] officers fetched...",
                              flush=True)
                except Exception as e:
                    failed.append(ticker)
                    print(f"  [{completed}/{len(remaining)}] {ticker} -> "
                          f"ERROR: {e}", file=sys.stderr, flush=True)

        if failed:
            print(f"WARNING: {len(failed)} tickers failed officers fetch: "
                  f"{', '.join(sorted(failed)[:20])}", file=sys.stderr)

    # Flatten all fetched officers
    all_officers: list[dict] = []
    for officers_list in checkpoint.values():
        all_officers.extend(officers_list)

    if not all_officers:
        print("No officers data to merge")
        return

    # Read existing people from Supabase
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("SELECT person_id, name, title, organization, type, tickers, "
                "age, born, pay, exercised, unexercised FROM people")
    columns = [desc[0] for desc in cur.description]
    people: list[dict] = [
        {col: str(val) if val is not None else "" for col, val in zip(columns, row)}
        for row in cur.fetchall()
    ]

    # Build name index for matching
    name_to_person: dict[str, dict] = {}
    for p in people:
        name_to_person[_normalize_name(p["name"])] = p

    # Find max person_id for new records
    max_id = 0
    for p in people:
        pid = p.get("person_id", "")
        if pid.startswith("PER-"):
            try:
                max_id = max(max_id, int(pid.split("-")[1]))
            except ValueError:
                pass
    next_id = max_id + 1

    compensation_fields = ["age", "born", "pay", "exercised", "unexercised"]
    matched = 0
    new_records = 0

    for officer in all_officers:
        norm = _normalize_name(officer["name"])
        symbol = officer.get("symbol", "").strip()

        if norm in name_to_person:
            person = name_to_person[norm]
            matched += 1
            for field in compensation_fields:
                val = officer.get(field, "").strip()
                if val:
                    person[field] = val
            if symbol:
                existing = [t.strip() for t in person.get("tickers", "").split(";") if t.strip()]
                if symbol not in existing:
                    existing.append(symbol)
                    person["tickers"] = ";".join(existing)
        else:
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
            for field in compensation_fields:
                new_person[field] = officer.get(field, "").strip()
            people.append(new_person)
            name_to_person[norm] = new_person

    # Upsert all people into Supabase
    db_rows = [
        tuple(p.get(col, "") for col in PEOPLE_COLUMNS)
        for p in people
    ]
    if db_rows:
        execute_values(cur,
            """INSERT INTO people (person_id, name, title, organization, type,
                                   tickers, age, born, pay, exercised, unexercised)
               VALUES %s
               ON CONFLICT (person_id) DO UPDATE SET
                   name = EXCLUDED.name, title = EXCLUDED.title,
                   organization = EXCLUDED.organization, type = EXCLUDED.type,
                   tickers = EXCLUDED.tickers, age = EXCLUDED.age,
                   born = EXCLUDED.born, pay = EXCLUDED.pay,
                   exercised = EXCLUDED.exercised, unexercised = EXCLUDED.unexercised""",
            db_rows, page_size=1000,
        )

    cur.close()
    conn.close()
    print(f"Merged {matched} matched + {new_records} new officer records "
          f"into {len(people)} total people rows -> people table")

    # Clean up checkpoint if all tickers done
    if len(checkpoint) >= len(tickers) and OFFICERS_CHECKPOINT.exists():
        OFFICERS_CHECKPOINT.unlink()
        print("Checkpoint removed (all tickers complete)")


# ---------------------------------------------------------------------------
# Phase 3 — SEC Filings (whitelist only)
# ---------------------------------------------------------------------------

def fetch_filings_for_ticker(ticker: str) -> list[dict]:
    """Fetch SEC filings for one ticker, filtering to US domestic forms."""
    api_ticker = to_api_ticker(ticker)
    t = Ticker(api_ticker, log_level=logging.WARNING)
    df = t.sec_filing()
    if df is None or df.empty:
        return []

    filings: list[dict] = []
    columns = list(df.columns)

    for _, row in df.iterrows():
        filing: dict = {col: str(row.get(col, "")).strip() for col in columns}
        filing["symbol"] = ticker

        # Filter by form_type if the column exists
        if "form_type" in columns:
            if filing.get("form_type", "") not in ALLOWED_FORM_TYPES:
                continue

        filings.append(filing)

    return filings


_EDGAR_UA = "GoldMine admin@goldmine.dev"


def _fetch_edgar_submissions(cik: str) -> dict[str, str]:
    """Fetch primaryDocument for all filings of a CIK from data.sec.gov.

    Returns {accession_number: primary_document_filename}.
    SEC rate-limits to 10 req/sec; callers should pace requests.
    """
    cik_padded = cik.lstrip("0").zfill(10)
    base_url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    req = Request(base_url, headers={"User-Agent": _EDGAR_UA})

    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except Exception:
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
        overflow_req = Request(overflow_url, headers={"User-Agent": _EDGAR_UA})
        time.sleep(0.15)  # respect rate limit
        try:
            with urlopen(overflow_req, timeout=30) as resp:
                odata = json.loads(resp.read())
            o_acc = odata.get("accessionNumber", [])
            o_pdoc = odata.get("primaryDocument", [])
            for acc, pdoc in zip(o_acc, o_pdoc):
                if acc and pdoc:
                    result[acc] = pdoc
        except Exception:
            pass

    return result


def _enrich_filings_with_primary_doc(
    all_filings: list[dict],
) -> None:
    """Add primary_document field to filings by querying EDGAR submissions API."""
    # Group filings by CIK
    cik_set: dict[str, str] = {}  # cik -> first symbol (for logging)
    for f in all_filings:
        cik = f.get("cik", "")
        if cik and cik not in cik_set:
            cik_set[cik] = f.get("symbol", "?")

    print(f"  Fetching primary documents from EDGAR for {len(cik_set)} CIKs...")

    # Fetch submissions for each CIK
    all_lookups: dict[str, str] = {}
    for i, (cik, sym) in enumerate(cik_set.items(), 1):
        time.sleep(0.15)  # respect SEC rate limit (10 req/sec)
        lookup = _fetch_edgar_submissions(cik)
        all_lookups.update(lookup)
        print(f"    [{i}/{len(cik_set)}] {sym} (CIK {cik}) -> "
              f"{len(lookup)} filings indexed", flush=True)

    # Enrich filings
    matched = 0
    for f in all_filings:
        acc = f.get("accession_number", "")
        pdoc = all_lookups.get(acc, "")
        f["primary_document"] = pdoc
        if pdoc:
            matched += 1

    print(f"  Matched primary documents for {matched}/{len(all_filings)} filings")


def run_phase_filings(whitelist: list[str], workers: int) -> None:
    """Phase 3: Download SEC filings for whitelist tickers."""
    print("\n" + "=" * 60)
    print("Phase 3: SEC Filings")
    print("=" * 60)
    print(f"Whitelist: {', '.join(whitelist)}")

    all_filings: list[dict] = []
    completed = 0
    failed: list[str] = []
    filing_columns: list[str] | None = None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(fetch_filings_for_ticker, ticker): ticker
            for ticker in whitelist
        }
        for future in as_completed(futures):
            ticker = futures[future]
            completed += 1
            try:
                filings = future.result()
                if filings:
                    if filing_columns is None:
                        filing_columns = list(filings[0].keys())
                    all_filings.extend(filings)
                print(f"  [{completed}/{len(whitelist)}] {ticker} -> "
                      f"{len(filings)} filings", flush=True)
            except Exception as e:
                failed.append(ticker)
                print(f"  [{completed}/{len(whitelist)}] {ticker} -> "
                      f"ERROR: {e}", file=sys.stderr, flush=True)

    if failed:
        print(f"WARNING: {len(failed)} tickers failed filings fetch: "
              f"{', '.join(sorted(failed))}", file=sys.stderr)

    if not all_filings or filing_columns is None:
        print("No filings data to write")
        return

    # Enrich with primary document URLs from EDGAR submissions API
    _enrich_filings_with_primary_doc(all_filings)

    # Upsert into Supabase sec_filings table
    _SEC_COLS = [
        "accession_number", "symbol", "cik", "company_name", "form_type",
        "form_type_description", "filing_date", "report_date",
        "acceptance_date_time", "filing_url", "primary_document",
    ]

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    db_rows = [
        tuple(f.get(col, "") for col in _SEC_COLS)
        for f in all_filings
        if f.get("accession_number")  # skip rows without PK
    ]

    if db_rows:
        execute_values(cur,
            """INSERT INTO sec_filings (accession_number, symbol, cik, company_name,
                                        form_type, form_type_description, filing_date,
                                        report_date, acceptance_date_time, filing_url,
                                        primary_document)
               VALUES %s
               ON CONFLICT (accession_number) DO UPDATE SET
                   symbol = EXCLUDED.symbol, cik = EXCLUDED.cik,
                   company_name = EXCLUDED.company_name,
                   form_type = EXCLUDED.form_type,
                   form_type_description = EXCLUDED.form_type_description,
                   filing_date = EXCLUDED.filing_date,
                   report_date = EXCLUDED.report_date,
                   acceptance_date_time = EXCLUDED.acceptance_date_time,
                   filing_url = EXCLUDED.filing_url,
                   primary_document = EXCLUDED.primary_document""",
            db_rows, page_size=1000,
        )

    cur.close()
    conn.close()

    unique_tickers = {r["symbol"] for r in all_filings}
    print(f"Upserted {len(db_rows)} filing rows ({len(unique_tickers)} tickers) "
          f"into sec_filings table")


# ---------------------------------------------------------------------------
# Phase 4 — Earnings Call Transcripts (whitelist only)
# ---------------------------------------------------------------------------

def run_phase_transcripts(whitelist: list[str]) -> None:
    """Phase 4: Download earnings call transcripts for whitelist tickers."""
    print("\n" + "=" * 60)
    print("Phase 4: Earnings Call Transcripts")
    print("=" * 60)
    print(f"Whitelist: {', '.join(whitelist)}")

    all_transcript_index: list[dict] = []
    index_columns: list[str] | None = None

    for i, ticker in enumerate(whitelist, 1):
        print(f"\n  [{i}/{len(whitelist)}] {ticker}...")
        api_ticker = to_api_ticker(ticker)

        try:
            t = Ticker(api_ticker, log_level=logging.WARNING)
            transcripts_obj = t.earning_call_transcripts()
            index_df = transcripts_obj.get_transcripts_list()

            if index_df is None or index_df.empty:
                print(f"    No transcripts available for {ticker}")
                continue

            # Collect index rows
            for _, row in index_df.iterrows():
                index_row = {col: str(row.get(col, "")).strip() for col in index_df.columns}
                index_row["symbol"] = ticker
                all_transcript_index.append(index_row)
                if index_columns is None:
                    index_columns = list(index_df.columns)

            print(f"    Found {len(index_df)} transcripts")

            # Fetch individual transcripts and store formatted text in index rows
            fetched = 0

            for _, row in index_df.iterrows():
                year = int(row["fiscal_year"])
                quarter = int(row["fiscal_quarter"])

                try:
                    transcript_df = transcripts_obj.get_transcript(year, quarter)
                    if transcript_df is None or transcript_df.empty:
                        continue

                    formatted = tabulate(
                        transcript_df,
                        headers="keys",
                        tablefmt="grid",
                        showindex=False,
                    )

                    # Find the matching index row and store the formatted text
                    for idx_row in all_transcript_index:
                        if (idx_row["symbol"] == ticker
                                and str(idx_row.get("fiscal_year")) == str(year)
                                and str(idx_row.get("fiscal_quarter")) == str(quarter)):
                            idx_row["transcripts"] = formatted
                            break

                    fetched += 1
                except Exception as e:
                    print(f"    WARNING: Failed to fetch {ticker} {year} Q{quarter}: {e}",
                          file=sys.stderr, flush=True)

            print(f"    Fetched {fetched} transcripts for {ticker}")

        except Exception as e:
            print(f"    ERROR fetching transcripts for {ticker}: {e}",
                  file=sys.stderr, flush=True)

    # Upsert transcripts index into Supabase
    if not all_transcript_index or index_columns is None:
        print("\nNo transcript index data to write")
        return

    _TL_COLS = [
        "transcripts_id", "symbol", "fiscal_year", "fiscal_quarter",
        "report_date", "transcripts",
    ]

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    # Generate synthetic IDs for rows where the API returned <NA> or empty
    for r in all_transcript_index:
        tid = r.get("transcripts_id", "")
        if not tid or tid == "<NA>" or tid == "nan":
            r["transcripts_id"] = f"{r['symbol']}-{r['fiscal_year']}-Q{r['fiscal_quarter']}"

    db_rows = [
        tuple(r.get(col, "") for col in _TL_COLS)
        for r in all_transcript_index
        if r.get("transcripts_id")
    ]

    if db_rows:
        execute_values(cur,
            """INSERT INTO transcripts_list (transcripts_id, symbol, fiscal_year,
                                             fiscal_quarter, report_date, transcripts)
               VALUES %s
               ON CONFLICT (transcripts_id) DO UPDATE SET
                   symbol = EXCLUDED.symbol, fiscal_year = EXCLUDED.fiscal_year,
                   fiscal_quarter = EXCLUDED.fiscal_quarter,
                   report_date = EXCLUDED.report_date,
                   transcripts = EXCLUDED.transcripts""",
            db_rows, page_size=1000,
        )

    cur.close()
    conn.close()

    unique_tickers = {r["symbol"] for r in all_transcript_index}
    print(f"\nUpserted {len(db_rows)} transcript index rows "
          f"({len(unique_tickers)} tickers) into transcripts_list table")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download fundamental reports: company info, officers, "
                    "SEC filings, and earnings call transcripts"
    )
    parser.add_argument("--info-only", action="store_true",
                        help="Only run Phase 1 (stock info)")
    parser.add_argument("--officers-only", action="store_true",
                        help="Only run Phase 2 (stock officers)")
    parser.add_argument("--filings-only", action="store_true",
                        help="Only run Phase 3 (SEC filings, whitelist)")
    parser.add_argument("--transcripts-only", action="store_true",
                        help="Only run Phase 4 (transcripts, whitelist)")
    parser.add_argument("--whitelist", nargs="+", metavar="TICKER",
                        help="Override default whitelist tickers")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"Thread pool size (default: {DEFAULT_WORKERS})")
    parser.add_argument("--fresh", action="store_true",
                        help="Ignore checkpoints, re-fetch all")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    tickers = load_tickers()
    whitelist = args.whitelist if args.whitelist else DEFAULT_WHITELIST
    # Validate whitelist tickers exist in the universe
    whitelist = [t for t in whitelist if t in set(tickers)]
    if args.whitelist and not whitelist:
        print("ERROR: None of the whitelist tickers found in stocks table",
              file=sys.stderr)
        sys.exit(1)

    phase_filter = (
        args.info_only or args.officers_only
        or args.filings_only or args.transcripts_only
    )

    print(f"Tickers: {len(tickers)} total, {len(whitelist)} in whitelist")
    print(f"Whitelist: {', '.join(whitelist)}")

    if not phase_filter or args.info_only:
        run_phase_info(tickers, args.workers, args.fresh)

    if not phase_filter or args.officers_only:
        run_phase_officers(tickers, args.workers, args.fresh)

    if not phase_filter or args.filings_only:
        run_phase_filings(whitelist, args.workers)

    if not phase_filter or args.transcripts_only:
        run_phase_transcripts(whitelist)

    print("\nDone!")


if __name__ == "__main__":
    main()
