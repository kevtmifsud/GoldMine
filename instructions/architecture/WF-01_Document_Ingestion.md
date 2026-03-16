# WF-01: Document Ingestion & Change Detection

## Purpose

This workflow is the entry point for the entire Mode 1 pipeline. It runs on a daily schedule, scans the Google Drive `/transcripts/` folder for new or updated documents across all tickers, and determines what needs to be processed. Nothing downstream runs unless this workflow identifies work to do.

---

## Goals

- Detect new documents that have never been processed
- Detect existing documents that have changed since last processing
- Skip documents that are unchanged — this is the primary cost control mechanism
- Hand off a clean, deduplicated job list to the classification workflow (WF-02)

---

## Inputs

| Input | Description |
|---|---|
| Google Drive `/transcripts/` folder | Contains one subfolder per ticker, each holding .txt transcript files |
| `processing_registry` table in Supabase | Tracks every document processed, its hash, and current status |

---

## Current Document Storage Structure

Documents are currently organized in Google Drive as follows:

```
/transcripts/
  /AAPL/
    AAPL_Q4_2024.txt
    AAPL_Q3_2024.txt
    AAPL_Q2_2024.txt
  /MSFT/
    MSFT_Q4_2024.txt
  /GOOGL/
    ...
```

The pipeline extracts the ticker from the immediate parent folder name. All documents at this level are treated as `earnings_transcript` type — there is no document type subfolder in the current structure. WF-02 handles this with a path-based rule.

**Filename convention:** Transcript filenames should follow `{TICKER}_{FISCAL_PERIOD}.txt` (e.g., `AAPL_Q4_2024.txt`). The fiscal period component (`Q4_2024`) must match the period format used in the structured financial data CSVs. This alignment is required for Mode 2 to correctly join transcript context with financial figures.

**Future structure:** When document types beyond earnings transcripts are added (10-Ks, 8-Ks, etc.), the folder structure will be updated to include a document type subfolder layer:
```
/transcripts/
  /AAPL/
    /earnings_transcript/
      AAPL_Q4_2024.txt
    /10K/
      AAPL_FY2024_10K.txt
```
WF-02 will be updated at that time to use subfolder-based classification. Until then, the flat structure is handled correctly by WF-02's current path rule.

---

## Change Detection Logic

The pipeline uses **content hashing** to determine what needs processing:

1. For each .txt file found under `/transcripts/{ticker}/`, download file contents and compute an MD5 hash
2. Look up the hash in `processing_registry` for that file path
3. If no record exists → new document, queue for processing
4. If record exists and hash differs → document has changed, queue for reprocessing
5. If record exists and hash matches → unchanged, skip entirely

Content hashing is more reliable than relying on Google Drive's modified timestamps, which can be affected by syncing and upload behavior.

---

## Metadata Extracted From File Path

For every document queued for processing, the following metadata is extracted from the file path before any file content is read:

| Metadata field | Extracted from | Example |
|---|---|---|
| `ticker` | Parent folder name | `AAPL` |
| `document_type` | Hardcoded as `earnings_transcript` for current structure | `earnings_transcript` |
| `fiscal_period` | Filename between ticker and `.txt` | `Q4_2024` |
| `file_path` | Full Google Drive path | `/transcripts/AAPL/AAPL_Q4_2024.txt` |

---

## Processing Registry

The `processing_registry` table in Supabase serves as the pipeline's memory. It tracks the state of every document the pipeline has ever seen.

| Column | Description |
|---|---|
| `document_id` | Unique identifier for the document |
| `ticker` | Ticker symbol extracted from folder path |
| `document_type` | Set to `earnings_transcript` for all current documents |
| `file_path` | Full Google Drive path to the file |
| `file_hash` | MD5 hash of file contents at last processing |
| `first_processed_at` | Timestamp of initial processing |
| `last_processed_at` | Timestamp of most recent processing |
| `processing_status` | pending / processing / complete / failed / archived |
| `worker_id` | Which worker claimed this job |
| `processing_started_at` | When processing began — used for stuck job detection |
| `chunk_count` | Number of chunks generated, set by WF-03 |
| `classification_method` | How the document type was determined, set by WF-02 |
| `error_message` | Error detail if processing failed |

---

## Output

A list of documents queued for processing, each containing:

- Google Drive file path
- Ticker
- Document type (`earnings_transcript`)
- Fiscal period
- File hash
- Flag indicating first-time ingestion vs. update to an existing document

This list is passed to WF-02 for classification.

---

## Handling Document Updates

When a document is detected as changed (hash mismatch on an existing record):

1. Set `is_active = FALSE` on all chunks in Supabase where `document_id` matches the old record
2. Queue the document for full reprocessing through WF-02, WF-03, and WF-04
3. On completion, update the registry with the new hash and chunk count

Old chunks are soft-deleted rather than hard-deleted. This preserves the ability to audit historical document versions.

---

## Key Considerations

**Filename consistency is a dependency.** The fiscal period extracted from the filename must match the format used in the structured financial CSVs for Mode 2 cross-source queries to work. Before running the pipeline on the existing corpus, verify that all transcript filenames follow the `{TICKER}_{FISCAL_PERIOD}.txt` format and that `FISCAL_PERIOD` matches the CSV convention exactly (e.g., `Q4_2024` not `Q4-2024` or `2024Q4`).

**Google Drive API rate limits.** The default limit is 1,000 requests per 100 seconds. For a large corpus, scan by iterating folder by folder rather than requesting all files at once. Implement a short delay between file downloads if rate limit errors occur.

**Idempotency.** If the daily job is re-run after a failure, it must produce the same job queue without creating duplicate registry records. Always check for an existing record by `file_path` before inserting a new one.

**Stuck job recovery.** At the start of every pipeline run, before scanning for new documents, reset any documents that have been stuck in `processing` status for more than 2 hours back to `pending`. This recovers from worker crashes automatically.

---

## Failure Modes to Handle

| Failure | Handling |
|---|---|
| Google Drive API unavailable | Abort run, log error, retry on next scheduled run |
| File download fails | Log error, mark document as `failed`, skip — retry on next run |
| Supabase unavailable | Abort run entirely — do not partially process |
| Malformed filename (can't extract fiscal period) | Log warning, still queue document — WF-02 will handle gracefully |
| Documents stuck in `processing` >2 hours | Reset to `pending` at start of next run |
