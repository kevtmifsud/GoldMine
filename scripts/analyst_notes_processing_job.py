"""Nightly job: process new analyst_notes rows through the document pipeline.

Queries analyst_notes for rows created in the last 24 hours where
chunks_processed = FALSE, sends each through WF-01→WF-05 via the existing
pipeline orchestrator, and marks processed rows as chunks_processed = TRUE.

Usage:
    python scripts/analyst_notes_processing_job.py
    python scripts/analyst_notes_processing_job.py --lookback-hours 48
    python scripts/analyst_notes_processing_job.py --dry-run
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import psycopg2
import structlog

# ---------------------------------------------------------------------------
# Ensure the backend package is importable when run from repo root
# ---------------------------------------------------------------------------
_backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(_backend_dir))

from app.pipeline.config import DATABASE_URL
from app.pipeline.ingestion import DocumentJob, compute_content_hash
from app.pipeline.orchestrator import process_single_document

logger = structlog.get_logger()


def _get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn


def fetch_unprocessed_notes(cur, lookback_hours: int = 24) -> list[dict]:
    """Return analyst_notes rows needing processing.

    Filters to rows where chunks_processed IS NOT TRUE and created_at is
    within the lookback window.  Uses LIMIT to avoid unbounded result sets.
    """
    cur.execute(
        """SELECT id, user_id, tickers, sectors, industries, content, created_at
           FROM analyst_notes
           WHERE (chunks_processed IS NOT TRUE)
             AND created_at >= NOW() - INTERVAL '%s hours'
           ORDER BY created_at
           LIMIT 1000""",
        (lookback_hours,),
    )
    columns = [desc[0] for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def build_document_job(note: dict) -> DocumentJob:
    """Build a DocumentJob with explicit doc_type override for an analyst note."""
    note_id = str(note["id"])
    content = note["content"] or ""
    tickers = note.get("tickers") or []
    # Use first ticker for the chunk-level ticker field, or 'MULTI' if multi-ticker
    primary_ticker = tickers[0] if len(tickers) == 1 else ("MULTI" if tickers else "NONE")

    return DocumentJob(
        file_path=f"/analyst_notes/{note_id}",
        ticker=primary_ticker,
        fiscal_period="",  # analyst notes are not period-specific
        file_hash=compute_content_hash(content),
        content=content,
        document_type="analyst_note",
        is_update=False,
        classification_method="explicit",
        metadata={
            "user_id": str(note["user_id"]),
            "ticker_list": tickers,
            "sector_list": note.get("sectors") or [],
            "industry_list": note.get("industries") or [],
            "source_note_id": note_id,
        },
    )


def mark_processed(cur, note_id: str) -> None:
    cur.execute(
        "UPDATE analyst_notes SET chunks_processed = TRUE WHERE id = %s",
        (note_id,),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Process new analyst notes into chunks.")
    parser.add_argument("--lookback-hours", type=int, default=24, help="Hours to look back for unprocessed notes (default 24)")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and report counts without processing")
    args = parser.parse_args()

    run_started = time.time()
    logger.info("analyst_notes_job_started", lookback_hours=args.lookback_hours)

    conn = _get_conn()
    cur = conn.cursor()

    notes = fetch_unprocessed_notes(cur, lookback_hours=args.lookback_hours)
    logger.info("unprocessed_notes_found", count=len(notes))

    cur.close()
    conn.close()

    if not notes:
        logger.info("analyst_notes_job_complete", processed=0, failed=0, skipped=0)
        return

    if args.dry_run:
        for note in notes:
            tickers = note.get("tickers") or []
            logger.info(
                "dry_run_note",
                note_id=str(note["id"]),
                user_id=str(note["user_id"]),
                tickers=tickers,
                content_length=len(note.get("content") or ""),
            )
        logger.info("dry_run_complete", total=len(notes))
        return

    processed = 0
    failed = 0
    skipped = 0

    for i, note in enumerate(notes, 1):
        note_id = str(note["id"])
        content = note.get("content") or ""

        if not content.strip():
            logger.warning("empty_note_skipped", note_id=note_id)
            skipped += 1
            continue

        log = logger.bind(note_id=note_id, progress=f"{i}/{len(notes)}")

        try:
            job = build_document_job(note)
            result = process_single_document(job)

            if result["status"] == "complete":
                conn = _get_conn()
                cur = conn.cursor()
                mark_processed(cur, note_id)
                cur.close()
                conn.close()

                processed += 1
                log.info(
                    "note_processed",
                    chunks=result["chunks"],
                    tickers=note.get("tickers") or [],
                )
            elif result["status"] == "skipped":
                skipped += 1
                log.warning("note_skipped", reason=result.get("error"))
            else:
                failed += 1
                log.error("note_failed", error=result.get("error"))

        except Exception:
            failed += 1
            log.exception("note_processing_error")

    duration = int(time.time() - run_started)
    logger.info(
        "analyst_notes_job_complete",
        processed=processed,
        failed=failed,
        skipped=skipped,
        duration_s=duration,
    )

    print(f"\nAnalyst Notes Processing Summary")
    print(f"  Processed: {processed}")
    print(f"  Failed:    {failed}")
    print(f"  Skipped:   {skipped}")
    print(f"  Duration:  {duration}s")


if __name__ == "__main__":
    main()
