# WF-11: Q&A Library Management

## Purpose

The Q&A library is the mechanism by which the platform gets smarter with usage. Every validated answer becomes institutional memory — surfaced to future analysts asking similar questions. This workflow covers how entries enter the library, how they are validated, how they are retrieved, and how they compound in value over time.

---

## Goals

- Capture every assistant response as a candidate library entry
- Provide analysts with simple tools to validate, correct, or reject answers
- Surface validated prior answers during retrieval before generating new ones
- Ensure the library reflects current knowledge — outdated entries do not mislead

---

## Library Entry Lifecycle

```
Assistant response generated (WF-09)
        ↓
Response stored in messages table — automatic library candidate
        ↓
Analyst interacts with feedback controls in Goldmine
        ↓
  thumbs_up → promoted to qa_library, validation_weight = 1.0
  edited    → corrected version promoted, validation_weight = 1.5
  thumbs_down → excluded from library, flagged for review
  flagged   → excluded, admin notified
        ↓
Future similar queries → library entry surfaces in WF-08 retrieval
        ↓
use_count increments each time entry is surfaced
```

---

## Promoting an Entry to the Library

When positive feedback is received (thumbs_up or edited):

1. Embed the question using `qa_library_embedder` model
2. Insert into `qa_library`:
   - `question`: the user's original question
   - `answer`: the assistant response (or edited version for `edited` type)
   - `question_embedding`: the embedded question
   - `source_chunks`: JSONB of chunks used in the original response
   - `tickers_referenced`: array from the original message
   - `query_type`: from the classifier
   - `fiscal_periods`: periods referenced in the answer
   - `validation_type`: `thumbs_up` or `edited_approved`
   - `validation_weight`: 1.0 for thumbs_up, 1.5 for edited_approved

---

## Validation Weight Rationale

Edited-and-approved answers carry higher weight (1.5 vs 1.0) because they represent cases where an analyst identified an error and corrected it — these are the highest quality entries in the library. When WF-08 retrieves library hits, entries are ranked by `similarity_score × validation_weight`, so edited entries surface preferentially over unedited ones for similar questions.

---

## Retrieval (in WF-08)

Library retrieval uses pgvector cosine similarity on `question_embedding`:

```sql
SELECT *, (question_embedding <=> $query_embedding) AS distance
FROM qa_library
WHERE validation_type IS NOT NULL
AND (question_embedding <=> $query_embedding) < 0.12  -- similarity > 0.88
ORDER BY (1 - (question_embedding <=> $query_embedding)) * validation_weight DESC
LIMIT 2;
```

The similarity threshold of 0.88 is intentionally high — only genuinely similar questions should surface a prior answer. A lower threshold risks surfacing misleading context for questions that are superficially similar but factually different.

---

## Handling Outdated Entries

Library entries can become outdated when new documents are processed — for example, a Q3 answer about AAPL margins becomes less relevant once Q4 data is available.

**Automatic staleness flagging:**
When Mode 1 processes a new document for a ticker, check the `qa_library` for entries that:
- Reference the same ticker
- Have `fiscal_periods` that are now superseded by the new document's period
- Have `query_type` of `single_ticker_qualitative` or `single_ticker_quantitative`

Flag these entries with a `is_stale` boolean column. Stale entries are not excluded from retrieval entirely — they may still be useful context — but Claude is instructed in the system prompt to note when a library entry references an older period than the current question.

---

## Deduplication Across Analysts

The primary deduplication value comes from the retrieval similarity threshold. When analyst B asks a question with >0.92 similarity to a question analyst A already answered and validated:

- The library entry surfaces with high confidence
- Claude is instructed to reference it directly
- The `use_count` on the entry increments
- No new Sonnet generation call is needed if the cache hit is clean

Over time, high `use_count` entries represent the team's most-asked questions. These can be surfaced proactively in a Goldmine "frequently asked" widget without any query required.

---

## Library Quality Monitoring

The following queries surface library health metrics:

**Most used library entries:**
```sql
SELECT question, tickers_referenced, use_count, validation_type
FROM qa_library
WHERE validation_type IS NOT NULL
ORDER BY use_count DESC
LIMIT 20;
```

**Entries flagged as incorrect:**
```sql
SELECT m.content, f.created_at, u.display_name
FROM message_feedback f
JOIN messages m ON f.message_id = m.id
JOIN user_profiles u ON f.user_id = u.user_id
WHERE f.feedback_type = 'flagged'
ORDER BY f.created_at DESC;
```

**Library coverage by ticker:**
```sql
SELECT
    ticker,
    COUNT(*) AS entry_count,
    SUM(use_count) AS total_uses,
    MAX(updated_at) AS last_updated
FROM qa_library, UNNEST(tickers_referenced) AS ticker
WHERE validation_type IS NOT NULL
GROUP BY ticker
ORDER BY entry_count DESC;
```

---

## Cost Tracking

Emits cost events for:

- `qa_library_embedder` — one embedding call per entry promoted to the library

Library retrieval (pgvector search in WF-08) is a free Supabase operation and does not emit a cost event.

See DS-04 for full cost logging specification.
