from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, File, Form, Query, Request, UploadFile

from app.config.settings import settings
from app.data_access.factory import get_data_provider
from app.documents.extractor import extract_text
from app.documents.factory import get_document_provider
from app.documents.models import (
    DocumentListItem,
    DocumentSearchResult,
    EntityAssociation,
)
from app.exceptions import GoldMineError, NotFoundError
from app.llm.models import LLMQueryRequest, LLMQueryResponse, LLMSource
from app.logging_config import get_logger
from app.object_storage.factory import get_storage_provider
from app.object_storage.models import FileMetadata

logger = get_logger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])

_indexed_existing = False

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB


# ---------------------------------------------------------------------------
# Auto-indexing
# ---------------------------------------------------------------------------

def _ensure_existing_files_indexed() -> None:
    global _indexed_existing
    if _indexed_existing:
        return
    _indexed_existing = True

    storage = get_storage_provider()
    doc_provider = get_document_provider()
    all_files = storage.list_files()

    indexed_count = 0
    for meta in all_files:
        if doc_provider.is_indexed(meta.file_id):
            continue

        # Build entity associations from tickers
        entities = [
            EntityAssociation(entity_type="stock", entity_id=ticker)
            for ticker in meta.tickers
        ]

        # Try to extract text
        result = storage.get_file_bytes(meta.file_id)
        text = ""
        if result:
            file_bytes, filename, mime_type = result
            text = extract_text(file_bytes, mime_type, filename)

        doc_provider.index_document(
            file_id=meta.file_id,
            filename=meta.filename,
            title=meta.description or meta.filename,
            doc_type=meta.type,
            mime_type=meta.mime_type,
            date=meta.date,
            description=meta.description,
            entities=entities,
            text=text,
        )
        indexed_count += 1

    if indexed_count > 0:
        logger.info("auto_indexed_existing_files", count=indexed_count)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/upload", status_code=201)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    entity_type: str = Form(...),
    entity_id: str = Form(...),
    title: str = Form(""),
    description: str = Form(""),
    date: str = Form(""),
) -> DocumentListItem:
    if not file.filename:
        raise GoldMineError("Filename is required", status_code=400)

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise GoldMineError("File is empty", status_code=400)
    if len(file_bytes) > MAX_UPLOAD_SIZE:
        raise GoldMineError("File exceeds 10MB limit", status_code=400)

    # Determine doc type from mime
    mime = file.content_type or "application/octet-stream"
    doc_type = _mime_to_doc_type(mime, file.filename)

    # Store file via object storage
    storage = get_storage_provider()
    file_id = storage._next_file_id()  # type: ignore[attr-defined]

    tickers = [entity_id] if entity_type == "stock" else []
    file_meta = FileMetadata(
        file_id=file_id,
        filename=file.filename,
        path="",
        type=doc_type,
        mime_type=mime,
        size_bytes=len(file_bytes),
        tickers=tickers,
        date=date,
        description=description or title,
    )
    storage.store_file(file.filename, file_bytes, file_meta)

    # Extract and index
    text = extract_text(file_bytes, mime, file.filename)
    entities = [EntityAssociation(entity_type=entity_type, entity_id=entity_id)]

    doc_provider = get_document_provider()
    record = doc_provider.index_document(
        file_id=file_id,
        filename=file.filename,
        title=title or file.filename,
        doc_type=doc_type,
        mime_type=mime,
        date=date,
        description=description,
        entities=entities,
        text=text,
    )

    return DocumentListItem(
        file_id=record.file_id,
        filename=record.filename,
        title=record.title,
        doc_type=record.doc_type,
        date=record.date,
        description=record.description,
        entities=record.entities,
        chunk_count=len(record.chunks),
        indexed_at=record.indexed_at,
    )


@router.get("/")
async def list_documents(
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
) -> list[DocumentListItem]:
    _ensure_existing_files_indexed()
    provider = get_document_provider()
    return provider.list_documents(entity_type=entity_type, entity_id=entity_id)


@router.get("/search")
async def search_documents(
    q: str = Query(..., min_length=1),
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
) -> list[DocumentSearchResult]:
    _ensure_existing_files_indexed()
    provider = get_document_provider()
    return provider.search(q, entity_type=entity_type, entity_id=entity_id)


@router.post("/query")
async def llm_query(request: Request, body: LLMQueryRequest) -> LLMQueryResponse:
    _ensure_existing_files_indexed()

    if not settings.ANTHROPIC_API_KEY:
        raise GoldMineError("LLM not configured", status_code=503)

    # 1. Get entity structured data
    context = _get_entity_context(body.entity_type, body.entity_id)

    # 2. Search document chunks
    doc_provider = get_document_provider()
    search_results = doc_provider.search(
        body.query,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
    )

    # 3. Assemble document context (up to max chunks)
    sources_parts: list[str] = []
    source_refs: list[LLMSource] = []
    chunk_count = 0
    for result in search_results:
        for chunk in result.matching_chunks:
            if chunk_count >= settings.LLM_MAX_CONTEXT_CHUNKS:
                break
            sources_parts.append(
                f"[{result.filename}, chunk {chunk.chunk_index}]\n{chunk.text}"
            )
            source_refs.append(
                LLMSource(
                    file_id=result.file_id,
                    filename=result.filename,
                    chunk_index=chunk.chunk_index,
                    excerpt=chunk.text[:200],
                )
            )
            chunk_count += 1
        if chunk_count >= settings.LLM_MAX_CONTEXT_CHUNKS:
            break

    sources_context = "\n\n".join(sources_parts) if sources_parts else "(No relevant documents found)"

    # 4. Call LLM via thread pool
    from app.llm.factory import get_llm_provider

    llm = get_llm_provider()
    response = await asyncio.to_thread(llm.query, body, context, sources_context)

    # 5. Attach source references
    response.sources = source_refs
    return response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_entity_context(entity_type: str, entity_id: str) -> str:
    """Build structured data context string for an entity."""
    provider = get_data_provider()

    if entity_type == "stock":
        record = provider.get_record("stocks", entity_id)
        if record:
            lines = [f"{k}: {v}" for k, v in record.items()]
            return "\n".join(lines)

    elif entity_type == "person":
        record = provider.get_record("people", entity_id)
        if record:
            lines = [f"{k}: {v}" for k, v in record.items()]
            return "\n".join(lines)

    elif entity_type == "dataset":
        datasets = provider.list_datasets()
        for ds in datasets:
            if ds.name == entity_id:
                return (
                    f"Dataset: {ds.display_name}\n"
                    f"Description: {ds.description}\n"
                    f"Records: {ds.record_count}\n"
                    f"Category: {ds.category}"
                )

    return "(No structured data available)"


def _mime_to_doc_type(mime: str, filename: str) -> str:
    """Map mime type to document type category."""
    lower = mime.lower()
    name_lower = filename.lower()

    if "pdf" in lower or name_lower.endswith(".pdf"):
        return "report"
    if "csv" in lower or name_lower.endswith(".csv"):
        return "data_export"
    if "audio" in lower or name_lower.endswith((".mp3", ".wav", ".m4a")):
        return "audio"
    if "text" in lower or name_lower.endswith(".txt"):
        return "transcript"
    return "report"
