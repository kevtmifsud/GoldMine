"""WF-09: Response Generation (Agentic Tool-Calling).

Claude receives the user question + tool definitions, calls tools as needed,
gets results back, calls more if needed, then streams the final answer.
Preserves SSE streaming, cost tracking, and message persistence.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import AsyncIterator

import anthropic
from dotenv import load_dotenv

from .cost import get_model_config, calculate_cost, emit_cost_event
from .db import get_conn
from .models import ClassifiedQuery, ResolvedUniverse
from .retrieval import _embed_query, _lookup_qa_library
from .steps import StepCollector
from .tools import GOLDMINE_TOOLS, execute_tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Friendly error messages — never expose raw errors to users
# ---------------------------------------------------------------------------

def _friendly_api_error(exc: Exception) -> tuple[str, bool, int]:
    """Map an Anthropic API error to (user_message, should_retry, max_retries).

    Returns a user-facing message, whether to retry, and how many times.
    """
    if isinstance(exc, anthropic.APIStatusError):
        status = exc.status_code
        if status == 529:
            return (
                "The AI service is experiencing high demand right now. "
                "Retrying automatically...",
                True, 3,
            )
        elif status == 429:
            return (
                "You've reached the API rate limit. "
                "Please wait a moment before asking another question.",
                False, 0,
            )
        elif status in (500, 502, 503):
            return (
                "The AI service is temporarily unavailable. "
                "Please try again in a few seconds.",
                True, 1,
            )
        elif status == 401:
            return (
                "There is a configuration issue with the AI service. "
                "Please contact your administrator.",
                False, 0,
            )
        elif status == 400:
            return (
                "Your question could not be processed. "
                "This may be due to message length. "
                "Try breaking it into a smaller question.",
                False, 0,
            )
    if isinstance(exc, anthropic.APIConnectionError):
        return (
            "Could not connect to the AI service. "
            "Please check your network and try again.",
            True, 1,
        )
    return (
        "Something went wrong processing your request. Please try again.",
        False, 0,
    )

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))


def _serialize_content_blocks(content_blocks: list) -> list[dict]:
    """Convert Anthropic SDK content blocks to plain dicts for safe re-serialization.

    The Anthropic SDK returns Pydantic model objects (TextBlock, ToolUseBlock)
    in response.content. When these are passed back into messages for the next
    API call, Pydantic V2 internal serialization can fail with:
        'by_alias': 'NoneType' object cannot be converted to 'PyBool'

    This converts them to plain dicts and strips None values to avoid the issue.
    """
    result = []
    for block in content_blocks:
        if hasattr(block, "model_dump"):
            d = block.model_dump(exclude_none=True)
        elif isinstance(block, dict):
            d = {k: v for k, v in block.items() if v is not None}
        else:
            d = {"type": "text", "text": str(block)}
        result.append(d)
    return result

# ---------------------------------------------------------------------------
# System prompt — loaded from markdown file at import time
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT_PATH = Path(__file__).resolve().parents[3] / "instructions" / "domain" / "WF-09_system_prompt.md"
_SYSTEM_PROMPT: str = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def _build_qa_context(qa_hits: list) -> str:
    """Format Q&A library hits for inclusion in the system prompt."""
    if not qa_hits:
        return ""
    parts = [
        "\n\n## Prior Validated Answers\n"
        "Prior validated answers to similar questions are provided below. "
        "Reference these where relevant but do not simply repeat them. "
        "If the prior answer conflicts with tool results, note the discrepancy."
    ]
    for hit in qa_hits:
        parts.append(
            f"\n**Prior Q:** {hit.question}\n"
            f"**Prior A:** {hit.answer}\n"
            f"*(Validation: {hit.validation_type}, similarity: {hit.similarity:.2f})*"
        )
    return "\n".join(parts)


async def generate_response(
    user_message: str,
    classified: ClassifiedQuery,
    universe: ResolvedUniverse,
    history: list[dict[str, str]] | None = None,
    rolling_summary: str | None = None,
    session_id: str | None = None,
    message_id: str | None = None,
    user_id: str | None = None,
    steps: StepCollector | None = None,
) -> AsyncIterator[dict]:
    """Agentic tool-calling loop that streams the final response.

    Yields dicts with:
      {"type": "step", ...}          — pipeline transparency events
      {"type": "cost_warning", ...}  — cost warning before large queries
      {"type": "token", "content": "..."}
      {"type": "metadata", ...}
      {"type": "done"}
    """
    # ------------------------------------------------------------------
    # 1. Embed the user query once
    # ------------------------------------------------------------------
    query_embedding = await _embed_query(
        user_message,
        session_id=session_id,
        message_id=message_id,
        user_id=user_id,
        steps=steps,
    )

    # Emit embedding step
    if steps:
        for step in steps.drain():
            yield step

    # ------------------------------------------------------------------
    # 2. Q&A library lookup (runs on every query)
    # ------------------------------------------------------------------
    qa_hits = await _lookup_qa_library(query_embedding, steps=steps)

    # Emit Q&A step
    if steps:
        for step in steps.drain():
            yield step

    # ------------------------------------------------------------------
    # 3. Build system prompt and messages
    # ------------------------------------------------------------------
    config = await get_model_config("response_generator")
    model = config["model"]

    system = _SYSTEM_PROMPT + _build_qa_context(qa_hits)

    messages: list[dict] = []

    # Rolling summary
    if rolling_summary:
        messages.append({
            "role": "user",
            "content": (
                f"[Previous session context — for topic continuity only. "
                f"Data availability and figures may have changed. "
                f"Always query tools for current values: {rolling_summary}]"
            ),
        })
        messages.append({
            "role": "assistant",
            "content": "Understood. I have the session context.",
        })

    # Recent history (last 4 turns = 8 messages)
    if history:
        for turn in history[-8:]:
            messages.append({"role": turn["role"], "content": turn["content"]})

    # User message with ticker context
    ticker_ctx = ""
    if universe.tickers:
        ticker_ctx = f"\n\nResolved tickers: {', '.join(universe.tickers)}"
    messages.append({
        "role": "user",
        "content": f"{user_message}{ticker_ctx}",
    })

    # ------------------------------------------------------------------
    # 4–6. Agentic tool-calling loop
    # ------------------------------------------------------------------
    api_key = os.environ.get("GOLDMINE_ANTHROPIC_API_KEY", "")
    client = anthropic.Anthropic(api_key=api_key)

    total_input_tokens = 0
    total_output_tokens = 0
    all_tool_names_used: list[str] = []
    cost_warning_emitted = False
    tool_loop_iteration = 0
    max_tool_loops = 10  # safety limit

    while tool_loop_iteration < max_tool_loops:
        tool_loop_iteration += 1

        # Call Claude with retry logic for transient errors
        response = None
        for attempt in range(4):  # attempt 0 = first try, 1-3 = retries
            try:
                response = client.messages.create(
                    model=model,
                    max_tokens=4096,
                    system=system,
                    messages=messages,
                    tools=GOLDMINE_TOOLS,
                )
                break  # Success — exit retry loop
            except (anthropic.APIError, anthropic.APIConnectionError) as api_err:
                user_msg, should_retry, max_retries = _friendly_api_error(api_err)
                logger.error("anthropic_api_error",
                             status=getattr(api_err, "status_code", None),
                             error=str(api_err), attempt=attempt)

                if should_retry and attempt < max_retries:
                    wait_seconds = 2 ** (attempt + 1)  # 2, 4, 8
                    if steps:
                        steps.add(
                            label=f"High demand — retrying ({attempt + 1}/{max_retries})...",
                            detail=f"Waiting {wait_seconds}s",
                            source="anthropic",
                            duration_ms=wait_seconds * 1000,
                        )
                        for step in steps.drain():
                            yield step
                    await asyncio.sleep(wait_seconds)
                    continue

                # No more retries — emit friendly error and stop
                if should_retry:
                    user_msg = (
                        "The AI service is currently overloaded. "
                        "Please try your question again in a moment."
                    )
                yield {
                    "type": "error",
                    "user_message": user_msg,
                    "retrying": False,
                    "retry_attempt": attempt,
                }
                yield {"type": "done"}
                return

        if response is None:
            yield {
                "type": "error",
                "user_message": "Something went wrong processing your request. Please try again.",
                "retrying": False,
            }
            yield {"type": "done"}
            return

        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens

        # Check if Claude wants to use tools
        if response.stop_reason == "tool_use":
            # Collect all tool_use blocks from the response
            tool_use_blocks = [
                block for block in response.content
                if block.type == "tool_use"
            ]

            # Cost warning: before first tool execution, if high ticker count
            # and search_documents is among the tools
            if (
                not cost_warning_emitted
                and classified.estimated_ticker_count >= 10
                and any(b.name == "search_documents" for b in tool_use_blocks)
            ):
                cost_warning_emitted = True
                yield {
                    "type": "cost_warning",
                    "ticker_count": classified.estimated_ticker_count,
                    "message": (
                        f"This query spans ~{classified.estimated_ticker_count} tickers "
                        f"and includes document search. This may be a larger query. Proceeding."
                    ),
                }

            # Emit step for tool calls
            tool_names = [b.name for b in tool_use_blocks]
            all_tool_names_used.extend(tool_names)
            if steps:
                steps.add(
                    label=f"Calling tools: {', '.join(tool_names)}",
                    detail=f"Iteration {tool_loop_iteration}",
                    source="tools",
                    result_summary=f"{len(tool_use_blocks)} tool calls",
                )
                for step in steps.drain():
                    yield step

            # Add the assistant message (with tool_use blocks) to conversation
            # Convert SDK Pydantic objects to plain dicts to avoid serialization errors
            messages.append({"role": "assistant", "content": _serialize_content_blocks(response.content)})

            # Execute tools and build tool_result blocks
            tool_results = []
            for block in tool_use_blocks:
                result_str = await execute_tool(
                    tool_name=block.name,
                    tool_input=block.input,
                    classified=classified,
                    query_embedding=query_embedding,
                    steps=steps,
                )

                # If tool returned an error, annotate the result for Claude
                # so it works around missing data gracefully
                try:
                    parsed = json.loads(result_str)
                    if isinstance(parsed, dict) and parsed.get("error") is True:
                        tool_label = parsed.get("tool_name", block.name)
                        result_str = json.dumps({
                            "error": True,
                            "note": (
                                f"The {tool_label} data was unavailable. "
                                "Base your response only on successfully retrieved data. "
                                "Do not mention specific technical errors."
                            ),
                        })
                except (json.JSONDecodeError, TypeError):
                    pass

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_str,
                })

            # Emit retrieval steps
            if steps:
                for step in steps.drain():
                    yield step

            # Add tool results to conversation
            messages.append({"role": "user", "content": tool_results})

        else:
            # Claude returned a final response — break out of loop
            break

    # ------------------------------------------------------------------
    # 7. Stream the final text response
    # ------------------------------------------------------------------
    # Extract text from the final response content blocks
    full_response = ""
    for block in response.content:
        if hasattr(block, "text"):
            full_response += block.text

    # Stream the response token-by-token to preserve SSE behavior
    # Since we already have the full text from the non-streaming final call,
    # we emit it in chunks to maintain the streaming UX
    chunk_size = 20  # characters per token event
    for i in range(0, len(full_response), chunk_size):
        yield {"type": "token", "content": full_response[i:i + chunk_size]}

    # ------------------------------------------------------------------
    # 8. Calculate cost and emit metadata
    # ------------------------------------------------------------------
    total_cost = await calculate_cost(model, total_input_tokens, total_output_tokens)
    emit_cost_event(
        mode="mode_2",
        component="response_generator",
        model=model,
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
        cost_usd=total_cost,
        session_id=session_id,
        message_id=message_id,
        user_id=user_id,
        query_type=classified.query_type,
        ticker_count=classified.estimated_ticker_count,
    )

    yield {
        "type": "metadata",
        "message_id": message_id,
        "query_type": classified.query_type,
        "tickers_referenced": universe.tickers,
        "tools_used": list(set(all_tool_names_used)),
        "classifier_model": (await get_model_config("query_classifier"))["model"],
        "generator_model": model,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "cost_usd": total_cost,
        "tool_loop_iterations": tool_loop_iteration,
        "cache_hit": False,
    }

    yield {"type": "done"}

    # ------------------------------------------------------------------
    # 9. Persist message to Supabase asynchronously
    # ------------------------------------------------------------------
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
                    universe.tickers,
                    json.dumps(list(set(all_tool_names_used))),
                    (await get_model_config("query_classifier"))["model"],
                    model, total_input_tokens, total_output_tokens, total_cost,
                )
                # Update session turn count
                await conn.execute(
                    """UPDATE sessions
                       SET turn_count = turn_count + 1,
                           total_cost_usd = COALESCE(total_cost_usd, 0) + $1,
                           updated_at = NOW()
                       WHERE id = $2""",
                    total_cost, session_id,
                )
        except Exception:
            logger.exception("Failed to save assistant message %s", message_id)
