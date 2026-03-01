from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.documents.embeddings import (
    batch_generate_embeddings,
    cosine_similarity,
    generate_embedding,
)
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
        self._ensure_embeddings()

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
        chunk_texts = [ct for ct, _, _ in raw_chunks]
        embeddings = batch_generate_embeddings(chunk_texts)

        chunks = [
            DocumentChunk(
                chunk_id=str(uuid.uuid4()),
                file_id=file_id,
                chunk_index=i,
                text=chunk_text_str,
                char_start=start,
                char_end=end,
                embedding=embeddings[i] if i < len(embeddings) else None,
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

    def semantic_search(
        self,
        query: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> list[DocumentSearchResult]:
        query_embedding = generate_embedding(query)

        # Check if the embedding is all zeros (no API key / error)
        if all(v == 0.0 for v in query_embedding):
            return []

        scored: list[tuple[DocumentRecord, list[tuple[DocumentChunk, float]], float]] = []

        for rec in self._records.values():
            if entity_type or entity_id:
                match = any(
                    (entity_type is None or e.entity_type == entity_type)
                    and (entity_id is None or e.entity_id == entity_id)
                    for e in rec.entities
                )
                if not match:
                    continue

            chunk_scores: list[tuple[DocumentChunk, float]] = []
            for chunk in rec.chunks:
                if not chunk.embedding or all(v == 0.0 for v in chunk.embedding):
                    continue
                sim = cosine_similarity(query_embedding, chunk.embedding)
                if sim > 0.0:
                    chunk_scores.append((chunk, sim))

            if not chunk_scores:
                continue

            chunk_scores.sort(key=lambda x: x[1], reverse=True)
            top_score = max(s for _, s in chunk_scores)
            scored.append((rec, chunk_scores, top_score))

        scored.sort(key=lambda x: x[2], reverse=True)

        results: list[DocumentSearchResult] = []
        for rec, chunk_scores, top_score in scored:
            top_chunks = [c for c, _ in chunk_scores[:5]]
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
                    score=top_score,
                )
            )

        return results

    def hybrid_search(
        self,
        query: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> list[DocumentSearchResult]:
        keyword_results = self.search(query, entity_type=entity_type, entity_id=entity_id)
        semantic_results = self.semantic_search(query, entity_type=entity_type, entity_id=entity_id)

        # Reciprocal Rank Fusion
        rrf_scores: dict[str, float] = {}
        rrf_results: dict[str, DocumentSearchResult] = {}
        k = 60

        for rank, result in enumerate(keyword_results):
            rrf_scores[result.file_id] = rrf_scores.get(result.file_id, 0.0) + 1.0 / (k + rank)
            rrf_results[result.file_id] = result

        for rank, result in enumerate(semantic_results):
            rrf_scores[result.file_id] = rrf_scores.get(result.file_id, 0.0) + 1.0 / (k + rank)
            # Prefer semantic result's chunks if not already present
            if result.file_id not in rrf_results:
                rrf_results[result.file_id] = result

        merged = [
            DocumentSearchResult(
                file_id=r.file_id,
                filename=r.filename,
                title=r.title,
                doc_type=r.doc_type,
                date=r.date,
                description=r.description,
                entities=r.entities,
                matching_chunks=r.matching_chunks,
                score=rrf_scores[r.file_id],
            )
            for r in rrf_results.values()
        ]
        merged.sort(key=lambda r: r.score, reverse=True)
        return merged

    def _ensure_embeddings(self) -> None:
        """Backfill embeddings for chunks that are missing them."""
        needs_save = False
        for rec in self._records.values():
            missing = [c for c in rec.chunks if not c.embedding]
            if not missing:
                continue
            texts = [c.text for c in missing]
            embeddings = batch_generate_embeddings(texts)
            for chunk, emb in zip(missing, embeddings):
                chunk.embedding = emb
            needs_save = True

        if needs_save:
            self._save_index()
            logger.info("embeddings_backfilled")

    def is_indexed(self, file_id: str) -> bool:
        return file_id in self._records


def _tokenize(text: str) -> list[str]:
    """Tokenize a query string into lowercase words."""
    return [w for w in re.findall(r"\w+", text.lower()) if len(w) >= 2]
