"""WF-05: Pipeline Orchestration & Job Management.

Coordinates WF-01 through WF-04 end-to-end. Manages the processing queue,
handles errors, logs pipeline runs, and tracks costs.
"""
from __future__ import annotations

import time
import traceback
from datetime import datetime
from pathlib import Path

import psycopg2

from .config import DATABASE_URL, TRANSCRIPTS_DIR
from .ingestion import scan_for_documents, register_document, reset_stuck_jobs, DocumentJob
from .classification import classify_document
from .chunking import chunk_transcript
from .embedding import generate_embeddings, store_chunks, get_embedding_cost


def process_single_document(
    cur,
    job: DocumentJob,
    transcripts_dir: Path,
) -> dict:
    """Process one document through WF-02 → WF-03 → WF-04.

    Returns a result dict with status and metrics.
    """
    result = {
        "ticker": job.ticker,
        "fiscal_period": job.fiscal_period,
        "status": "failed",
        "chunks": 0,
        "error": None,
    }

    # Resolve local file path
    # job.file_path is like /transcripts/AAPL/2024_Q4.txt
    parts = job.file_path.strip("/").split("/")
    # parts = ["transcripts", "AAPL", "2024_Q4.txt"]
    local_path = transcripts_dir / parts[1] / parts[2]

    if not local_path.exists():
        result["error"] = f"File not found: {local_path}"
        return result

    # Register document in processing_registry
    document_id = register_document(cur, job)

    # Mark as processing
    cur.execute(
        """UPDATE processing_registry
           SET processing_status = 'processing', processing_started_at = NOW()
           WHERE document_id = %s""",
        (document_id,),
    )

    try:
        # WF-02: Classification
        classification = classify_document(job.file_path)
        if classification.document_type == "unknown":
            raise ValueError(f"Could not classify document type for {job.file_path}")

        cur.execute(
            "UPDATE processing_registry SET document_type = %s, classification_method = %s WHERE document_id = %s",
            (classification.document_type, classification.classification_method, document_id),
        )

        # WF-03: Chunking
        chunks = chunk_transcript(local_path)
        if not chunks:
            # Mark as skipped rather than failed — document may have an unsupported format
            cur.execute(
                """UPDATE processing_registry
                   SET processing_status = 'skipped', error_message = 'No chunks produced (unsupported format)'
                   WHERE document_id = %s""",
                (document_id,),
            )
            result["status"] = "skipped"
            result["error"] = f"No chunks produced for {job.file_path}"
            return result

        # WF-04: Embedding + Storage
        embeddings = generate_embeddings(
            chunks,
            ticker=job.ticker,
            document_type=classification.document_type,
            fiscal_period=job.fiscal_period,
        )

        chunk_count = store_chunks(
            cur,
            document_id=document_id,
            ticker=job.ticker,
            document_type=classification.document_type,
            fiscal_period=job.fiscal_period,
            chunks=chunks,
            embeddings=embeddings,
        )

        # Mark as complete
        now = datetime.utcnow()
        cur.execute(
            """UPDATE processing_registry
               SET processing_status = 'complete',
                   chunk_count = %s,
                   first_processed_at = COALESCE(first_processed_at, %s),
                   last_processed_at = %s
               WHERE document_id = %s""",
            (chunk_count, now, now, document_id),
        )

        result["status"] = "complete"
        result["chunks"] = chunk_count

    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        cur.execute(
            """UPDATE processing_registry
               SET processing_status = 'failed', error_message = %s
               WHERE document_id = %s""",
            (error_msg, document_id),
        )
        result["error"] = error_msg

    return result


