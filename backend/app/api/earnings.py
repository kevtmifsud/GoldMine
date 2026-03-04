from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/api/earnings", tags=["earnings"])

_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "structured"
_EARNINGS_CSV = _DATA_DIR / "earnings_calendar.csv"
_TRANSCRIPTS_CSV = _DATA_DIR / "transcripts_list.csv"
_SEC_FILINGS_CSV = _DATA_DIR / "sec_filings.csv"


def _quarter_from_month(month: int) -> int:
    """Map month (1-12) to fiscal quarter (1-4)."""
    return (month - 1) // 3 + 1


def _parse_fiscal_quarter_ending(fqe: str) -> tuple[int, int] | None:
    """Return (fiscal_year, fiscal_quarter) from a fiscal_quarter_ending date string."""
    try:
        dt = datetime.strptime(fqe, "%Y-%m-%d")
        return dt.year, _quarter_from_month(dt.month)
    except (ValueError, TypeError):
        return None


def _has_transcript(symbol: str, year: int, quarter: int) -> bool:
    if not _TRANSCRIPTS_CSV.exists():
        return False
    with open(_TRANSCRIPTS_CSV, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (
                row["symbol"] == symbol
                and int(row["fiscal_year"]) == year
                and int(row["fiscal_quarter"]) == quarter
            ):
                return True
    return False


def _find_filing_url(symbol: str, report_date_str: str) -> str | None:
    """Find the 10-Q filing URL for the given symbol closest to the report_date."""
    if not _SEC_FILINGS_CSV.exists():
        return None
    try:
        target = datetime.strptime(report_date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None

    best_url: str | None = None
    best_diff: int | None = None
    with open(_SEC_FILINGS_CSV, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["symbol"] != symbol or row["form_type"] != "10-Q":
                continue
            try:
                rd = datetime.strptime(row["report_date"], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                continue
            diff = abs((rd - target).days)
            if best_diff is None or diff < best_diff:
                best_diff = diff
                best_url = row.get("filing_url") or None
    # Only match if within ~120 days (one quarter)
    if best_diff is not None and best_diff <= 120:
        return best_url
    return None


@router.get("/{ticker}")
async def get_earnings(ticker: str) -> dict[str, Any]:
    """Return last and next earnings dates for a ticker."""
    ticker_upper = ticker.upper()
    today = date.today().isoformat()

    if not _EARNINGS_CSV.exists():
        return {"ticker": ticker_upper, "last_earnings": None, "next_earnings": None}

    # Load all earnings rows for this ticker
    rows: list[dict[str, str]] = []
    with open(_EARNINGS_CSV, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["ticker"] == ticker_upper:
                rows.append(row)
    rows.sort(key=lambda r: r["report_date"])

    last_row: dict[str, str] | None = None
    next_row: dict[str, str] | None = None

    for row in rows:
        if row["report_date"] <= today:
            last_row = row
        elif next_row is None:
            next_row = row

    last_earnings: dict[str, Any] | None = None
    next_earnings: dict[str, Any] | None = None
    all_earnings: list[dict[str, Any]] = []

    for row in rows:
        if row["report_date"] <= today:
            fqe = row.get("fiscal_quarter_ending", "")
            parsed = _parse_fiscal_quarter_ending(fqe)
            all_earnings.append({
                "report_date": row["report_date"],
                "fiscal_year": parsed[0] if parsed else None,
                "fiscal_quarter": parsed[1] if parsed else None,
            })

    if last_row:
        fqe = last_row.get("fiscal_quarter_ending", "")
        parsed = _parse_fiscal_quarter_ending(fqe)
        fy = parsed[0] if parsed else None
        fq = parsed[1] if parsed else None

        last_earnings = {
            "report_date": last_row["report_date"],
            "time": last_row.get("time", ""),
            "fiscal_quarter_ending": fqe,
            "fiscal_year": fy,
            "fiscal_quarter": fq,
            "has_transcript": _has_transcript(ticker_upper, fy, fq) if fy and fq else False,
            "filing_url": _find_filing_url(ticker_upper, fqe) if fqe else None,
        }

    if next_row:
        fqe = next_row.get("fiscal_quarter_ending", "")
        next_earnings = {
            "report_date": next_row["report_date"],
            "time": next_row.get("time", ""),
            "fiscal_quarter_ending": fqe,
        }

    return {
        "ticker": ticker_upper,
        "last_earnings": last_earnings,
        "next_earnings": next_earnings,
        "all_earnings": all_earnings,
    }
