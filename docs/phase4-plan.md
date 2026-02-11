# GoldMine Phase 4 — Unstructured Data & LLM Integration

## Context

Phase 3 delivered saved views, analyst packs, and browse pages. Phase 4 adds document ingestion/indexing, keyword search across documents, file upload from entity pages, and LLM-powered research queries using the Anthropic Claude API. Documents are associated with entities and searchable. The LLM is read-only — it cannot modify widgets, views, or settings.

**User decisions:**
- LLM Provider: Anthropic Claude API (`anthropic` Python SDK)
- Search: Keyword search only (no vector embeddings)
- Upload: Users can upload documents via UI on entity pages

**Key patterns to follow:**
- Backend: factory+provider singletons, Pydantic models, `from __future__ import annotations`, `request.state.user`
- Frontend: functional components with hooks, BEM CSS, axios API services in `config/`
- Data: JSON flat files in `data/documents/`, files in `data/unstructured/`

---

## New Files (19)

| File | Purpose |
|------|---------|
| `backend/app/documents/__init__.py` | Package init |
| `backend/app/documents/models.py` | Pydantic models: DocumentRecord, DocumentChunk, EntityAssociation, search results |
| `backend/app/documents/interfaces.py` | Abstract DocumentIndexProvider |
| `backend/app/documents/extractor.py` | Text extraction (.txt, .csv, .pdf) + chunking utility |
| `backend/app/documents/json_provider.py` | JSON flat-file document index implementation |
| `backend/app/documents/factory.py` | Singleton factory `get_document_provider()` |
| `backend/app/llm/__init__.py` | Package init |
| `backend/app/llm/models.py` | Pydantic models: LLMQueryRequest, LLMQueryResponse, LLMSource |
| `backend/app/llm/interfaces.py` | Abstract LLMProvider |
| `backend/app/llm/anthropic_provider.py` | Anthropic SDK implementation with system prompt |
| `backend/app/llm/factory.py` | Singleton factory `get_llm_provider()` |
| `backend/app/api/documents.py` | REST router: upload, list, search, LLM query |
| `backend/app/tests/test_documents.py` | Document upload, list, search, auto-index tests |
| `backend/app/tests/test_llm.py` | LLM query tests (mocked provider) |
| `frontend/src/config/documentsApi.ts` | Typed API service for documents and LLM |
| `frontend/src/components/DocumentsPanel.tsx` | Document list, search, upload trigger |
| `frontend/src/components/LLMQueryPanel.tsx` | LLM query input + response display |
| `frontend/src/components/FileUploadDialog.tsx` | Upload modal with file picker and metadata |
| `frontend/src/styles/documents.css` | All Phase 4 component styles |

## Modified Files (10)

| File | Change |
|------|--------|
| `backend/app/config/settings.py` | Add `DOCUMENTS_DIR`, `ANTHROPIC_API_KEY`, `LLM_MODEL`, `LLM_MAX_CONTEXT_CHUNKS`, `LLM_MAX_RESPONSE_TOKENS` |
| `backend/requirements.txt` | Add `pypdf`, `anthropic` |
| `backend/app/object_storage/interfaces.py` | Add `store_file()` abstract method |
| `backend/app/object_storage/local_provider.py` | Implement `store_file()`, `_save_manifest()`, `_next_file_id()` |
| `backend/app/main.py` | Register `documents_router` |
| `backend/app/tests/conftest.py` | Reset documents + LLM providers, temp documents dir |
| `frontend/src/types/entities.ts` | Add Document/LLM interfaces |
| `frontend/src/pages/EntityPage.tsx` | Add DocumentsPanel + LLMQueryPanel below widgets |
| `frontend/src/styles/entity.css` | Spacing for new panels |
| `backend/.env.example` | Add new env vars |

---

## Stage 1: Backend Document Index Layer

**New files:** `backend/app/documents/__init__.py`, `models.py`, `interfaces.py`, `extractor.py`, `json_provider.py`, `factory.py`

**`models.py`** — Core data models:
- `EntityAssociation(entity_type, entity_id)` — links document to an entity
- `DocumentChunk(chunk_id, file_id, chunk_index, text, char_start, char_end)` — text chunk
- `DocumentRecord(file_id, filename, title, doc_type, mime_type, date, description, entities[], chunks[], indexed_at)` — full index record
- `DocumentSearchResult(file_id, filename, title, doc_type, date, description, entities[], matching_chunks[], score)` — search hit
- `DocumentListItem(file_id, filename, title, doc_type, date, description, entities[], chunk_count, indexed_at)` — list view

