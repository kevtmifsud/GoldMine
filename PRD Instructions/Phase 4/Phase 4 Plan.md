# GoldMine Phase 4 — Unstructured Data & LLM Integration

## Context

Phase 3 delivered saved views, widget state overrides, and Analyst Packs. Phase 4 adds unstructured data support: document ingestion, indexing, search (keyword + semantic), and read-only LLM-powered analysis grounded in entity documents. The LLM integration is strictly read-only — it cannot modify views, widgets, or platform state.

**Key existing patterns to follow:**
- Backend: factory+provider singletons, Pydantic models, `request.state.user` for current user
- Frontend: functional components with hooks, BEM CSS, typed API services
- Auth: 3 users (analyst1/analyst2/pm1), JWT cookie-based
- Data: CSV files in `data/structured/`, unstructured files in `data/unstructured/`, document index in `data/documents/`

---

## Current State Assessment

Phase 4 is **substantially implemented**. A thorough codebase audit reveals the following status:

### Already Complete

| Area | Status | Details |
|------|--------|---------|
| Object storage & file manifest | Done | `backend/app/object_storage/` — local file storage, JSON manifest, type-based directories, 26 files tracked |
| Text extraction | Done | `backend/app/documents/extractor.py` — .txt, .csv, .pdf support via `pypdf`; audio files return empty string |
| Document chunking | Done | `extractor.py` — 800-char chunks with 100-char overlap at sentence boundaries |
| Document indexing | Done | `backend/app/documents/json_provider.py` — JSON flat-file index, 58 documents indexed |
| Keyword search | Done | Token-based scoring with metadata boost, top-5 chunks per document, sorted by relevance |
| LLM integration | Done | `backend/app/llm/anthropic_provider.py` — Anthropic Claude API, system prompt, citation tracking |
| Document API routes | Done | `backend/app/api/documents.py` — upload, list, search, LLM query endpoints |
| Auto-indexing | Done | Existing manifest files auto-indexed on first access |
| Dataset document synthesis | Done | Transcripts and SEC filings integrated as virtual documents |
| Frontend DocumentsPanel | Done | List, search, upload dialog, type badges, chunk excerpts |
| Frontend LLMQueryPanel | Done | Query textarea, loading state, response display, collapsible sources |
| Frontend FileUploadDialog | Done | File input, metadata form, validation, upload |
| Frontend DocumentInspectorDialog | Done | Preview for PDF/transcripts/audio, download, metadata display |
| Frontend ResearchDocumentsGrid | Done | AG Grid display, filtering, transcript viewer, CSV export |
| EntityPage integration | Done | DocumentsPanel + LLMQueryPanel rendered below widgets (non-dataset entities) |
| Backend tests | Done | 12 tests: upload, list, search, filters, validation, LLM query, auth |
| Configuration | Done | `ANTHROPIC_API_KEY`, `LLM_MODEL`, `LLM_MAX_CONTEXT_CHUNKS`, `LLM_MAX_RESPONSE_TOKENS`, `DOCUMENTS_DIR` |

### Gaps Remaining

| Gap | PRD Requirement | Priority | Effort |
|-----|----------------|----------|--------|
| Semantic search / vector embeddings | FR-4.2, FR-4.3: "Support keyword and semantic search" | High | Medium |
| Frontend file size validation | FR-4.1: "Ingestion pipeline must validate file type and integrity" | Medium | Low |
| Search result highlighting | FR-4.3: Improve result readability | Low | Low |
| Document deletion UI | FR-4.1: Complete document management | Low | Low |
| LLM error resilience | FR-4.5: Graceful degradation | Medium | Low |

---

## Remaining Implementation Stages

### Stage 1: Semantic Search with Vector Embeddings

The PRD explicitly requires semantic search alongside keyword search. Currently only keyword search is implemented. This stage adds embedding-based retrieval using Anthropic's Voyage embeddings (or an open-source alternative) with a local vector store.

**New files:**

| File | Purpose |
|------|---------|
| `backend/app/documents/embeddings.py` | Embedding generation and vector search logic |

