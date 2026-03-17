from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter

from app.data_access.db import get_sync_conn

router = APIRouter(prefix="/api/earnings", tags=["earnings"])


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
    conn = get_sync_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM transcripts_list "
        "WHERE symbol = %s AND fiscal_year = %s AND fiscal_quarter = %s LIMIT 1",
        (symbol, str(year), str(quarter)),
    )
    found = cur.fetchone() is not None
    cur.close()
    return found


def _find_filing_url(symbol: str, report_date_str: str) -> str | None:
    """Find the 10-Q filing URL for the given symbol closest to the report_date."""
    try:
        target = datetime.strptime(report_date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None

    conn = get_sync_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT filing_url, report_date FROM sec_filings "
        "WHERE symbol = %s AND form_type = '10-Q'",
        (symbol,),
    )
    best_url: str | None = None
    best_diff: int | None = None
    for filing_url, rd_str in cur.fetchall():
        try:
            rd = datetime.strptime(str(rd_str), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        diff = abs((rd - target).days)
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best_url = filing_url or None
    cur.close()

    if best_diff is not None and best_diff <= 120:
        return best_url
    return None


@router.get("/{ticker}")
async def get_earnings(ticker: str) -> dict[str, Any]:
    """Return last and next earnings dates for a ticker."""
    ticker_upper = ticker.upper()
    today = date.today().isoformat()

    conn = get_sync_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT ticker, report_date, time, fiscal_quarter_ending "
        "FROM earnings_calendar WHERE ticker = %s ORDER BY report_date",
        (ticker_upper,),
    )
    columns = [desc[0] for desc in cur.description]
    rows = [{col: str(val) if val is not None else "" for col, val in zip(columns, row)}
            for row in cur.fetchall()]
    cur.close()

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
