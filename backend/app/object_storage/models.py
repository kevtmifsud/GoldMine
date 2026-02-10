from __future__ import annotations

from pydantic import BaseModel


class FileMetadata(BaseModel):
    file_id: str
    filename: str
    path: str
    type: str
    mime_type: str
    size_bytes: int
    tickers: list[str]
    date: str
    description: str
