from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.data_access.db import get_sync_conn
from app.exceptions import NotFoundError

router = APIRouter(prefix="/api/transcripts", tags=["transcripts"])


def _fetch_transcript_text(symbol: str, year: int, quarter: int) -> str:
    """Validate inputs and fetch transcript text from Supabase."""
    clean_symbol = re.sub(r"[^A-Za-z0-9_\-]", "", symbol).upper()
    if not clean_symbol:
        raise NotFoundError("Invalid symbol")

    if quarter < 1 or quarter > 4:
        raise NotFoundError("Quarter must be between 1 and 4")

    conn = get_sync_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT transcripts FROM transcripts_list "
        "WHERE symbol = %s AND fiscal_year = %s AND fiscal_quarter = %s",
        (clean_symbol, str(year), str(quarter)),
    )
    row = cur.fetchone()
    cur.close()

    if row is None or not row[0]:
        raise NotFoundError(f"Transcript not found for {clean_symbol} {year} Q{quarter}")

    return row[0]


def _parse_transcript_table(text: str) -> list[dict[str, Any]]:
    """Parse the text-table transcript format into structured paragraphs.

    Expected format:
        +----+--------+----------+
        | paragraph_number | speaker | content |
        +====+========+==========+
        | 1  | Name   | Text...  |
        +----+--------+----------+
        | 2  | Name   | Text...  |
        ...
    """
    paragraphs: list[dict[str, Any]] = []

    for line in text.splitlines():
        # Skip separator rows (+----- or +===== patterns)
        if not line or line.startswith("+"):
            continue

        # Data rows start with |
        if not line.startswith("|"):
            continue

        # Split by | and strip whitespace from each cell
        cells = [cell.strip() for cell in line.split("|")]
        # line.split("|") on "|  1 | Name | Text |" gives ['', '1', 'Name', 'Text', '']
        # Filter out empty strings from leading/trailing |
        cells = [c for c in cells if c != ""]

        if len(cells) < 3:
            continue

        # Skip the header row
        if cells[0] == "paragraph_number":
            continue

        try:
            para_num = int(cells[0])
        except ValueError:
            continue

        speaker = cells[1]
        content = cells[2]

        paragraphs.append({
            "paragraph_number": para_num,
            "speaker": speaker,
            "content": content,
        })

    return paragraphs


@router.get("/{symbol}/{year}/{quarter}")
async def get_transcript(symbol: str, year: int, quarter: int) -> list[dict[str, Any]]:
    """Return transcript as structured JSON with speaker paragraphs."""
    text = _fetch_transcript_text(symbol, year, quarter)
    return _parse_transcript_table(text)


@router.get("/{symbol}/{year}/{quarter}/raw")
async def get_transcript_raw(symbol: str, year: int, quarter: int) -> PlainTextResponse:
    """Return the raw transcript text file (original table format)."""
    text = _fetch_transcript_text(symbol, year, quarter)
    return PlainTextResponse(text)
