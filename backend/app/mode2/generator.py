"""WF-09: Response Generation.

Assembles context into prompt, calls Claude Sonnet, streams response.
Enforces sourcing requirements and selects format per query type.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import AsyncIterator

import anthropic
from dotenv import load_dotenv

from .cost import get_model_config, calculate_cost, emit_cost_event
from .db import get_conn
from .models import RetrievalContext, ClassifiedQuery, ChunkResult

logger = logging.getLogger(__name__)

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

# ---------------------------------------------------------------------------
# System prompt components
# ---------------------------------------------------------------------------
_ROLE_CONTEXT = """\
You are a financial research assistant for a professional investment team.
You are analyzing financial documents and data for portfolio managers and analysts.
Always maintain the precision and rigor expected of institutional financial analysis."""

_SOURCING_REQUIREMENT = """\
Every factual claim, figure, or quote in your response MUST be attributed to its source.
Cite sources inline using this format: [TICKER | DOCUMENT_TYPE | PERIOD | SECTION]
Example: [AAPL | Earnings Transcript | Q4 2024 | CFO Remarks]
If you cannot attribute a claim to a provided source, do not make the claim.
Do not use prior knowledge about companies — rely only on the provided context."""

_QA_LIBRARY_INSTRUCTION = """\
Prior validated answers to similar questions are provided below.
Reference these where relevant but do not simply repeat them.
If the prior answer conflicts with the current source documents, note the discrepancy."""

_FORMAT_INSTRUCTIONS = {
    "single_ticker_qualitative": "Provide a narrative response with inline citations. Be concise — answer directly, do not pad.",
    "single_ticker_quantitative": "Lead with the exact figure and period. Follow with one sentence of context if relevant. Citation required on the figure.",
    "cross_ticker": "Provide a structured comparison. Use consistent format per ticker (one paragraph each or a summary table followed by detail). Order tickers by relevance.",
    "screening": "Provide a ranked list of tickers matching the criteria. For each: ticker, brief evidence quote with citation, why it matches. Non-matching tickers should not appear.",
    "trend_analysis": "Describe the evolution chronologically across periods. Use citations anchored to specific periods. Conclude with a summary of direction and magnitude of change.",
}


def _build_system_prompt(
    context: RetrievalContext,
    classified: ClassifiedQuery,
) -> str:
    """Assemble the full system prompt for the generator."""
    parts = [_ROLE_CONTEXT, "", _SOURCING_REQUIREMENT, ""]

    # Response format instruction
    fmt = _FORMAT_INSTRUCTIONS.get(classified.query_type, _FORMAT_INSTRUCTIONS["single_ticker_qualitative"])
    parts.append(f"## Response Format\n{fmt}")
    parts.append("")

    # Q&A library hits
    if context.qa_library_hits:
        parts.append(f"## Prior Validated Answers\n{_QA_LIBRARY_INSTRUCTION}")
        for hit in context.qa_library_hits:
            parts.append(f"\n**Prior Q:** {hit.question}\n**Prior A:** {hit.answer}\n*(Validation: {hit.validation_type}, similarity: {hit.similarity:.2f})*")
        parts.append("")

    return "\n".join(parts)


def _build_context_block(context: RetrievalContext) -> str:
    """Format retrieved context for inclusion in the user message."""
    parts = []

    # Structured data first
    if context.structured_data:
        parts.append("## Financial Data")
        for row in context.structured_data:
            table = row.pop("_table", "unknown")
            parts.append(f"\n**{table}**")
            for k, v in row.items():
                if v is not None and k not in ("id",):
                    parts.append(f"  {k}: {v}")
        parts.append("")

    # Chunks by ticker
    if context.chunks:
        parts.append("## Source Documents")
        current_ticker = ""
        for c in context.chunks:
            if c.ticker != current_ticker:
                current_ticker = c.ticker
                parts.append(f"\n### {c.ticker}")
            parts.append(
                f"\n**[{c.ticker} | {c.document_type} | {c.fiscal_period} | {c.section_name}]**\n{c.chunk_text}"
            )

    return "\n".join(parts)


async def generate_response(
    user_message: str,
    context: RetrievalContext,
    classified: ClassifiedQuery,
    history: list[dict[str, str]] | None = None,
    rolling_summary: str | None = None,
    session_id: str | None = None,
    message_id: str | None = None,
    user_id: str | None = None,
) -> AsyncIterator[dict]:
    """Stream response tokens from Claude.

    Yields dicts with:
      {"type": "token", "content": "..."}
      {"type": "metadata", ...}
      {"type": "done"}
    """
    # Handle cache hits — return directly, no LLM call
    if context.cache_hit and context.chunks:
        cached_text = "## Screening Results (Cached)\n\n"
        for c in context.chunks:
            cached_text += f"- **{c.ticker}** ({c.fiscal_period}): {c.chunk_text[:200]}...\n"
        yield {"type": "token", "content": cached_text}
        yield {
            "type": "metadata",
            "message_id": message_id,
            "query_type": classified.query_type,
            "tickers_referenced": list({c.ticker for c in context.chunks}),
            "source_chunks": [c.model_dump() for c in context.chunks[:10]],
            "cache_hit": True,
            "cost_usd": 0.0,
        }
        yield {"type": "done"}
        return

    # Get model from config
    config = await get_model_config("response_generator")
    model = config["model"]

    # Build system prompt
    system = _build_system_prompt(context, classified)

    # Build messages
    messages = []

    # Include rolling summary if available
    if rolling_summary:
        messages.append({
            "role": "user",
            "content": f"[Session summary so far: {rolling_summary}]",
        })
        messages.append({
            "role": "assistant",
            "content": "Understood. I have the session context.",
        })

    # Include recent history (last 4 turns)
    if history:
        for turn in history[-8:]:  # 4 exchanges = 8 messages
            messages.append({"role": turn["role"], "content": turn["content"]})

    # Build the user message with context
    context_block = _build_context_block(context)
    full_message = f"{context_block}\n\n## Question\n{user_message}"
    messages.append({"role": "user", "content": full_message})

    # Stream from Claude
    api_key = os.environ.get("GOLDMINE_ANTHROPIC_API_KEY", "")
    client = anthropic.Anthropic(api_key=api_key)

    full_response = ""
    input_tokens = 0
    output_tokens = 0

    with client.messages.stream(
        model=model,
        max_tokens=2048,
        system=system,
        messages=messages,
    ) as stream:
        for event in stream:
            if hasattr(event, "type"):
                if event.type == "content_block_delta":
                    text = event.delta.text
                    full_response += text
                    yield {"type": "token", "content": text}

        # Get final usage from the stream
        final_message = stream.get_final_message()
        input_tokens = final_message.usage.input_tokens
        output_tokens = final_message.usage.output_tokens

    # Calculate and log cost
    cost = await calculate_cost(model, input_tokens, output_tokens)
    emit_cost_event(
        mode="mode_2",
        component="response_generator",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        session_id=session_id,
        message_id=message_id,
        user_id=user_id,
        query_type=classified.query_type,
        ticker_count=len(context.chunks),
    )

    # Build source chunk references for metadata
    source_refs = []
    for c in context.chunks[:20]:
        source_refs.append({
            "ticker": c.ticker,
            "document_type": c.document_type,
            "fiscal_period": c.fiscal_period,
            "section_name": c.section_name,
            "similarity": c.similarity,
        })

    # Emit metadata
    yield {
        "type": "metadata",
        "message_id": message_id,
        "query_type": classified.query_type,
        "tickers_referenced": list({c.ticker for c in context.chunks}),
        "source_chunks": source_refs,
        "classifier_model": (await get_model_config("query_classifier"))["model"],
        "generator_model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost,
        "cache_hit": False,
    }

    yield {"type": "done"}

    # Save assistant message asynchronously
    if session_id and message_id:
        try:
            async with get_conn() as conn:
                await conn.execute(
                    """INSERT INTO messages
                       (id, session_id, user_id, role, content, query_type,
                        tickers_referenced, source_chunks, classifier_model,
                        generator_model, input_tokens, output_tokens, cost_usd)
                       VALUES ($1, $2, $3, 'assistant', $4, $5, $6, $7, $8, $9, $10, $11, $12)""",
                    message_id, session_id, user_id, full_response,
                    classified.query_type,
                    list({c.ticker for c in context.chunks}),
                    json.dumps(source_refs),
                    (await get_model_config("query_classifier"))["model"],
                    model, input_tokens, output_tokens, cost,
                )
                # Update session turn count
                await conn.execute(
                    """UPDATE sessions
                       SET turn_count = turn_count + 1,
                           total_cost_usd = COALESCE(total_cost_usd, 0) + $1,
                           updated_at = NOW()
                       WHERE id = $2""",
                    cost, session_id,
                )
        except Exception:
            logger.exception("Failed to save assistant message %s", message_id)
