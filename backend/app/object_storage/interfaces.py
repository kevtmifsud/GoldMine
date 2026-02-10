from __future__ import annotations

from abc import ABC, abstractmethod

from app.object_storage.models import FileMetadata


class ObjectStorageProvider(ABC):
    @abstractmethod
    def list_files(self, file_type: str | None = None) -> list[FileMetadata]:
        """List all files, optionally filtered by type."""

    @abstractmethod
    def get_metadata(self, file_id: str) -> FileMetadata | None:
        """Get metadata for a specific file."""

    @abstractmethod
    def get_file_bytes(self, file_id: str) -> tuple[bytes, str, str] | None:
        """Return (bytes, filename, mime_type) or None if not found."""
