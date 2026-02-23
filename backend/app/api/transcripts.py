from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.config.settings import settings
from app.exceptions import NotFoundError

router = APIRouter(prefix="/api/transcripts", tags=["transcripts"])


@router.get("/{symbol}/{year}/{quarter}")
async def get_transcript(symbol: str, year: int, quarter: int) -> PlainTextResponse:
    # Sanitize symbol: strip path traversal characters, uppercase
    clean_symbol = re.sub(r"[^A-Za-z0-9_\-]", "", symbol).upper()
    if not clean_symbol:
        raise NotFoundError("Invalid symbol")

    if quarter < 1 or quarter > 4:
        raise NotFoundError("Quarter must be between 1 and 4")

    data_dir = Path(settings.DATA_DIR).resolve()
    transcript_path = (data_dir / "transcripts" / clean_symbol / f"{year}_Q{quarter}.txt").resolve()

    # Path traversal protection
    if not str(transcript_path).startswith(str(data_dir)):
        raise NotFoundError("Invalid path")

    if not transcript_path.is_file():
        raise NotFoundError(f"Transcript not found for {clean_symbol} {year} Q{quarter}")

    text = transcript_path.read_text(encoding="utf-8")
    return PlainTextResponse(text)
