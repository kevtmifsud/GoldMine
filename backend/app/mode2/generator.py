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
import re
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
from app.mcp.registry import get_registry
from app.mcp.types import MCPToolResult
from .tools import (
    ALWAYS_LOADED_TOOL_NAMES,
    get_always_loaded_tools,
    get_tool_definitions,
)

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


def _build_chart_from_mcp_result(
    result: "MCPToolResult",
) -> str | None:
    """Build a ```chart block from an MCPToolResult with preferred_presentation='chart'."""
    if result.preferred_presentation != "chart":
        return None
    if not result.rows:
        return None

    from .chart_builder import build_line_chart, build_bar_chart
    from collections import defaultdict

    config = result.chart_config or {}
    chart_type = config.get("type", "line")
    x_col = config.get("x_column", "date")
    y_col = config.get("y_column", "value")
    series_col = config.get("series_column")
    title = config.get("title", "")
    y_label = config.get("y_label", "")

    # Build series data from rows
    if series_col:
        series_map: dict[str, list] = defaultdict(list)
        for row in result.rows:
            key = str(row.get(series_col, ""))
            x_val = str(row.get(x_col, ""))
            y_val = row.get(y_col)
            if y_val is not None:
                series_map[key].append([x_val, float(y_val)])
        series_data = [
            {"name": k, "data": v}
            for k, v in series_map.items()
        ]
    else:
        series_data = [{
            "name": y_label or y_col,
            "data": [
                [str(r.get(x_col, "")), float(r.get(y_col, 0))]
                for r in result.rows
                if r.get(y_col) is not None
            ],
        }]

    # Detect y format from data magnitude
    sample_val = 0.0
    for row in result.rows:
        v = row.get(y_col)
        if v is not None:
            sample_val = abs(float(v))
            break

    if sample_val > 1e9:
        y_format = "billions"
    elif sample_val > 1e6:
        y_format = "millions"
    else:
        y_format = "number"

    # Override with chart_config formatters
    formatters = config.get("formatters", {})
    if y_col in formatters:
        y_format = formatters[y_col]

    # Embed tool metadata so frontend can extract for "Add to Page"
    tool_meta = result.metadata.get("params", {})
    metadata_comment = (
        f"// tool: {result.tool_name}\n"
        f"// params: {json.dumps(tool_meta)}\n"
    )

    if chart_type == "line":
        spec = build_line_chart(
            title=title, series_data=series_data,
            y_format=y_format, y_label=y_label, x_label="Date",
        )
    elif chart_type == "bar":
        categories = list(dict.fromkeys(
            str(r.get(x_col, "")) for r in result.rows
        ))
        spec = build_bar_chart(
            title=title, categories=categories,
            series_data=series_data,
            y_format=y_format, y_label=y_label,
        )
    else:
        return None

    return (
        f"\n```chart\n"
        f"{metadata_comment}"
        f"{json.dumps(spec, indent=2)}"
        f"\n```\n"
    )


def _has_chartable_data(tool_results: list) -> bool:
    """Check if tool results contain data that could be plotted."""
    for result in tool_results:
        if not isinstance(result, list):
            continue
        for row in result:
            if isinstance(row, dict) and row.get("_table") in (
                "daily_estimates", "daily_pnl", "stock_history",
            ):
                return True
    return False


_CHART_BLOCK_RE = re.compile(r"\n*```chart\n.*?```\n*", re.DOTALL)
_PLOT_TOGGLE_RE = re.compile(r"\n*\[📈 Plot Over Time\?\]\(#plot-over-time\)\n*")


def _strip_chart_blocks(text: str) -> str:
    """Remove any ```chart blocks and Plot Over Time toggles from text.

    Used when auto-charts from MCP results will be appended, to prevent
    duplicate charts (one Claude-generated, one auto-generated).
    """
    text = _CHART_BLOCK_RE.sub("", text)
    text = _PLOT_TOGGLE_RE.sub("", text)
    return text