def run_pipeline(
    test_tickers: list[str] | None = None,
    test_limit: int | None = None,
    transcripts_dir: Path | None = None,
) -> dict:
    """Run the full Mode 1 pipeline.

    Args:
        test_tickers: If provided, only process these tickers.
        test_limit: If provided, only process this many documents.
        transcripts_dir: Override default transcripts directory.

    Returns:
        Summary dict with run metrics.
    """
    base_dir = transcripts_dir or TRANSCRIPTS_DIR
    run_started = time.time()

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    # Record pipeline run
    cur.execute(
        "INSERT INTO pipeline_runs (run_type, status) VALUES ('incremental', 'running') RETURNING run_id"
    )
    run_id = str(cur.fetchone()[0])

    print("=" * 60)
    print("Mode 1 Pipeline — Starting")
    print("=" * 60)

    # Reset stuck jobs
    stuck = reset_stuck_jobs(cur)
    if stuck:
        print(f"  Reset {stuck} stuck jobs")

    # WF-01: Scan for documents
    print("\nPhase 1: Scanning for new/changed documents...")
    jobs = scan_for_documents(cur, base_dir)

    # Filter by test tickers if specified
    if test_tickers:
        jobs = [j for j in jobs if j.ticker in test_tickers]

    if test_limit:
        # Distribute limit across tickers: pick latest files per ticker
        from collections import defaultdict
        by_ticker: dict[str, list] = defaultdict(list)
        for j in jobs:
            by_ticker[j.ticker].append(j)
        # Take from end (latest files) of each ticker, round-robin
        limited: list = []
        ticker_lists = {t: list(reversed(jl)) for t, jl in by_ticker.items()}
        idx = 0
        while len(limited) < test_limit and any(ticker_lists.values()):
            for t in sorted(ticker_lists.keys()):
                if ticker_lists[t] and len(limited) < test_limit:
                    limited.append(ticker_lists[t].pop(0))
            idx += 1
        jobs = limited

    print(f"  Found {len(jobs)} documents to process")

    if not jobs:
        cur.execute(
            """UPDATE pipeline_runs
               SET status = 'complete', run_completed_at = NOW(),
                   documents_scanned = 0, documents_queued = 0,
                   documents_succeeded = 0, documents_failed = 0,
                   chunks_generated = 0, estimated_cost_usd = 0,
                   run_duration_seconds = 0
               WHERE run_id = %s""",
            (run_id,),
        )
        cur.close()
        conn.close()
        print("  Nothing to process. Done.")
        return {"documents_queued": 0, "succeeded": 0, "failed": 0, "chunks": 0}

    # Process documents sequentially (parallelism can be added later)
    print(f"\nPhase 2: Processing {len(jobs)} documents...")
    succeeded = 0
    failed = 0
    total_chunks = 0

    for i, job in enumerate(jobs):
        label = f"  [{i + 1}/{len(jobs)}] {job.ticker} {job.fiscal_period}"
        try:
            result = process_single_document(cur, job, base_dir)
            if result["status"] == "complete":
                print(f"{label} — {result['chunks']} chunks")
                succeeded += 1
                total_chunks += result["chunks"]
            else:
                print(f"{label} — FAILED: {result['error']}")
                failed += 1
        except Exception as e:
            print(f"{label} — EXCEPTION: {e}")
            traceback.print_exc()
            failed += 1

    # Finalize pipeline run
    duration = int(time.time() - run_started)
    est_cost = get_embedding_cost(total_chunks)

    cur.execute(
        """UPDATE pipeline_runs
           SET status = 'complete', run_completed_at = NOW(),
               documents_scanned = %s, documents_queued = %s,
               documents_succeeded = %s, documents_failed = %s,
               chunks_generated = %s, estimated_cost_usd = %s,
               run_duration_seconds = %s
           WHERE run_id = %s""",
        (len(jobs), len(jobs), succeeded, failed, total_chunks, est_cost, duration, run_id),
    )

    # Log cost event for embeddings
    cur.execute(
        """INSERT INTO api_cost_events
           (mode, component, model, input_tokens, cost_usd)
           VALUES ('mode_1', 'document_embedder', %s, %s, %s)""",
        (f"text-embedding-3-large-1536", total_chunks * 500, est_cost),
    )

    cur.close()
    conn.close()

    # Print summary
    print("\n" + "=" * 60)
    print("Pipeline Run Summary")
    print("=" * 60)
    print(f"  Documents processed: {succeeded + failed}")
    print(f"  Succeeded: {succeeded}")
    print(f"  Failed: {failed}")
    print(f"  Chunks generated: {total_chunks}")
    print(f"  Estimated cost: ${est_cost:.4f}")
    print(f"  Duration: {duration}s")
    print("Done.")

    return {
        "documents_queued": len(jobs),
        "succeeded": succeeded,
        "failed": failed,
        "chunks": total_chunks,
        "cost_usd": est_cost,
        "duration_s": duration,
    }
