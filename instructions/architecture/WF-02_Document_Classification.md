# WF-02: Document Classification

## Purpose

Each document type has a different structure, different natural sections, and different chunking logic. Before a document can be chunked, the pipeline needs to know what kind of document it is so it can apply the right processing rules. This workflow classifies each incoming document and routes it to the appropriate chunking template in WF-03.

---

## Goals

- Identify the document type for every document in the job queue
- Enrich the processing registry in Supabase with document type before chunking begins
- Route each document to the correct chunking template downstream

---

## Current State vs. Future State

### Current State — Transcripts Only (Flat Structure)

The Google Drive folder structure is currently:
```
/transcripts/{ticker}/{filename}.txt
```

There is no document type subfolder. All documents at this level are earnings transcripts. Classification is therefore trivial — any document found under `/transcripts/{ticker}/` is assigned type `earnings_transcript` without reading the file or making any API call.

**Classification rule for current structure:**
```
IF file_path matches /transcripts/{ticker}/*.txt
THEN document_type = 'earnings_transcript'
       chunking_template = 'Template A'
       classification_method = 'path'
```

This is deterministic, instant, and costs nothing.

### Future State — Multiple Document Types

When additional document types are added (10-Ks, 8-Ks, etc.), the folder structure will be updated to include a document type subfolder:
```
/transcripts/{ticker}/{document_type}/{filename}.txt
```

At that point the classification rule becomes:
```
IF file_path matches /transcripts/{ticker}/earnings_transcript/*.txt  → earnings_transcript
IF file_path matches /transcripts/{ticker}/10K/*.txt                  → 10K
IF file_path matches /transcripts/{ticker}/10Q/*.txt                  → 10Q
IF file_path matches /transcripts/{ticker}/8K/*.txt                   → 8K
```

WF-02 should be built with this two-phase logic from the start — check for a document type subfolder first, and fall back to the flat-structure rule if no subfolder exists. This avoids needing to rewrite WF-02 when new document types are introduced.

---

## Classification Logic (Full Decision Tree)

```
1. Does the file path contain a document_type subfolder?
   (i.e., does /transcripts/{ticker}/{subfolder}/ match a known document type?)
      YES → classify from subfolder name
      NO  → continue to step 2

2. Is the file located directly under /transcripts/{ticker}/?
      YES → classify as 'earnings_transcript'
      NO  → continue to step 3

3. Does the filename contain recognizable keywords?
   (see keyword table below)
      YES → classify from keyword match
      NO  → continue to step 4

4. Invoke Claude to classify from first 500 words of document content
      SUCCESS → classify from LLM response, log as classification_method = 'llm'
      FAILURE → classify as 'unknown', flag for manual review
```

---

## Keyword Fallback Table

Used in step 3 above when file is not in the expected folder structure:

| Keywords in filename | Classified as |
|---|---|
| `transcript`, `earnings_call`, `call` | `earnings_transcript` |
| `10-K`, `10K`, `annual_report` | `10K` |
| `10-Q`, `10Q`, `quarterly_report` | `10Q` |
| `8-K`, `8K` | `8K` |
| `investor_day`, `investor_presentation` | `investor_day` |
| `proxy`, `DEF14A` | `proxy` |

---

## Supported Document Types

| Type | Description | Chunking template |
|---|---|---|
| `earnings_transcript` | Quarterly earnings call transcript | Template A — see WF-03 |
| `10K` | Annual SEC filing | Template B — see WF-03 |
| `10Q` | Quarterly SEC filing | Template C — see WF-03 |
| `8K` | Material event filing | Template D — see WF-03 |
| `investor_day` | Investor day presentation transcript | Template E — see WF-03 |
| `unknown` | Could not classify | Flag for manual review |

---

## Output

Each document in the job queue is enriched with:

- `document_type` — one of the types above
- `chunking_template` — which template WF-03 should apply
- `classification_method` — `path` / `filename` / `llm` / `manual`

These are written to the `processing_registry` table in Supabase before WF-03 begins.

Documents classified as `unknown` have their `processing_status` set to `failed` and `error_message` set to `'Could not classify document type — manual review required'`. They are excluded from further processing until resolved.

---

## Key Considerations

**For the current corpus, every document should classify via the path rule.** If any documents are classified by keyword match or LLM fallback during the initial pipeline run, it indicates a folder structure inconsistency that should be fixed in Google Drive rather than worked around in code.

**Log every LLM classification.** Each time Claude is invoked to classify a document, log the file path and the classification result. Review these logs periodically — a pattern of LLM classifications signals a folder structure problem upstream that is worth fixing at the source.

**Build for future document types now.** The decision tree above handles both the current flat structure and the future subfolder structure. Implementing the full logic now means WF-02 requires no changes when 10-Ks and other document types are introduced — only the Google Drive folder structure needs updating.

**Unknown documents never silently fail.** Any document that cannot be classified is flagged explicitly in the processing registry. Query `WHERE processing_status = 'failed' AND error_message LIKE '%classify%'` in Supabase to find and resolve unclassified documents.
