from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, File, Form, Query, Request, UploadFile

from app.config.settings import settings
from app.data_access.factory import get_data_provider
from app.documents.extractor import extract_text
from app.documents.factory import get_document_provider
from app.data_access.models import FilterParams
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


@router.post("/query")
async def llm_query(request: Request, body: LLMQueryRequest) -> LLMQueryResponse:
    _ensure_existing_files_indexed()

    if not settings.ANTHROPIC_API_KEY:
        raise GoldMineError("LLM not configured", status_code=503)

    source_refs: list[LLMSource] = []

    if body.is_first_message:
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
    else:
        # Follow-up messages: skip context and document search
        context = ""
        sources_context = ""

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


_STOCK_RELATED_DATASETS: list[tuple[str, str, str, int]] = [
    # (dataset_name, filter_field, section_label, max_rows)
    ("portfolio_trades", "ticker", "Portfolio Trades", 200),
    ("sec_filings", "symbol", "SEC Filings", 50),
    ("transcripts_list", "symbol", "Earnings Transcripts", 50),
]


def _build_portfolio_summaries(provider: Any) -> str:
    """Build a concise summary of all portfolios: tickers, trade counts, date ranges."""
    all_rows: list[dict[str, Any]] = []
    page = 1
    while True:
        try:
            result = provider.query(
                "portfolio_trades",
                FilterParams(page=page, page_size=1000),
            )
            if not result.data:
                break
            all_rows.extend(result.data)
            if len(all_rows) >= result.total_records:
                break
            page += 1
        except Exception:
            break

    if not all_rows:
        return ""

    # Group by portfolio → ticker → stats
    portfolios: dict[str, dict[str, dict[str, Any]]] = {}
    for row in all_rows:
        port = row.get("portfolio", "")
        ticker = row.get("ticker", "")
        if not port or not ticker:
            continue
        if port not in portfolios:
            portfolios[port] = {}
        if ticker not in portfolios[port]:
            portfolios[port][ticker] = {
                "trades": 0,
                "total_shares": 0,
                "side": row.get("side", ""),
                "first_date": row.get("date", ""),
                "last_date": row.get("date", ""),
            }
        entry = portfolios[port][ticker]
        entry["trades"] += 1
        entry["total_shares"] += int(float(row.get("shares", 0)))
        date = row.get("date", "")
        if date < entry["first_date"]:
            entry["first_date"] = date
        if date > entry["last_date"]:
            entry["last_date"] = date

    if not portfolios:
        return ""

    lines: list[str] = []
    for port_name in sorted(portfolios):
        tickers = portfolios[port_name]
        # Sort by trade count descending
        sorted_tickers = sorted(tickers.items(), key=lambda x: x[1]["trades"], reverse=True)
        lines.append(f"Portfolio: {port_name} ({len(sorted_tickers)} tickers, {sum(t['trades'] for t in tickers.values())} total trades)")
        for tk, stats in sorted_tickers:
            lines.append(
                f"  {tk}: {stats['trades']} trades, {stats['total_shares']:,} shares, "
                f"{stats['side']}, {stats['first_date']} to {stats['last_date']}"
            )

    return "--- Portfolio Composition (All Portfolios) ---\n" + "\n".join(lines)


def _get_entity_context(entity_type: str, entity_id: str) -> str:
    """Build structured data context string for an entity.

    Always includes a portfolio composition summary so the LLM can
    answer cross-entity questions regardless of which page the user
    is on.
    """
    provider = get_data_provider()
    parts: list[str] = []

    if entity_type == "stock":
        record = provider.get_record("stocks", entity_id)
        if record:
            lines = [f"{k}: {v}" for k, v in record.items()]
            parts.append("--- Stock Info ---\n" + "\n".join(lines))

        for dataset_name, filter_field, label, max_rows in _STOCK_RELATED_DATASETS:
            try:
                result = provider.query(
                    dataset_name,
                    FilterParams(
                        page=1,
                        page_size=max_rows,
                        filters={filter_field: entity_id},
                    ),
                )
                if result.data:
                    rows_text = "\n".join(
                        ", ".join(f"{k}: {v}" for k, v in row.items())
                        for row in result.data
                    )
                    parts.append(
                        f"--- {label} ({result.total_records} total) ---\n{rows_text}"
                    )
            except Exception:
                logger.warning("failed_to_load_related_dataset", dataset=dataset_name, entity_id=entity_id)

    elif entity_type == "person":
        record = provider.get_record("people", entity_id)
        if record:
            lines = [f"{k}: {v}" for k, v in record.items()]
            parts.append("\n".join(lines))

    elif entity_type == "dataset":
        datasets = provider.list_datasets()
        for ds in datasets:
            if ds.name == entity_id:
                parts.append(
                    f"Dataset: {ds.display_name}\n"
                    f"Description: {ds.description}\n"
                    f"Records: {ds.record_count}\n"
                    f"Category: {ds.category}"
                )
                break

    elif entity_type == "sector":
        try:
            result = provider.query(
                "stocks",
                FilterParams(page=1, page_size=200, filters={"sector": entity_id}),
            )
            if result.data:
                _SECTOR_FIELDS = (
                    "ticker", "company_name", "industry", "market_cap_b",
                    "pe_ratio", "price", "52w_high", "52w_low",
                    "dividend_yield", "eps", "revenue_b",
                )
                rows_text = "\n".join(
                    ", ".join(
                        f"{k}: {v}" for k, v in row.items() if k in _SECTOR_FIELDS
                    )
                    for row in result.data
                )
                parts.append(
                    f"--- {entity_id} Sector Stocks ({result.total_records} total) ---\n{rows_text}"
                )
        except Exception:
            logger.warning("failed_to_load_sector_stocks", entity_id=entity_id)

    elif entity_type == "industry":
        try:
            result = provider.query(
                "stocks",
                FilterParams(page=1, page_size=200, filters={"industry": entity_id}),
            )
            if result.data:
                _INDUSTRY_FIELDS = (
                    "ticker", "company_name", "sector", "market_cap_b",
                    "pe_ratio", "price", "52w_high", "52w_low",
                    "dividend_yield", "eps", "revenue_b",
                )
                rows_text = "\n".join(
                    ", ".join(
                        f"{k}: {v}" for k, v in row.items() if k in _INDUSTRY_FIELDS
                    )
                    for row in result.data
                )
                parts.append(
                    f"--- {entity_id} Industry Stocks ({result.total_records} total) ---\n{rows_text}"
                )
        except Exception:
            logger.warning("failed_to_load_industry_stocks", entity_id=entity_id)

    elif entity_type == "portfolio":
        try:
            result = provider.query(
                "portfolio_trades",
                FilterParams(
                    page=1,
                    page_size=500,
                    filters={"portfolio": entity_id},
                ),
            )
            if result.data:
                rows_text = "\n".join(
                    ", ".join(f"{k}: {v}" for k, v in row.items())
                    for row in result.data
                )
                parts.append(
                    f"--- {entity_id} Trades ({result.total_records} total) ---\n{rows_text}"
                )
        except Exception:
            logger.warning("failed_to_load_portfolio_trades", entity_id=entity_id)

    # Always include portfolio composition so the LLM can answer
    # cross-entity questions from any page
    portfolio_summary = _build_portfolio_summaries(provider)
    if portfolio_summary:
        parts.append(portfolio_summary)

    return "\n\n".join(parts) if parts else "(No structured data available)"


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
