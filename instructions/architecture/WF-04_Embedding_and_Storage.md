# WF-04: Embedding Generation & Vector Storage

## Purpose

This workflow takes the cleaned, chunked, and metadata-enriched output from WF-03 and transforms it into vector embeddings stored in Supabase. This is what makes semantic retrieval possible in Mode 2.

---

## Goals

- Generate a vector embedding for every chunk produced by WF-03
- Store embeddings alongside chunk text and metadata in the Supabase `chunks` table
- Ensure the database is always consistent with the processing registry — no stale embeddings from old document versions

---

## Embedding Model

**Recommended model:** OpenAI `text-embedding-3-large` with 1536 dimensions.

This model supports flexible output dimensions — the full model produces 3072 dimensions but can be configured to output 1536 with minimal quality loss. 1536 dimensions is recommended as the default because it halves storage consumption in Supabase, which is important given the free tier's 500MB limit and the cost of Supabase Pro storage.

To use 1536 dimensions, pass `dimensions: 1536` in the OpenAI API call. Update the `chunks` table schema accordingly — the `embedding` column should be `vector(1536)` not `vector(3072)`. If you created the schema with 3072 as defined in WF-00, update it before loading any embeddings:

```sql
ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(1536);
```

**Why not a free embedding model?** Open-source embedding models (e.g., sentence-transformers) require local compute to run, which conflicts with the goal of minimal setup complexity on a Mac. OpenAI's embedding API is very cheap ($0.065 per million tokens at 1536 dims) and requires no local infrastructure. For a corpus of 10,000 documents at ~100 chunks each averaging 400 tokens per chunk, the total one-time embedding cost is approximately $26.

---

## What Gets Embedded

Each chunk is embedded as a combination of its metadata context prepended to the chunk text. This improves retrieval relevance significantly — queries that reference a ticker or document type will semantically match even if those words don't appear in the chunk body.

**Embedding input format:**
```
Ticker: AAPL | Document: Earnings Transcript Q4 2024 | Section: CFO Prepared Remarks
[chunk text here...]
```

---

## Supabase Storage

Embeddings and chunk data are stored in the `chunks` table created in WF-00. Each row represents one chunk and contains both the embedding vector and all metadata needed for filtered retrieval.

**Key indexes on the chunks table** (created in WF-00):

Standard indexes on `ticker`, `document_type`, `section_type`, and `filing_date` support metadata filtering. The vector search index (`ivfflat`) must be created **after** the initial corpus is loaded — not before. Creating it on an empty or partially-filled table and then bulk-inserting data is significantly slower than loading all data first and indexing afterward.

**Run this only after initial corpus load is complete:**
```sql
CREATE INDEX idx_chunks_embedding
    ON chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
```

The `lists` parameter should be roughly the square root of the total number of rows. At 1 million chunks, use `lists = 1000`. At 100,000 chunks, use `lists = 316`. At initial scale (~50,000 chunks), `lists = 100` is appropriate.

---

## Handling Document Updates

When WF-01 detects that a document has changed (hash mismatch), prior embeddings must be deactivated before new ones are inserted:

1. Set `is_active = FALSE` on all chunks where `document_id` matches the updated document
2. Process the updated document through WF-03 to generate new chunks
3. Insert new chunks with fresh embeddings via this workflow
4. Update the processing registry record with the new hash and chunk count

Hard deletion of old chunks is intentionally avoided. Keeping deactivated chunks preserves the ability to audit historical document versions and supports potential future features like change detection between document versions.

---

## Batching

The OpenAI embedding API supports batching multiple texts in a single request. Always batch:

- Target batch size: 50–100 chunks per API call
- A typical 50-page earnings transcript produces 60–100 chunks — usually 1–2 API calls
- Batching reduces latency and the number of API calls significantly at scale

---

## Output

- All chunks for the processed document are stored in the Supabase `chunks` table with embeddings and full metadata
- Processing registry is updated: `processing_status = 'complete'`, `chunk_count` populated, `last_processed_at` set
- Document is now queryable via semantic search in Mode 2

---

## Key Considerations

**Never mix embedding model versions.** All chunks in the database must be embedded with the same model and the same dimensions. Semantic similarity search across vectors from different models produces meaningless results. If you ever need to upgrade the embedding model, every chunk in the database must be re-embedded before the new model can be used. Treat embedding model selection as a long-term commitment.

**Supabase storage growth.** Monitor storage usage in the Supabase dashboard under **Settings → Database**. When approaching the 500MB free tier limit, either upgrade to Supabase Pro ($25/month) or export older/less-used embeddings to cold storage. The Supabase dashboard shows a clear storage usage indicator.

**Embedding API errors.** The OpenAI embedding API occasionally returns rate limit or timeout errors under load. Implement exponential backoff with up to 3 retries before marking a document as failed. A failed embedding job should not affect other documents processing in parallel.