**`interfaces.py`** — Abstract `DocumentIndexProvider` with: `index_document()`, `get_document()`, `list_documents()`, `search()`, `remove_document()`, `is_indexed()`

**`extractor.py`** — Text extraction + chunking:
- `extract_text(file_bytes, mime_type, filename) -> str` — dispatches by mime type
- `.txt` → decode UTF-8, `.csv` → decode UTF-8, `.pdf` → use `pypdf.PdfReader`, audio → empty string
- `chunk_text(text, chunk_size=800, overlap=100) -> list[(text, start, end)]` — splits at sentence/paragraph boundaries

**`json_provider.py`** — `JsonDocumentIndexProvider`:
- Stores index in `DOCUMENTS_DIR/index.json`
- `index_document()`: chunks text, creates DocumentRecord, writes to JSON
- `search()`: tokenizes query, scores chunks by token occurrence count, boosts metadata matches 2x, returns top results sorted by score
- `list_documents()`: filters by entity_type/entity_id
- `is_indexed()`: checks if file_id exists in index

**`factory.py`** — Singleton `get_document_provider()` using `settings.DOCUMENTS_DIR`

**Modify:** `backend/app/config/settings.py` — Add:
```python
DOCUMENTS_DIR: str = "../data/documents"
ANTHROPIC_API_KEY: str = ""
LLM_MODEL: str = "claude-sonnet-4-20250514"
LLM_MAX_CONTEXT_CHUNKS: int = 15
LLM_MAX_RESPONSE_TOKENS: int = 1024
```

**Modify:** `backend/requirements.txt` — Add `pypdf` and `anthropic`

---

## Stage 2: Object Storage Upload Extension

**Modify:** `backend/app/object_storage/interfaces.py` — Add abstract method:
```python
@abstractmethod
def store_file(self, filename: str, file_bytes: bytes, metadata: FileMetadata) -> FileMetadata:
    """Store a file and update the manifest."""
```

**Modify:** `backend/app/object_storage/local_provider.py` — Add three methods:
- `_next_file_id() -> str` — scans manifest for highest FILE-NNN, returns FILE-(N+1)
- `_save_manifest()` — writes updated manifest back to `files_manifest.json`
- `store_file(filename, file_bytes, metadata)` — determines subdirectory from `metadata.type`, writes file, updates in-memory index + manifest

---

## Stage 3: Backend LLM Layer

**New files:** `backend/app/llm/__init__.py`, `models.py`, `interfaces.py`, `anthropic_provider.py`, `factory.py`

**`models.py`** — Request/response models:
- `LLMQueryRequest(query, entity_type, entity_id)`
- `LLMSource(file_id, filename, chunk_index, excerpt)` — citation reference
- `LLMQueryResponse(answer, sources[], model, token_usage)`

**`interfaces.py`** — Abstract `LLMProvider` with single method: `query(request, context, sources_context) -> LLMQueryResponse`

**`anthropic_provider.py`** — `AnthropicProvider`:
- System prompt: investment research assistant, answer from provided context only, cite sources, read-only
- Uses `anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)`
- Calls `client.messages.create()` with assembled user message
- Returns LLMQueryResponse (sources populated by API layer, not LLM)

**`factory.py`** — Singleton factory, lazy-imports AnthropicProvider (only when API key is set), raises ValueError if ANTHROPIC_API_KEY is empty

---

## Stage 4: Backend Documents API Router

**New file:** `backend/app/api/documents.py`

