#!/usr/bin/env python3
"""Download fundamental reports: company info, officers, SEC filings, transcripts.

Runs four phases:
  Phase 1 — Stock Info:     Company profile data merged into stocks.csv
  Phase 2 — Stock Officers: Executive officer data merged into people.csv
  Phase 3 — SEC Filings:    US domestic filings for whitelist tickers
  Phase 4 — Transcripts:    Earnings call transcripts for whitelist tickers

Output files:
  data/structured/stocks.csv (info fields merged)
  data/structured/people.csv (officers merged)
  data/structured/sec_filings.csv
  data/structured/transcripts_list.csv
  data/structured/transcripts/{TICKER}/{YYYY}_Q{N}.txt

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
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tabulate import tabulate

from defeatbeta_api.data.ticker import Ticker

ROOT = Path(__file__).resolve().parent.parent
STOCKS_CSV = ROOT / "data" / "structured" / "stocks.csv"
STRUCTURED_DIR = ROOT / "data" / "structured"
TRANSCRIPTS_DIR = STRUCTURED_DIR / "transcripts"

PEOPLE_CSV = STRUCTURED_DIR / "people.csv"
FILINGS_CSV = STRUCTURED_DIR / "sec_filings.csv"
TRANSCRIPTS_LIST_CSV = STRUCTURED_DIR / "transcripts_list.csv"

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
    """Read tickers from stocks.csv."""
    tickers: list[str] = []
    with open(STOCKS_CSV, newline="") as f:
        for row in csv.DictReader(f):
            ticker = row["ticker"].strip()
            if ticker:
                tickers.append(ticker)
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

    # Read existing stocks.csv
    stocks: list[dict] = []
    with open(STOCKS_CSV, newline="") as f:
        reader = csv.DictReader(f)
        stock_fields = list(reader.fieldnames or [])
        for row in reader:
            stocks.append(row)

    # Ensure info columns are in the field list
    merged_fields = list(stock_fields)
    for col in INFO_COLUMNS:
        if col not in merged_fields:
            merged_fields.append(col)

    # Merge fetched info into stock rows
    merged_count = 0
    for stock in stocks:
        ticker = stock["ticker"].strip()
        info = checkpoint.get(ticker)
        if info:
            merged_count += 1
            for col in INFO_COLUMNS:
                stock[col] = info.get(col, "")

    # Write merged stocks.csv
    STRUCTURED_DIR.mkdir(parents=True, exist_ok=True)
    with open(STOCKS_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=merged_fields)
        writer.writeheader()
        for stock in stocks:
            writer.writerow({col: stock.get(col, "") for col in merged_fields})

    print(f"Merged info for {merged_count}/{len(stocks)} tickers into {STOCKS_CSV}")

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

    # Read existing people.csv
    people: list[dict] = []
    if PEOPLE_CSV.exists():
        with open(PEOPLE_CSV, newline="") as f:
            for row in csv.DictReader(f):
                people.append(row)

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

    # Write merged people.csv
    people.sort(key=lambda p: p.get("name", "").strip().lower())

    STRUCTURED_DIR.mkdir(parents=True, exist_ok=True)
    with open(PEOPLE_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=PEOPLE_COLUMNS)
        writer.writeheader()
        for row in people:
            writer.writerow({col: row.get(col, "") for col in PEOPLE_COLUMNS})

    print(f"Merged {matched} matched + {new_records} new officer records "
          f"into {len(people)} total people rows -> {PEOPLE_CSV}")

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

    # Ensure symbol is the first column
    if "symbol" in filing_columns:
        filing_columns.remove("symbol")
    filing_columns.insert(0, "symbol")

    STRUCTURED_DIR.mkdir(parents=True, exist_ok=True)
    with open(FILINGS_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=filing_columns)
        writer.writeheader()
        for row in sorted(all_filings, key=lambda r: (
            r.get("symbol", ""), r.get("filing_date", ""),
        )):
            writer.writerow({col: row.get(col, "") for col in filing_columns})

    unique_tickers = {r["symbol"] for r in all_filings}
    print(f"Wrote {len(all_filings)} filing rows ({len(unique_tickers)} tickers) "
          f"to {FILINGS_CSV}")


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

            # Fetch individual transcripts
            ticker_dir = TRANSCRIPTS_DIR / ticker
            ticker_dir.mkdir(parents=True, exist_ok=True)
            fetched = 0

            for _, row in index_df.iterrows():
                year = int(row["fiscal_year"])
                quarter = int(row["fiscal_quarter"])
                filename = f"{year}_Q{quarter}.txt"
                filepath = ticker_dir / filename

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
                    filepath.write_text(formatted, encoding="utf-8")
                    fetched += 1
                except Exception as e:
                    print(f"    WARNING: Failed to fetch {ticker} {year} Q{quarter}: {e}",
                          file=sys.stderr, flush=True)

            print(f"    Saved {fetched} transcript files to {ticker_dir}")

        except Exception as e:
            print(f"    ERROR fetching transcripts for {ticker}: {e}",
                  file=sys.stderr, flush=True)

    # Write transcripts index CSV
    if not all_transcript_index or index_columns is None:
        print("\nNo transcript index data to write")
        return

    # Ensure symbol is the first column
    if "symbol" in index_columns:
        index_columns.remove("symbol")
    index_columns.insert(0, "symbol")

    STRUCTURED_DIR.mkdir(parents=True, exist_ok=True)
    with open(TRANSCRIPTS_LIST_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=index_columns)
        writer.writeheader()
        for row in sorted(all_transcript_index, key=lambda r: (
            r.get("symbol", ""),
            r.get("fiscal_year", ""),
            r.get("fiscal_quarter", ""),
        )):
            writer.writerow({col: row.get(col, "") for col in index_columns})

    unique_tickers = {r["symbol"] for r in all_transcript_index}
    print(f"\nWrote {len(all_transcript_index)} transcript index rows "
          f"({len(unique_tickers)} tickers) to {TRANSCRIPTS_LIST_CSV}")


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
        print("ERROR: None of the whitelist tickers found in stocks.csv",
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
