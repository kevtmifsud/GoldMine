from __future__ import annotations

from app.config.settings import settings
from app.documents.interfaces import DocumentIndexProvider
from app.documents.json_provider import JsonDocumentIndexProvider

_provider: DocumentIndexProvider | None = None


def get_document_provider() -> DocumentIndexProvider:
    global _provider
    if _provider is not None:
        return _provider

    _provider = JsonDocumentIndexProvider(settings.DOCUMENTS_DIR)
    return _provider
