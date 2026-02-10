from __future__ import annotations

from app.config.settings import settings
from app.object_storage.interfaces import ObjectStorageProvider
from app.object_storage.local_provider import LocalStorageProvider

_provider: ObjectStorageProvider | None = None


def get_storage_provider() -> ObjectStorageProvider:
    global _provider
    if _provider is not None:
        return _provider

    if settings.STORAGE_PROVIDER == "local":
        _provider = LocalStorageProvider()
    else:
        raise ValueError(f"Unknown storage provider: {settings.STORAGE_PROVIDER}")

    return _provider
