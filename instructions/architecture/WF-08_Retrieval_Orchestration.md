# WF-08: Retrieval Orchestration

## Purpose

Retrieval orchestration takes the classified query and resolved ticker universe and assembles the context that Claude uses to generate the answer. Different query types require fundamentally different retrieval strategies. This workflow routes each query to the right strategy, enforces chunk limits to control cost, checks the screening cache, and surfaces Q&A library hits.

---

## Goals

- Route each query type to the correct retrieval strategy
- Enforce per-query chunk limits to keep input token costs predictable
- Check screening cache before running expensive multi-ticker retrieval
- Surface relevant Q&A library entries as prior validated context
- Return a structured context package to WF-09 for response generation

---

## Q&A Library Lookup — Runs First on Every Query

Before any document retrieval, check the Q&A library for semantically similar validated answers. This runs on every query type without exception.

**Process:**
1. Embed the user's question using the `query_embedder` model
2. Search `qa_library` using pgvector cosine similarity on `question_embedding`
3. Filter to entries where `validation_type IS NOT NULL` (only validated entries)
4. Apply a similarity threshold of 0.88 — below this, results are too dissimilar to be useful
5. Return top 2 entries if above threshold, otherwise empty

**Deduplication logic:**
If a Q&A library entry exists with similarity > 0.92 for the same ticker and fiscal period as the current query, surface it prominently in the context with an instruction to Claude to reference it directly rather than regenerating from scratch. This is the primary deduplication mechanism — analytically identical questions from different analysts converge to the same validated answer.

---

## Screening Cache Check

For `screening` query type only, check the cache before any retrieval:

1. Hash the query text + fiscal period as a cache key
2. Look up `screening_cache` WHERE `query_hash` = key AND `expires_at` > NOW()
3. If hit: increment `hit_count`, return cached result directly to WF-09 — skip all retrieval
4. If miss: proceed with full retrieval, write result to cache with `expires_at = NOW() + INTERVAL '24 hours'`

---

## Retrieval Strategy by Query Type

### Single Ticker Qualitative

```
Filter: ticker = X, is_active = TRUE
Optional filter: section_type = classifier hint (if provided)
Optional filter: fiscal_period IN classifier periods (if provided)
Rank: cosine similarity to query embedding
Return: top 6 chunks
```

Straightforward filtered semantic search. Fast and precise.

---

### Single Ticker Quantitative

No vector search. Query Supabase structured tables directly:

```sql
-- Example for gross margin question
SELECT ticker, fiscal_period, gross_margin, gross_profit, revenue
FROM income_statement
WHERE ticker = 'AAPL'
AND fiscal_period IN ('Q4_2024', 'Q3_2024')
AND period_type = 'quarterly';
```

The classifier's `needs_structured_data: true` flag and `topic` field determine which table and columns to query. Return exact figures formatted as a structured data block for WF-09.

For hybrid questions (e.g., "what was the margin and what did management say about it"):
- Run both the structured table query AND the vector search
- Return both result sets to WF-09 separately

---

### Cross-Ticker Comparison

Run parallel vector searches — one per ticker in the resolved universe.

**Per-ticker retrieval:**
```
Filter: ticker = X, is_active = TRUE
Optional filter: section_type = classifier hint
Optional filter: fiscal_period IN classifier periods
Rank: cosine similarity to query embedding
Return: top 3 chunks per ticker (not 6 — cost control for large universes)
```

**Parallelism:** All per-ticker searches run concurrently, not sequentially. At 20 tickers with 3 chunks each, this is 60 chunks total — manageable context.

**Cap:** Maximum 50 tickers as defined in WF-07. At 50 tickers × 3 chunks = 150 chunks, which is large. If ticker count exceeds 20, reduce to top 2 chunks per ticker automatically.

---

### Screening

Screening queries span the entire active ticker universe. Two-stage approach to control cost:

**Stage 1 — Broad retrieval (pgvector):**
```
Filter: is_active = TRUE
Filter: section_type IN ('risk_factors', 'cfo_remarks') — or classifier hint
Filter: filing_date >= NOW() - INTERVAL '6 months' (recent only)
Rank: cosine similarity to query embedding
Return: top 3 chunks per ticker, up to 100 tickers
```

This can return up to 300 chunks. That is too large to pass directly to Sonnet.

**Stage 2 — Haiku pre-filter:**
Pass the 300 chunks to Haiku with a prompt asking it to identify the 20 most relevant chunks to the screening criteria. Haiku returns a list of chunk IDs.

Pass only those 20 chunks to Sonnet in WF-09.

This two-stage approach ensures Sonnet's context is focused and cost-controlled regardless of universe size.

---

### Trend Analysis

Retrieve chunks for one ticker across multiple fiscal periods, ordered chronologically.

```
Filter: ticker = X, is_active = TRUE
Filter: fiscal_period IN [last N quarters from classifier]
Optional filter: section_type = classifier hint
Rank: by filing_date ASC (chronological), then cosine similarity within period
Return: top 3 chunks per period
```

For 8 quarters at 3 chunks each = 24 chunks, ordered chronologically. Claude can reason about change over time from this sequence.

---

## Context Package Output

The assembled context passed to WF-09:

```python
class RetrievalContext(BaseModel):
    query_type: str
    structured_data: list[dict] | None
    chunks: list[ChunkResult]
    qa_library_hits: list[QALibraryEntry]
    cache_hit: bool
    total_chunks_retrieved: int
    total_input_tokens_estimate: int
```

Each `ChunkResult` includes the chunk text, full metadata (ticker, document_type, fiscal_period, section_name), and similarity score. The metadata is what enables sourcing in WF-09.

---

## Cost Tracking

Emits cost events for:

- `query_embedder` — one embedding call per user message (all query types)
- `screening_prefilter` — one Haiku call for screening queries only

The pgvector searches themselves are free Supabase operations and do not emit cost events.

See DS-04 for full cost logging specification.