**Modified files:**

| File | Change |
|------|--------|
| `backend/app/config/settings.py` | Add `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS` settings |
| `backend/app/documents/models.py` | Add `embedding: list[float] | None` to `DocumentChunk` |
| `backend/app/documents/json_provider.py` | Store embeddings in index, add `semantic_search()` method |
| `backend/app/documents/interfaces.py` | Add `semantic_search()` to abstract interface |
| `backend/app/api/documents.py` | Add `mode` query param to search endpoint (`keyword` | `semantic` | `hybrid`), default `hybrid` |
| `frontend/src/components/DocumentsPanel.tsx` | Add search mode toggle (Keyword / Semantic / Hybrid) |
| `frontend/src/config/documentsApi.ts` | Add `mode` param to `searchDocuments()` |

**`embeddings.py`** — Embedding generation and cosine similarity search:
- `generate_embedding(text: str) -> list[float]` — Calls Anthropic Voyage API (or `sentence-transformers` locally) to generate a dense vector for a text chunk
- `cosine_similarity(a, b) -> float` — Dot product of normalized vectors
- `semantic_search(query_embedding, chunk_embeddings, top_k) -> list[tuple[str, float]]` — Returns chunk_ids ranked by cosine similarity
- Embeddings generated at index time (when `index_document()` is called) and stored alongside chunks
- Query embedding generated at search time

**`json_provider.py`** changes:
- `index_document()` — After chunking text, generate embedding for each chunk and store in the `DocumentChunk.embedding` field
- `semantic_search(query, entity_type, entity_id, top_k=20)` — Generate query embedding, compute cosine similarity against all chunk embeddings for matching entities, return top-K results as `DocumentSearchResult[]`
- Existing `search()` method remains for keyword search
- New `hybrid_search()` — Runs both keyword and semantic, merges results using reciprocal rank fusion (RRF): `score = sum(1 / (k + rank))` for each result across both lists

**`documents.py`** API changes:
- `GET /api/documents/search` gains `mode: str = Query(default="hybrid", pattern="^(keyword|semantic|hybrid)$")`
- `keyword` → existing `search()` path
- `semantic` → new `semantic_search()` path
- `hybrid` → new `hybrid_search()` with RRF merging

**Frontend changes:**
- `DocumentsPanel.tsx` — Add a small toggle group (3 buttons: Keyword | Semantic | Hybrid) next to the search bar, default to Hybrid. Pass `mode` to API call.
- `documentsApi.ts` — `searchDocuments(query, entityType?, entityId?, mode?)` — adds `mode` query param

**Configuration:**
- `settings.py` — Add:
  - `EMBEDDING_PROVIDER: str = "anthropic"` (or `"local"` for sentence-transformers)
  - `EMBEDDING_MODEL: str = "voyage-3"` (Anthropic Voyage) or `"all-MiniLM-L6-v2"` (local)
  - `EMBEDDING_DIMENSIONS: int = 1024`

**Re-indexing:**
- Existing indexed documents lack embeddings. Add a one-time migration: `_ensure_embeddings()` called from `_ensure_existing_files_indexed()`. Iterates all indexed documents, generates embeddings for chunks missing them, writes updated index.

**Verify:** Search for "what drove revenue growth" on AAPL page using semantic mode → returns relevant transcript chunks about revenue even if exact keywords don't match. Hybrid mode combines both keyword hits and semantic hits.

---

### Stage 2: Frontend Polish & Validation

Small but important UX improvements to meet PRD acceptance criteria.

**Modified files:**

| File | Change |
|------|--------|
| `frontend/src/components/FileUploadDialog.tsx` | Add client-side file size validation (10MB limit) |
| `frontend/src/components/DocumentsPanel.tsx` | Highlight search terms in result excerpts |
| `frontend/src/components/DocumentsPanel.tsx` | Add delete button on documents the user uploaded |
| `frontend/src/config/documentsApi.ts` | Add `deleteDocument(fileId)` function |
| `backend/app/api/documents.py` | Add `DELETE /api/documents/{file_id}` endpoint |
| `frontend/src/styles/documents.css` | Highlight styling, delete button styling |

