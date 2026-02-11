from __future__ import annotations

from app.config.settings import settings
from app.views.interfaces import ViewsProvider
from app.views.json_provider import JsonViewsProvider

_provider: ViewsProvider | None = None


def get_views_provider() -> ViewsProvider:
    global _provider
    if _provider is not None:
        return _provider

    _provider = JsonViewsProvider(settings.VIEWS_DIR)
    return _provider
