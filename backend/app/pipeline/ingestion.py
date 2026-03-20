"""WF-01: Document Ingestion & Change Detection.

Scans the transcripts_list table in Supabase for new or changed documents.
Computes content hashes and checks against processing_registry in Supabase.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field


@dataclass
class DocumentJob:
    """A document queued for processing."""
    file_path: str
    ticker: str
    fiscal_period: str
    file_hash: str
    content: str | None = None
    document_type: str = "earnings_transcript"
    is_update: bool = False
    document_id: str | None = None  # set for updates


def compute_content_hash(content: str) -> str:
    """MD5 hash of text content."""
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def extract_fiscal_period(filename: str) -> str | None:
    """Extract fiscal period from transcript filename.

    Expected format: {YYYY}_Q{N}.txt → Q{N}_{YYYY}
    """
    m = re.match(r"(\d{4})_Q(\d)\.txt$", filename)
    if m:
        return f"Q{m.group(2)}_{m.group(1)}"
    return None


def reset_stuck_jobs(cur) -> int:
    """Reset documents stuck in 'processing' for >2 hours back to 'pending'."""
    cur.execute("""
        UPDATE processing_registry
        SET processing_status = 'pending',
            worker_id = NULL,
            processing_started_at = NULL
        WHERE processing_status = 'processing'
        AND processing_started_at < NOW() - INTERVAL '2 hours'
    """)
    return cur.rowcount


def scan_for_documents(cur) -> list[DocumentJob]:
    """Query transcripts_list for documents needing processing.

    Uses two bulk queries (transcripts + registry) instead of per-row lookups,
    then compares in Python.

    Returns:
        List of DocumentJob for new or changed documents.
    """
    # 1. Fetch all transcripts with content
    cur.execute(
        "SELECT symbol, fiscal_year, fiscal_quarter, transcripts "
        "FROM transcripts_list WHERE transcripts IS NOT NULL"
    )
    transcript_rows = cur.fetchall()

    # 2. Bulk-fetch entire processing_registry for transcripts (one query)
    cur.execute(
        "SELECT file_path, document_id, file_hash, processing_status "
        "FROM processing_registry WHERE file_path LIKE '/transcripts/%%'"
    )
    registry: dict[str, dict] = {}
    for file_path, document_id, file_hash, status in cur.fetchall():
        registry[file_path] = {
            "document_id": str(document_id),
            "file_hash": file_hash,
            "status": status,
        }

    # 3. Compare and build job list
    jobs: list[DocumentJob] = []

    for symbol, fiscal_year, fiscal_quarter, transcripts_text in transcript_rows:
        if not transcripts_text or not transcripts_text.strip():
            continue

        ticker = symbol
        year = str(fiscal_year)
        quarter = str(fiscal_quarter)
        filename = f"{year}_Q{quarter}.txt"
        file_path = f"/transcripts/{ticker}/{filename}"
        content_hash = compute_content_hash(transcripts_text)
        fiscal_period = f"Q{quarter}_{year}"

        existing = registry.get(file_path)

        if existing is None:
            # New document
            jobs.append(DocumentJob(
                file_path=file_path,
                ticker=ticker,
                fiscal_period=fiscal_period,
                file_hash=content_hash,
                content=transcripts_text,
                is_update=False,
            ))
        elif existing["file_hash"] != content_hash:
            # Changed document
            jobs.append(DocumentJob(
                file_path=file_path,
                ticker=ticker,
                fiscal_period=fiscal_period,
                file_hash=content_hash,
                content=transcripts_text,
                is_update=True,
                document_id=existing["document_id"],
            ))
        # else: unchanged, skip

    return jobs


def register_document(cur, job: DocumentJob) -> str:
    """Insert or update processing_registry for a document. Returns document_id."""
    if job.is_update and job.document_id:
        # Deactivate old chunks
        cur.execute(
            "UPDATE chunks SET is_active = FALSE WHERE document_id = %s",
            (job.document_id,),
        )
        # Update registry
        cur.execute(
            """UPDATE processing_registry
               SET file_hash = %s, processing_status = 'pending',
                   worker_id = NULL, processing_started_at = NULL, error_message = NULL
               WHERE document_id = %s
               RETURNING document_id""",
            (job.file_hash, job.document_id),
        )
        return str(cur.fetchone()[0])
    else:
        cur.execute(
            """INSERT INTO processing_registry
               (ticker, document_type, file_path, file_hash, processing_status)
               VALUES (%s, %s, %s, %s, 'pending')
               RETURNING document_id""",
            (job.ticker, job.document_type, job.file_path, job.file_hash),
        )
        return str(cur.fetchone()[0])
