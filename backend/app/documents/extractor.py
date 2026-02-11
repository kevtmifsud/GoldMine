from __future__ import annotations

import re

from app.logging_config import get_logger

logger = get_logger(__name__)


def extract_text(file_bytes: bytes, mime_type: str, filename: str) -> str:
    """Extract text content from a file based on its mime type."""
    lower_mime = mime_type.lower()
    lower_name = filename.lower()

    if lower_mime in ("text/plain", "text/csv") or lower_name.endswith((".txt", ".csv")):
        try:
            return file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            logger.warning("utf8_decode_failed", filename=filename)
            return file_bytes.decode("utf-8", errors="replace")

    if lower_mime == "application/pdf" or lower_name.endswith(".pdf"):
        return _extract_pdf(file_bytes, filename)

    if lower_mime.startswith("audio/") or lower_name.endswith((".mp3", ".wav", ".m4a")):
        logger.info("audio_skip", filename=filename)
        return ""

    logger.warning("unsupported_mime", mime_type=mime_type, filename=filename)
    return ""


def _extract_pdf(file_bytes: bytes, filename: str) -> str:
    """Extract text from PDF bytes using pypdf."""
    try:
        import io

        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(file_bytes))
        pages: list[str] = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
        return "\n\n".join(pages)
    except Exception as e:
        logger.error("pdf_extraction_failed", filename=filename, error=str(e))
        return ""


def chunk_text(
    text: str,
    chunk_size: int = 800,
    overlap: int = 100,
) -> list[tuple[str, int, int]]:
    """Split text into overlapping chunks at sentence/paragraph boundaries.

    Returns list of (chunk_text, char_start, char_end).
    """
    if not text or not text.strip():
        return []

    # Split into sentences (at period/newline boundaries)
    sentences: list[tuple[str, int, int]] = []
    for m in re.finditer(r"[^\n]+", text):
        line = m.group()
        line_start = m.start()
        # Split line into sentences at period boundaries
        for sm in re.finditer(r"[^.!?]*[.!?]+\s*|[^.!?]+$", line):
            s = sm.group()
            if s.strip():
                start = line_start + sm.start()
                end = line_start + sm.end()
                sentences.append((s, start, end))

    if not sentences:
        # Fallback: treat entire text as one chunk
        return [(text.strip(), 0, len(text))]

    chunks: list[tuple[str, int, int]] = []
    current_texts: list[str] = []
    current_len = 0
    chunk_start = sentences[0][1]

    for sent_text, sent_start, sent_end in sentences:
        sent_len = len(sent_text)

        if current_len + sent_len > chunk_size and current_texts:
            # Emit current chunk
            chunk_text_str = "".join(current_texts).strip()
            if chunk_text_str:
                chunks.append((chunk_text_str, chunk_start, sent_start))

            # Calculate overlap: keep sentences from the end that fit in overlap
            overlap_texts: list[str] = []
            overlap_len = 0
            for t in reversed(current_texts):
                if overlap_len + len(t) > overlap:
                    break
                overlap_texts.insert(0, t)
                overlap_len += len(t)

            current_texts = overlap_texts + [sent_text]
            current_len = overlap_len + sent_len
            chunk_start = sent_start - overlap_len if overlap_texts else sent_start
            chunk_start = max(0, chunk_start)
        else:
            current_texts.append(sent_text)
            current_len += sent_len

    # Emit remaining text
    if current_texts:
        chunk_text_str = "".join(current_texts).strip()
        if chunk_text_str:
            last_end = sentences[-1][2] if sentences else len(text)
            chunks.append((chunk_text_str, chunk_start, last_end))

    return chunks
