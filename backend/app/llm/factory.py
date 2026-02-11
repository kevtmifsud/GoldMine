from __future__ import annotations

from app.config.settings import settings
from app.llm.interfaces import LLMProvider

_provider: LLMProvider | None = None


def get_llm_provider() -> LLMProvider:
    global _provider
    if _provider is not None:
        return _provider

    if not settings.ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY is not configured")

    from app.llm.anthropic_provider import AnthropicProvider

    _provider = AnthropicProvider()
    return _provider
