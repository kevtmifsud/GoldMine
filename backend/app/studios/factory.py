from __future__ import annotations

from app.config.settings import settings
from app.studios.interfaces import StudiosProvider
from app.studios.json_provider import JsonStudiosProvider

_provider: StudiosProvider | None = None


def get_studios_provider() -> StudiosProvider:
    global _provider
    if _provider is not None:
        return _provider

    _provider = JsonStudiosProvider(settings.STUDIOS_DIR)
    return _provider