**File size validation (`FileUploadDialog.tsx`):**
- Before upload, check `file.size > 10 * 1024 * 1024`
- If too large, show inline error message: "File exceeds 10MB limit"
- Prevent form submission

**Search highlighting (`DocumentsPanel.tsx`):**
- After receiving search results, wrap matching query terms in `<mark>` tags within the excerpt text
- Use case-insensitive regex replacement: `text.replace(new RegExp(`(${escapedTerms})`, 'gi'), '<mark>$1</mark>')`
- Render excerpt with `dangerouslySetInnerHTML` (safe since terms come from user's own search input, and excerpts are server-generated)

**Document deletion:**
- Backend: `DELETE /api/documents/{file_id}` — removes from document index and object storage manifest. Owner check via `request.state.user`.
- Frontend: Small trash icon button on each document card in the list view. Confirmation prompt before delete. Refetch list after successful delete.
- `documentsApi.ts`: `deleteDocument(fileId: string): Promise<void>` — `DELETE /api/documents/${fileId}`

**Verify:**
- Upload a 15MB file → error shown before upload attempt
- Search "earnings revenue" → matching terms highlighted in yellow in excerpts
- Upload a document, see it listed, click delete → removed from list

---

### Stage 3: LLM Resilience & UX

Improve LLM query robustness and user experience for edge cases.

**Modified files:**

| File | Change |
|------|--------|
| `backend/app/api/documents.py` | Add timeout handling, retry logic for LLM calls |
| `backend/app/llm/anthropic_provider.py` | Catch API errors gracefully, add timeout parameter |
| `frontend/src/components/LLMQueryPanel.tsx` | Add query history, improve error messages, add cancel button |

**Backend resilience (`anthropic_provider.py` + `documents.py`):**
- Wrap `client.messages.create()` in try/except for `anthropic.APIError`, `anthropic.APITimeoutError`, `anthropic.RateLimitError`
- On rate limit: return 429 with `Retry-After` header
- On timeout: return 504 with "LLM request timed out" message
- On other API errors: return 502 with sanitized error message
- Add `timeout=60` to the `messages.create()` call

**Frontend UX (`LLMQueryPanel.tsx`):**
- **Cancel button**: Show a "Cancel" button while loading. Uses `AbortController` to cancel the axios request.
- **Query history**: Store last 5 queries in component state. Show as clickable chips below the textarea for quick re-submission.
- **Error messages**: Map HTTP status codes to user-friendly messages:
  - 503 → "LLM not configured. Set ANTHROPIC_API_KEY to enable."
  - 429 → "Too many requests. Please wait and try again."
  - 504 → "Request timed out. Try a simpler query."
  - 502 → "LLM service unavailable. Try again later."

**Verify:**
- Submit a query, click Cancel → request aborted, UI returns to ready state
- Previously submitted queries appear as chips, click one → re-submits
- If API key not set → clear 503 message with setup instructions

---

### Stage 4: Tests & Final Verification

Extend test coverage for the new functionality added in Stages 1-3.

**Modified files:**

| File | Change |
|------|--------|
| `backend/app/tests/test_documents.py` | Add semantic search tests, delete endpoint tests, search mode parameter tests |
| `backend/app/tests/test_llm.py` | Add timeout/error handling tests |

**New tests:**
- `test_search_semantic_mode` — Search with `mode=semantic` returns results
- `test_search_hybrid_mode` — Search with `mode=hybrid` merges keyword + semantic results
- `test_search_keyword_mode` — Explicit `mode=keyword` matches existing behavior
- `test_delete_document` — Upload, verify listed, delete, verify removed
- `test_delete_document_not_found` — Delete non-existent file_id → 404
- `test_llm_query_timeout` — Mocked timeout → 504 response
- `test_llm_query_rate_limited` — Mocked rate limit → 429 response
- `test_embedding_generation` — Verify embeddings stored on index
- `test_reindex_adds_embeddings` — Existing documents gain embeddings on re-index

**Final verification checklist:**

| Criteria | How to verify |
|---|---|
| Keyword search works | Search "earnings" on AAPL page → relevant transcripts returned |
| Semantic search works | Search "what drove revenue growth" → relevant chunks even without exact keyword match |
| Hybrid search works | Default mode combines keyword + semantic results |
| Search mode toggle | Click Keyword/Semantic/Hybrid buttons, results change appropriately |
| LLM query works | Ask "Summarize AAPL's latest earnings" → coherent answer with source citations |
| LLM cancel works | Start query, click Cancel → loading stops |
| LLM error handling | Unset API key → clear error message |
| Document upload | Upload .pdf/.txt → appears in list, searchable |
| File size validation | Upload >10MB file → client-side error before network request |
| Document deletion | Upload, then delete → removed from list and search |
| Search highlighting | Search terms highlighted in yellow in result excerpts |
| Query history | Previous queries shown as clickable chips |
| Auto-indexing | Restart server, existing files re-indexed on first access |
| No widget mutation | LLM queries and document operations don't affect views/widgets |
| All backend tests pass | `pytest -v` — all tests pass |
| TypeScript builds | `npx tsc --noEmit` — clean |

---

## Files Summary

### New Files (1)

| File | Purpose |
|------|---------|
| `backend/app/documents/embeddings.py` | Embedding generation, cosine similarity, semantic search utilities |

### Modified Files (13)

| File | Change |
|------|--------|
| `backend/app/config/settings.py` | Add `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS` |
| `backend/app/documents/models.py` | Add `embedding` field to `DocumentChunk` |
| `backend/app/documents/interfaces.py` | Add `semantic_search()` abstract method |
| `backend/app/documents/json_provider.py` | Store embeddings, add `semantic_search()` and `hybrid_search()`, re-index migration |
| `backend/app/api/documents.py` | Add `mode` param to search, add `DELETE` endpoint, LLM error handling |
| `backend/app/llm/anthropic_provider.py` | Timeout parameter, graceful error catching |
| `backend/app/tests/test_documents.py` | Semantic search, delete, search mode tests |
| `backend/app/tests/test_llm.py` | Timeout and error handling tests |
| `frontend/src/components/DocumentsPanel.tsx` | Search mode toggle, search highlighting, delete button |
| `frontend/src/components/FileUploadDialog.tsx` | Client-side file size validation |
| `frontend/src/components/LLMQueryPanel.tsx` | Cancel button, query history, improved error messages |
| `frontend/src/config/documentsApi.ts` | Add `mode` param, `deleteDocument()` |
| `frontend/src/styles/documents.css` | Highlight styles, search mode toggle styles, delete button styles |

---

## Key Design Decisions

1. **Hybrid search as default** — Combines keyword precision with semantic recall. Users can switch to pure keyword or semantic if they prefer. Reciprocal rank fusion (RRF) merges both result lists without needing to normalize scores.
2. **Embeddings stored in JSON index** — Follows the existing flat-file pattern. Embedding vectors are stored directly in `index.json` alongside chunks. Acceptable for the current data scale (~58 documents, ~500 chunks). For production scale, would migrate to a dedicated vector store.
3. **Embedding generation at index time** — Embeddings computed once when documents are indexed, not at query time. Only the query embedding is computed per-search. This keeps search latency low.
4. **No new npm dependencies** — Search mode toggle uses plain HTML buttons. No charting or UI library additions.
5. **Graceful LLM degradation** — If the Anthropic API key is not set, the LLM panel shows a clear configuration message. If the API is down or rate-limited, specific error messages guide the user. The rest of the platform remains fully functional.
6. **Read-only LLM** — System prompt explicitly forbids widget/view modification. LLM has no access to write APIs. Sources are populated from search results by the API layer, not by the LLM itself.
7. **Re-indexing migration** — Existing documents without embeddings are backfilled lazily on first search. No manual migration step required.