Router prefix: `/api/documents`, tags: `["documents"]`

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/documents/upload` | Multipart upload: file + entity_type + entity_id + title + description + date. Validates file (max 10MB, non-empty), stores via object storage, extracts text, indexes. Returns 201 with DocumentListItem |
| `GET` | `/api/documents/` | List documents (optional `entity_type`, `entity_id` filters). Auto-indexes existing files on first call |
| `GET` | `/api/documents/search` | Keyword search: `q` (required), optional `entity_type`, `entity_id`. Returns DocumentSearchResult[] |
| `POST` | `/api/documents/query` | LLM query: body `{query, entity_type, entity_id}`. Gathers entity structured data + relevant document chunks → calls LLM → returns LLMQueryResponse with citations. Returns 503 if no API key |

**Auto-indexing:** `_ensure_existing_files_indexed()` runs once on first list/search/query call. Scans object storage manifest, indexes any files not yet in the document index. Maps `tickers` field to `EntityAssociation(entity_type="stock", entity_id=ticker)`.

**LLM context assembly:**
1. Get entity structured data via `get_data_provider().get_record()`
2. Search document chunks matching the query for this entity
3. Assemble up to `LLM_MAX_CONTEXT_CHUNKS` chunks as context
4. Call LLM provider via `asyncio.to_thread()` (non-blocking)
5. Attach source references from matching chunks

---

## Stage 5: Backend Tests

**New file:** `backend/app/tests/test_documents.py` — 9 tests:
1. `test_list_documents_auto_indexes_existing` — GET /api/documents/ returns ≥14 items
2. `test_list_documents_filter_by_entity` — filter by stock/AAPL returns only AAPL docs
3. `test_search_documents` — search "earnings" returns transcript matches with chunks
4. `test_search_documents_filter_by_entity` — search "earnings" + entity filter returns only matching entity
5. `test_search_no_results` — search nonsense returns empty
6. `test_upload_document` — POST multipart upload, verify 201, verify in subsequent list
7. `test_upload_empty_file` — expect 400
8. `test_upload_no_filename` — expect 400/422
9. `test_documents_require_auth` — unauthenticated GET returns 401

**New file:** `backend/app/tests/test_llm.py` — 3 tests (mocked LLM provider):
1. `test_llm_query_returns_response` — patch provider with mock, verify 200 with answer
2. `test_llm_query_no_api_key` — expect 503
3. `test_llm_query_includes_sources` — verify sources list populated from document search

---

## Stage 6: Frontend Types + API Service

**Modify:** `frontend/src/types/entities.ts` — Append interfaces:
- `EntityAssociation`, `DocumentChunk`, `DocumentListItem`, `DocumentSearchResult`, `LLMSource`, `LLMQueryResponse`

**New file:** `frontend/src/config/documentsApi.ts` — Typed functions:
- `listDocuments(entityType?, entityId?)`, `searchDocuments(query, entityType?, entityId?)`, `uploadDocument(file, entityType, entityId, title, description, date)`, `queryLLM(query, entityType, entityId)`

---

## Stage 7: Frontend Document UI Components

**New file:** `frontend/src/components/DocumentsPanel.tsx`
- Fetches document list on mount, search bar, upload button, document cards with type badges and excerpts

**New file:** `frontend/src/components/LLMQueryPanel.tsx`
- Textarea for query input, loading spinner, response display with collapsible sources, model/token metadata

**New file:** `frontend/src/components/FileUploadDialog.tsx`
- Modal overlay, form with file input + metadata fields, upload via API

**New file:** `frontend/src/styles/documents.css`
- BEM styles for all three components

---

## Stage 8: Frontend Entity Page Integration

**Modify:** `frontend/src/pages/EntityPage.tsx` — Add DocumentsPanel + LLMQueryPanel below widgets

**Modify:** `frontend/src/styles/entity.css` — Add spacing for new panels

---

## Key Design Decisions

1. **Standalone panels, not widgets** — Documents and LLM panels are placed below the widget grid but don't participate in the views/overrides system.
2. **Auto-indexing existing files** — On first access, the documents API scans the object storage manifest and indexes any unindexed files.
3. **Backend-driven keyword search** — Simple token-based scoring in Python. No external search engine needed.
4. **LLM context assembly on backend** — Entity structured data + relevant document chunks assembled into a single prompt. Sources tracked by the API layer.
5. **`asyncio.to_thread` for LLM calls** — Keeps the async event loop unblocked during synchronous Anthropic SDK calls.
6. **Lazy LLM provider loading** — `anthropic` SDK only imported when API key is configured. App starts fine without it; LLM endpoint returns 503.
7. **Object storage write extension** — `store_file()` added to existing ABC + LocalStorageProvider. Maintains manifest integrity with auto-generated FILE-NNN IDs.