async def _build_chart_from_results(
    tool_results: list,
    classified: ClassifiedQuery,
) -> str | None:
    """Build a chart spec from tool results if chart was requested.

    For line charts, fetches the full time series (the tool results only
    contain the latest snapshot). Returns a ```chart code block or None.
    """
    if not classified.chart_requested:
        return None

    from .chart_builder import (
        format_estimates_for_line_chart,
        format_estimates_for_bar_chart,
        format_pnl_for_line_chart,
    )
    from .retrieval import _query_estimates_timeseries
    from .tools import _safe_json_dumps
    from collections import Counter

    estimates_rows = []
    pnl_rows = []

    for result in tool_results:
        if not isinstance(result, list):
            continue
        for row in result:
            if isinstance(row, dict):
                table = row.get("_table", "")
                if table == "daily_estimates":
                    estimates_rows.append(row)
                elif table == "daily_pnl":
                    pnl_rows.append(row)

    chart_spec = None

    if estimates_rows:
        # Pick the metric that best matches the user's topic
        topic = (classified.topic or "").lower()
        metric_candidates = list({r.get("metric") for r in estimates_rows})
        top_metric = metric_candidates[0]  # fallback
        for m in metric_candidates:
            if m and m.replace("_", " ") in topic:
                top_metric = m
                break
        # Prefer revenue/eps if topic doesn't narrow it
        if top_metric == metric_candidates[0]:
            for preferred in ["total_revenue", "diluted_eps", "ebitda"]:
                if preferred in metric_candidates:
                    top_metric = preferred
                    break

        period_counts = Counter(r.get("period") for r in estimates_rows)
        top_period = period_counts.most_common(1)[0][0]
        tickers = list({r.get("ticker") for r in estimates_rows if r.get("ticker")})

        if classified.chart_type == "line":
            # Line chart needs full time series — fetch it
            ts_rows = await _query_estimates_timeseries(tickers, top_metric, top_period)
            ts_parsed = json.loads(_safe_json_dumps(ts_rows))
            chart_spec = format_estimates_for_line_chart(
                ts_parsed, top_metric, top_period,
            )
        else:
            # Bar chart — grouped by period with source as series
            # Pass all estimate rows and let the chart builder handle grouping
            chart_spec = format_estimates_for_bar_chart(
                estimates_rows, top_metric,
            )
    elif pnl_rows:
        chart_spec = format_pnl_for_line_chart(pnl_rows, metric="itd_pnl")

    if not chart_spec:
        return None

    return f"\n\n```chart\n{json.dumps(chart_spec)}\n```\n"


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
    all_tool_calls_used: list[dict] = []  # name + input for each call (ordered, may have dupes)
    all_tool_result_data: list = []  # parsed tool results for chart building
    all_mcp_results: list[MCPToolResult] = []  # structured MCP results for auto-chart
    cost_warning_emitted = False
    tool_loop_iteration = 0
    max_tool_loops = 10  # safety limit

    # Dynamic tool loading: start with always-loaded tools,
    # expand as Claude discovers more via search_tools
    discovered_tool_names: set[str] = set()

    while tool_loop_iteration < max_tool_loops:
        tool_loop_iteration += 1

        # Build tool list: always-loaded + any discovered tools
        active_tools = get_always_loaded_tools() + get_tool_definitions(
            discovered_tool_names - ALWAYS_LOADED_TOOL_NAMES,
        )

        # Call Claude with retry logic for transient errors
        response = None
        for attempt in range(4):  # attempt 0 = first try, 1-3 = retries
            try:
                response = client.messages.create(
                    model=model,
                    max_tokens=4096,
                    system=system,
                    messages=messages,
                    tools=active_tools,
                )
                break  # Success — exit retry loop
            except (anthropic.APIError, anthropic.APIConnectionError) as api_err:
                user_msg, should_retry, max_retries = _friendly_api_error(api_err)
                logger.error(
                    "anthropic_api_error status=%s error=%s attempt=%s",
                    getattr(api_err, "status_code", None),
                    str(api_err), attempt,
                )

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

            # Track tool calls with full params
            tool_names = [b.name for b in tool_use_blocks]
            all_tool_names_used.extend(tool_names)
            for b in tool_use_blocks:
                all_tool_calls_used.append({"name": b.name, "input": b.input})
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

            # Execute tools via MCP registry and build tool_result blocks
            registry = get_registry()
            tool_results = []
            for block in tool_use_blocks:
                mcp_result = await registry.call_tool(
                    block.name,
                    block.input,
                    classified=classified,
                    query_embedding=query_embedding,
                    steps=steps,
                )

                # Store params in metadata for auto-chart "Add to Page"
                mcp_result.metadata["params"] = block.input
                mcp_result.metadata["tool_name"] = block.name
                all_mcp_results.append(mcp_result)

                # Convert MCPToolResult to JSON string for Claude.
                # If tool has preferred_presentation="chart", inject a hint
                # so Claude writes observations instead of a redundant table.
                # Use raw_json when available (legacy tools) to preserve
                # exact output format; fall back to structured conversion.
                if mcp_result.raw_json is not None:
                    result_str = mcp_result.raw_json
                elif mcp_result.rows:
                    from .tools import _safe_json_dumps
                    result_str = _safe_json_dumps(mcp_result.rows)
                else:
                    result_str = json.dumps([])

                # If tool returned an error, annotate for Claude
                if mcp_result.error:
                    result_str = json.dumps({
                        "error": True,
                        "note": (
                            f"The {block.name} data was unavailable. "
                            "Base your response only on successfully retrieved data. "
                            "Do not mention specific technical errors."
                        ),
                    })

                # For chart tools: truncate the raw data and replace with a
                # compact summary. Claude doesn't need 500 rows of JSON to
                # write 3 bullet observations — the chart is built separately
                # from the full data. This prevents Claude from dumping raw JSON.
                if (
                    mcp_result.preferred_presentation == "chart"
                    and not mcp_result.error
                    and mcp_result.rows
                ):
                    # Build a compact summary: first 5 and last 5 rows + stats
                    sample_rows = mcp_result.rows[:5]
                    if len(mcp_result.rows) > 10:
                        sample_rows += mcp_result.rows[-5:]
                    from .tools import _safe_json_dumps
                    result_str = _safe_json_dumps(sample_rows)
                    result_str += (
                        f"\n\n[SYSTEM: Showing {len(sample_rows)} of "
                        f"{len(mcp_result.rows)} total rows. "
                        "A chart will be automatically appended for the FULL dataset. "
                        "Do NOT render this data as a table or code block. "
                        "Do NOT output raw JSON. "
                        "Write ONLY: one intro line, then the chart (auto-provided), "
                        "then 3 bullet observations with specific numbers from the data. "
                        "Do NOT add any ```chart blocks — the system provides the chart.]"
                    )

                # Inject pre-formatted markdown for table tools
                if (
                    mcp_result.formatted_markdown
                    and not mcp_result.error
                    and mcp_result.preferred_presentation != "chart"
                ):
                    result_str += (
                        "\n\n[SYSTEM: The data above has been pre-formatted "
                        "into a markdown table. Include this table EXACTLY "
                        "as shown in your response — do not reformat, "
                        "reorder, or change any numbers. Add only a one-line "
                        "intro before it. Nothing after it.]\n\n"
                        + mcp_result.formatted_markdown
                    )

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_str,
                })

                # Track tools discovered via search_tools
                if block.name == "search_tools":
                    try:
                        search_result = json.loads(result_str)
                        if isinstance(search_result, dict):
                            for tool_info in search_result.get("matching_tools", []):
                                discovered_tool_names.add(tool_info["name"])
                    except (json.JSONDecodeError, TypeError, KeyError):
                        pass

                # Collect parsed data for chart building
                try:
                    parsed_result = json.loads(result_str)
                    if isinstance(parsed_result, list):
                        all_tool_result_data.append(parsed_result)
                except (json.JSONDecodeError, TypeError):
                    pass

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
    # 6b. Build chart specs — from explicit chart requests and MCP auto-chart
    # ------------------------------------------------------------------
    chart_block = await _build_chart_from_results(all_tool_result_data, classified)

    # Auto-chart: MCP tools with preferred_presentation="chart"
    mcp_chart_blocks: list[str] = []
    for mcp_res in all_mcp_results:
        block = _build_chart_from_mcp_result(mcp_res)
        if block:
            mcp_chart_blocks.append(block)

    # ------------------------------------------------------------------
    # 7. Stream the final text response
    # ------------------------------------------------------------------
    # Extract text from the final response content blocks
    full_response = ""
    for block in response.content:
        if hasattr(block, "text"):
            full_response += block.text

    # Append chart blocks: explicit request first, then MCP auto-charts.
    # When auto-charts are present, strip any chart blocks Claude generated
    # to prevent duplicate charts in the response.
    if chart_block:
        full_response = _strip_chart_blocks(full_response)
        full_response += chart_block
    elif mcp_chart_blocks:
        full_response = _strip_chart_blocks(full_response)
        full_response += "".join(mcp_chart_blocks)
    elif _has_chartable_data(all_tool_result_data):
        full_response += "\n\n[📈 Plot Over Time?](#plot-over-time)"

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
        "tool_calls": all_tool_calls_used,
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
