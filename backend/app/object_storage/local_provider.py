from __future__ import annotations

import json
from pathlib import Path

from app.config.settings import settings
from app.object_storage.interfaces import ObjectStorageProvider
from app.object_storage.models import FileMetadata
from app.exceptions import DataAccessError
from app.logging_config import get_logger

logger = get_logger(__name__)


class LocalStorageProvider(ObjectStorageProvider):
    def __init__(self, storage_dir: str | None = None):
        self._storage_dir = Path(storage_dir or settings.STORAGE_DIR).resolve()
        self._manifest: list[FileMetadata] = []
        self._index: dict[str, FileMetadata] = {}
        self._load_manifest()

    def _load_manifest(self) -> None:
        manifest_path = self._storage_dir / "files_manifest.json"
        if not manifest_path.exists():
            logger.warning("manifest_missing", path=str(manifest_path))
            return
        try:
            with open(manifest_path) as f:
                data = json.load(f)
            for item in data.get("files", []):
                meta = FileMetadata(**item)
                self._manifest.append(meta)
                self._index[meta.file_id] = meta
            logger.info("manifest_loaded", file_count=len(self._manifest))
        except Exception as e:
            raise DataAccessError(f"Failed to load manifest: {e}")

    def list_files(self, file_type: str | None = None) -> list[FileMetadata]:
        if file_type:
            return [f for f in self._manifest if f.type == file_type]
        return self._manifest

    def get_metadata(self, file_id: str) -> FileMetadata | None:
        return self._index.get(file_id)

    def get_file_bytes(self, file_id: str) -> tuple[bytes, str, str] | None:
        meta = self._index.get(file_id)
        if not meta:
            return None
        file_path = self._storage_dir / meta.path
        if not file_path.exists():
            logger.error("file_not_found", file_id=file_id, path=str(file_path))
            return None
        return file_path.read_bytes(), meta.filename, meta.mime_type
