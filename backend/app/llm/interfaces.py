from __future__ import annotations

from abc import ABC, abstractmethod

from app.llm.models import LLMQueryRequest, LLMQueryResponse


class LLMProvider(ABC):
    @abstractmethod
    def query(
        self,
        request: LLMQueryRequest,
        context: str,
        sources_context: str,
    ) -> LLMQueryResponse:
        """Send a query to the LLM with assembled context."""
