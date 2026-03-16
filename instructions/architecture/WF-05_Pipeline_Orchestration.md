# WF-05: Pipeline Orchestration & Job Management

## Purpose

This workflow manages the end-to-end execution of the Mode 1 pipeline. It is responsible for scheduling the daily job, coordinating work across WF-01 through WF-04, managing parallelism, handling failures gracefully, and tracking costs. At thousands of documents across thousands of tickers, the reliability and efficiency of orchestration is as important as any individual workflow.

---

## Pipeline Execution Flow

```
Daily schedule trigger
        ↓
WF-01: Scan Google Drive for new/changed documents → build job queue
        ↓
WF-02: Classify each document → assign chunking template
        ↓
WF-03: Chunk and enrich with metadata → produce chunk lists
        ↓
WF-04: Generate embeddings → store in Supabase chunks table
        ↓
Update processing_registry → mark complete / failed
        ↓
Write run summary to pipeline_runs table
```

Each step hands off to the next. The Supabase `processing_registry` table is the shared state that all steps read from and write to.

---

## Parallelism

Sequential processing at scale is too slow. The pipeline should process multiple documents concurrently.

**Target concurrency:** 10–20 documents in parallel is a safe starting point. This is intentionally conservative given the Google Drive API rate limits discussed in WF-01. Increase concurrency only after confirming no rate limit errors in practice.

**Parallelism model:** A worker pool where a fixed number of workers pull jobs from the `processing_registry` queue (documents with `processing_status = 'pending'`) and process them independently. Each worker handles one document end-to-end through WF-02, WF-03, and WF-04.

---

## Job Queue — Claiming Work

Workers query Supabase for pending documents and claim them atomically to prevent two workers processing the same document:

```sql
UPDATE processing_registry
SET
    processing_status     = 'processing',
    worker_id             = '{worker_id}',
    processing_started_at = NOW()
WHERE document_id = (
    SELECT document_id
    FROM processing_registry
    WHERE processing_status = 'pending'
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
RETURNING *;
```

`FOR UPDATE SKIP LOCKED` is the key clause — it ensures only one worker can claim a given document even when many workers are querying simultaneously.

---

## Error Handling & Retries

| Failure type | Handling |
|---|---|
| Google Drive API rate limit | Pause that worker 30 seconds, retry — do not fail the document |
| Google Drive file download timeout | Retry up to 3 times with backoff, then mark as `failed` |
| OpenAI embedding API rate limit | Pause 10 seconds, retry — do not fail the document |
| Supabase write failure | Retry up to 3 times, then mark as `failed` and log |
| Worker crash mid-processing | Documents stuck in `processing` for >2 hours are reset to `pending` on next run start |
| Unreadable or malformed text file | Mark as `failed`, log error, skip — do not retry automatically |

**Stuck job recovery** — run this at the start of every pipeline execution before scanning for new documents:

```sql
UPDATE processing_registry
SET processing_status = 'pending',
    worker_id = NULL,
    processing_started_at = NULL
WHERE processing_status = 'processing'
AND processing_started_at < NOW() - INTERVAL '2 hours';
```

---

## Scheduling

The pipeline needs to run daily. Since this setup avoids cloud infrastructure, the simplest scheduler is a **cron job on your Mac** that triggers the pipeline script.

**To set up a daily cron job on Mac:**

Open Terminal and run `crontab -e`, then add:
```
0 7 * * * /path/to/your/pipeline/run.sh >> /path/to/logs/pipeline.log 2>&1
```

This runs the pipeline at 2am ET (7am UTC) daily. Adjust the time to suit your preference. Ensure your Mac is awake at the scheduled time, or use a tool like **Amphetamine** (free, Mac App Store) to keep it awake overnight.

**Alternative — run manually:** During development and early usage, simply run the pipeline manually whenever needed rather than scheduling it. Automate once the pipeline is stable and producing reliable results.

---

## Incremental vs. Full Reprocessing

**Normal daily run (incremental):** Only process new and changed documents. This is the default and keeps daily costs and runtime minimal.

**Full reprocessing:** Reprocess all documents regardless of hash. This is a deliberate, manually-triggered operation only needed in specific scenarios:
- Chunking template logic has been significantly updated
- Embedding model or dimensions have changed (requires complete re-embedding)
- Supabase chunks table has been rebuilt from scratch

Full reprocessing at thousands of documents is expensive and slow. Plan it as a scheduled event, not an ad-hoc operation.

---

## Cost Tracking

Every pipeline run writes a record to the `pipeline_runs` table in Supabase. Track:

| Metric | Why |
|---|---|
| Documents processed | Volume baseline |
| Chunks generated | Primary embedding cost driver |
| Estimated cost (USD) | Calculated from token counts × API pricing |
| Run duration | Performance monitoring |
| Documents failed | Quality and reliability signal |

**Estimating embedding cost:** Count the total tokens across all chunks in a run. At OpenAI's current pricing for `text-embedding-3-large` at 1536 dimensions ($0.065 per million tokens), even a large daily run of 500 new documents at 100 chunks × 400 tokens each is approximately $1.30.

---

## Run Summary

At the end of each run, the pipeline writes a completion record to `pipeline_runs`:

```
Run date:              2025-01-30
Run type:              incremental
Documents scanned:     4,847
Documents queued:      23
Documents succeeded:   22
Documents failed:      1
Chunks generated:      1,760
Estimated cost:        $0.46
Run duration:          24 minutes
```

Query this table in the Supabase SQL editor or Table Editor at any time to review run history.

---

## Key Considerations

**Observability is the highest priority.** Silent failures — documents that fail to process without any record — are the biggest operational risk. Every document must always have a clear, current status in `processing_registry`. Query `WHERE processing_status = 'failed'` regularly to catch and investigate issues.

**Keep the pipeline modular.** Each workflow (WF-01 through WF-04) should be independently re-runnable for a specific document. If chunking logic is updated, it should be possible to re-run just WF-03 and WF-04 for a targeted set of documents without re-running ingestion and classification.

**Start simple on scheduling.** A manual run or simple Mac cron job is entirely sufficient to start. Only move to a more robust scheduler (a small cloud VM running continuously, or a service like GitHub Actions on a schedule) if the Mac-based approach proves unreliable in practice.
