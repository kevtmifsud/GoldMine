from __future__ import annotations

from fastapi import APIRouter, File, Form, Query, Request, UploadFile

from app.documents.extractor import extract_text
from app.documents.factory import get_document_provider
from app.data_access.factory import get_data_provider
from app.data_access.models import FilterParams
from app.documents.models import (
    DocumentListItem,
    DocumentSearchResult,
    EntityAssociation,
)
from app.exceptions import GoldMineError, NotFoundError
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
    doc_type: str = Form(""),
) -> DocumentListItem:
    if not file.filename:
        raise GoldMineError("Filename is required", status_code=400)

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise GoldMineError("File is empty", status_code=400)
    if len(file_bytes) > MAX_UPLOAD_SIZE:
        raise GoldMineError("File exceeds 10MB limit", status_code=400)

    # Determine doc type: use explicit value if provided, otherwise infer from mime
    mime = file.content_type or "application/octet-stream"
    if not doc_type:
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
    docs = provider.list_documents(entity_type=entity_type, entity_id=entity_id)

    # Merge transcript and SEC filing records from datasets for stock entities
    if entity_type == "stock" and entity_id:
        docs = list(docs)  # ensure mutable copy
        docs.extend(_synthesize_dataset_docs(entity_id))

    return docs


@router.get("/search")
async def search_documents(
    q: str = Query(..., min_length=1),
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    mode: str = Query(default="hybrid", pattern="^(keyword|semantic|hybrid)$"),
) -> list[DocumentSearchResult]:
    _ensure_existing_files_indexed()
    provider = get_document_provider()
    if mode == "semantic":
        return provider.semantic_search(q, entity_type=entity_type, entity_id=entity_id)
    elif mode == "hybrid":
        return provider.hybrid_search(q, entity_type=entity_type, entity_id=entity_id)
    else:
        return provider.search(q, entity_type=entity_type, entity_id=entity_id)


@router.delete("/{file_id}")
async def delete_document(file_id: str, request: Request) -> dict:
    provider = get_document_provider()
    removed = provider.remove_document(file_id)
    if not removed:
        raise NotFoundError(f"Document {file_id} not found")
    return {"deleted": True}




# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _derive_fiscal_period(date_str: str) -> tuple[str, str]:
    """Derive fiscal year and quarter from a date string (YYYY-MM-DD)."""
    try:
        parts = date_str.split("-")
        year = parts[0]
        month = int(parts[1])
        quarter = str((month - 1) // 3 + 1)
        return year, quarter
    except (IndexError, ValueError):
        return "", ""


def _synthesize_dataset_docs(symbol: str) -> list[DocumentListItem]:
    """Synthesize DocumentListItem records from transcripts_list and sec_filings datasets."""
    data_provider = get_data_provider()
    items: list[DocumentListItem] = []

    # --- Transcripts ---
    try:
        result = data_provider.query(
            "transcripts_list",
            FilterParams(page=1, page_size=1000, filters={"symbol": symbol}),
        )
        for row in result.data:
            year = str(row.get("fiscal_year", row.get("year", "")))
            quarter = str(row.get("fiscal_quarter", row.get("quarter", "")))
            report_date = str(row.get("report_date", row.get("date", "")))
            items.append(DocumentListItem(
                file_id=f"transcript-{symbol}-{year}-Q{quarter}",
                filename="",
                title=f"{symbol} Q{quarter} {year} Transcript",
                doc_type="transcript",
                date=report_date,
                description=f"Earnings call transcript for {symbol} Q{quarter} {year}",
                entities=[EntityAssociation(entity_type="stock", entity_id=symbol)],
                metadata={
                    "source": "dataset",
                    "symbol": symbol,
                    "fiscal_year": year,
                    "fiscal_quarter": quarter,
                },
            ))
    except Exception:
        logger.warning("failed_to_load_transcripts", symbol=symbol)

    # --- SEC Filings ---
    try:
        result = data_provider.query(
            "sec_filings",
            FilterParams(page=1, page_size=1000, filters={"symbol": symbol}),
        )
        for row in result.data:
            accession = str(row.get("accession_number", row.get("accessionNumber", "")))
            filing_date = str(row.get("filing_date", row.get("filingDate", "")))
            form_type = str(row.get("form_type", row.get("formType", "")))
            description = str(row.get("form_type_description", row.get("description", form_type)))
            filing_url = str(row.get("filing_url", row.get("filingUrl", "")))
            report_date = str(row.get("report_date", ""))
            fiscal_year, fiscal_quarter = _derive_fiscal_period(report_date)
            items.append(DocumentListItem(
                file_id=f"sec-{accession}",
                filename="",
                title=description,
                doc_type="sec_filing",
                date=filing_date,
                description=f"{form_type} filing for {symbol}",
                entities=[EntityAssociation(entity_type="stock", entity_id=symbol)],
                metadata={
                    "source": "dataset",
                    "filing_url": filing_url,
                    "form_type": form_type,
                    "fiscal_year": fiscal_year,
                    "fiscal_quarter": fiscal_quarter,
                },
            ))
    except Exception:
        logger.warning("failed_to_load_sec_filings", symbol=symbol)

    return items


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
