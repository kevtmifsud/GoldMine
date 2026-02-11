from __future__ import annotations

from abc import ABC, abstractmethod

from app.documents.models import (
    DocumentListItem,
    DocumentRecord,
    DocumentSearchResult,
    EntityAssociation,
)


class DocumentIndexProvider(ABC):
    @abstractmethod
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
        """Index a document with extracted text."""

    @abstractmethod
    def get_document(self, file_id: str) -> DocumentRecord | None:
        """Get a single document record by file_id."""

    @abstractmethod
    def list_documents(
        self,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> list[DocumentListItem]:
        """List documents, optionally filtered by entity."""

    @abstractmethod
    def search(
        self,
        query: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> list[DocumentSearchResult]:
        """Search documents by keyword query."""

    @abstractmethod
    def remove_document(self, file_id: str) -> bool:
        """Remove a document from the index. Returns True if found."""

    @abstractmethod
    def is_indexed(self, file_id: str) -> bool:
        """Check if a file_id is already indexed."""
