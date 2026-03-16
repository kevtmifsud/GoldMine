"""WF-01: Document Ingestion & Change Detection.

Scans the local transcripts directory for new or changed documents.
Computes content hashes and checks against processing_registry in Supabase.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import psycopg2

from .config import TRANSCRIPTS_DIR


@dataclass
class DocumentJob:
    """A document queued for processing."""
    file_path: str
    ticker: str
    fiscal_period: str
    file_hash: str
    document_type: str = "earnings_transcript"
    is_update: bool = False
    document_id: str | None = None  # set for updates


def compute_file_hash(path: Path) -> str:
    """MD5 hash of file contents."""
    h = hashlib.md5()
    h.update(path.read_bytes())
    return h.hexdigest()


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


def scan_for_documents(cur, transcripts_dir: Path | None = None) -> list[DocumentJob]:
    """Scan transcripts directory and return list of documents needing processing.

    Returns:
        List of DocumentJob for new or changed documents.
    """
    base_dir = transcripts_dir or TRANSCRIPTS_DIR
    if not base_dir.exists():
        return []

    jobs: list[DocumentJob] = []

    # Iterate ticker folders
    for ticker_dir in sorted(base_dir.iterdir()):
        if not ticker_dir.is_dir():
            continue
        ticker = ticker_dir.name

        for txt_file in sorted(ticker_dir.glob("*.txt")):
            file_path = f"/transcripts/{ticker}/{txt_file.name}"
            file_hash = compute_file_hash(txt_file)
            fiscal_period = extract_fiscal_period(txt_file.name)

            if fiscal_period is None:
                continue

            # Check processing registry
            cur.execute(
                "SELECT document_id, file_hash, processing_status FROM processing_registry WHERE file_path = %s",
                (file_path,),
            )
            row = cur.fetchone()

            if row is None:
                # New document
                jobs.append(DocumentJob(
                    file_path=file_path,
                    ticker=ticker,
                    fiscal_period=fiscal_period,
                    file_hash=file_hash,
                    is_update=False,
                ))
            elif row[1] != file_hash:
                # Changed document
                jobs.append(DocumentJob(
                    file_path=file_path,
                    ticker=ticker,
                    fiscal_period=fiscal_period,
                    file_hash=file_hash,
                    is_update=True,
                    document_id=str(row[0]),
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
