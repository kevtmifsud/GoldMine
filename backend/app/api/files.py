from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.exceptions import NotFoundError
from app.object_storage.factory import get_storage_provider
from app.object_storage.models import FileMetadata

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("/")
async def list_files(file_type: str | None = Query(default=None)) -> list[FileMetadata]:
    provider = get_storage_provider()
    return provider.list_files(file_type=file_type)


@router.get("/{file_id}/metadata")
async def get_file_metadata(file_id: str) -> FileMetadata:
    provider = get_storage_provider()
    meta = provider.get_metadata(file_id)
    if meta is None:
        raise NotFoundError(f"File '{file_id}' not found")
    return meta


@router.get("/{file_id}")
async def get_file(file_id: str) -> Response:
    provider = get_storage_provider()
    result = provider.get_file_bytes(file_id)
    if result is None:
        raise NotFoundError(f"File '{file_id}' not found")
    content, filename, mime_type = result
    return Response(
        content=content,
        media_type=mime_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
