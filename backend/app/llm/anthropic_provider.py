from __future__ import annotations

from app.config.settings import settings
from app.llm.interfaces import LLMProvider
from app.llm.models import LLMQueryRequest, LLMQueryResponse
from app.logging_config import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """\
You are an investment research assistant for the GoldMine platform. \
Your role is to answer questions about companies, stocks, people, and financial data \
based ONLY on the provided context documents and structured data.

Rules:
- Answer using only the information provided in the context below.
- If the context does not contain enough information to answer, say so clearly.
- Cite specific documents when referencing information.
- You are read-only: you cannot modify any widgets, views, settings, or data.
- Be concise and factual.
"""


class AnthropicProvider(LLMProvider):
    def __init__(self) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        logger.info("anthropic_provider_init", model=settings.LLM_MODEL)

    def query(
        self,
        request: LLMQueryRequest,
        context: str,
        sources_context: str,
    ) -> LLMQueryResponse:
        user_message = (
            f"Entity: {request.entity_type} / {request.entity_id}\n\n"
            f"--- Structured Data ---\n{context}\n\n"
            f"--- Document Excerpts ---\n{sources_context}\n\n"
            f"--- Question ---\n{request.query}"
        )

        response = self._client.messages.create(
            model=settings.LLM_MODEL,
            max_tokens=settings.LLM_MAX_RESPONSE_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        answer = ""
        for block in response.content:
            if block.type == "text":
                answer += block.text

        token_usage = {}
        if response.usage:
            token_usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }

        return LLMQueryResponse(
            answer=answer,
            sources=[],  # Populated by the API layer
            model=response.model,
            token_usage=token_usage,
        )
