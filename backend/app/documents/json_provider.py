from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.documents.extractor import chunk_text
from app.documents.interfaces import DocumentIndexProvider
from app.documents.models import (
    DocumentChunk,
    DocumentListItem,
    DocumentRecord,
    DocumentSearchResult,
    EntityAssociation,
)
from app.logging_config import get_logger

logger = get_logger(__name__)


class JsonDocumentIndexProvider(DocumentIndexProvider):
    def __init__(self, documents_dir: str) -> None:
        self._dir = Path(documents_dir).resolve()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._dir / "index.json"
        self._records: dict[str, DocumentRecord] = {}
        self._load_index()

    def _load_index(self) -> None:
        if not self._index_path.exists():
            return
        try:
            with open(self._index_path) as f:
                data = json.load(f)
            for item in data:
                rec = DocumentRecord(**item)
                self._records[rec.file_id] = rec
            logger.info("document_index_loaded", count=len(self._records))
        except Exception as e:
            logger.error("document_index_load_failed", error=str(e))

    def _save_index(self) -> None:
        with open(self._index_path, "w") as f:
            json.dump(
                [rec.model_dump() for rec in self._records.values()],
                f,
                indent=2,
            )

    def index_document(
        self,
        file_id: str,
        filename: str,
        title: str,
        doc_type: str,
        mime_type: str,
        date: str,
        description: str,
        entities: list[EntityAssociation],
        text: str,
    ) -> DocumentRecord:
        raw_chunks = chunk_text(text)
        chunks = [
            DocumentChunk(
                chunk_id=str(uuid.uuid4()),
                file_id=file_id,
                chunk_index=i,
                text=chunk_text_str,
                char_start=start,
                char_end=end,
            )
            for i, (chunk_text_str, start, end) in enumerate(raw_chunks)
        ]

        record = DocumentRecord(
            file_id=file_id,
            filename=filename,
            title=title,
            doc_type=doc_type,
            mime_type=mime_type,
            date=date,
            description=description,
            entities=entities,
            chunks=chunks,
            indexed_at=datetime.now(timezone.utc).isoformat(),
        )

        self._records[file_id] = record
        self._save_index()
        logger.info("document_indexed", file_id=file_id, chunks=len(chunks))
        return record

    def get_document(self, file_id: str) -> DocumentRecord | None:
        return self._records.get(file_id)

    def list_documents(
        self,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> list[DocumentListItem]:
        results: list[DocumentListItem] = []
        for rec in self._records.values():
            if entity_type or entity_id:
                match = any(
                    (entity_type is None or e.entity_type == entity_type)
                    and (entity_id is None or e.entity_id == entity_id)
                    for e in rec.entities
                )
                if not match:
                    continue
            results.append(
                DocumentListItem(
                    file_id=rec.file_id,
                    filename=rec.filename,
                    title=rec.title,
                    doc_type=rec.doc_type,
                    date=rec.date,
                    description=rec.description,
                    entities=rec.entities,
                    chunk_count=len(rec.chunks),
                    indexed_at=rec.indexed_at,
                )
            )
        return results

    def search(
        self,
        query: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> list[DocumentSearchResult]:
        tokens = _tokenize(query)
        if not tokens:
            return []

        results: list[DocumentSearchResult] = []

        for rec in self._records.values():
            # Entity filter
            if entity_type or entity_id:
                match = any(
                    (entity_type is None or e.entity_type == entity_type)
                    and (entity_id is None or e.entity_id == entity_id)
                    for e in rec.entities
                )
                if not match:
                    continue

            # Score metadata (2x boost)
            meta_text = f"{rec.title} {rec.filename} {rec.description}".lower()
            meta_score = sum(meta_text.count(t) for t in tokens) * 2.0

            # Score chunks
            matching_chunks: list[tuple[DocumentChunk, float]] = []
            for chunk in rec.chunks:
                chunk_lower = chunk.text.lower()
                chunk_score = sum(chunk_lower.count(t) for t in tokens)
                if chunk_score > 0:
                    matching_chunks.append((chunk, float(chunk_score)))

            total_score = meta_score + sum(s for _, s in matching_chunks)
            if total_score <= 0:
                continue

            # Sort matching chunks by score descending, take top 5
            matching_chunks.sort(key=lambda x: x[1], reverse=True)
            top_chunks = [c for c, _ in matching_chunks[:5]]

            results.append(
                DocumentSearchResult(
                    file_id=rec.file_id,
                    filename=rec.filename,
                    title=rec.title,
                    doc_type=rec.doc_type,
                    date=rec.date,
                    description=rec.description,
                    entities=rec.entities,
                    matching_chunks=top_chunks,
                    score=total_score,
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def remove_document(self, file_id: str) -> bool:
        if file_id not in self._records:
            return False
        del self._records[file_id]
        self._save_index()
        logger.info("document_removed", file_id=file_id)
        return True

    def is_indexed(self, file_id: str) -> bool:
        return file_id in self._records


def _tokenize(text: str) -> list[str]:
    """Tokenize a query string into lowercase words."""
    return [w for w in re.findall(r"\w+", text.lower()) if len(w) >= 2]
