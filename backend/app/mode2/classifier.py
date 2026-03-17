"""WF-06: Query Classification.

Classifies user query, extracts tickers, periods, topic.
Uses Claude Haiku via model_config — never hardcoded.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

import time

import anthropic

from .cost import get_model_config, calculate_cost, emit_cost_event
from .db import get_conn
from .models import ClassifiedQuery
from .steps import StepCollector

logger = logging.getLogger(__name__)

CLASSIFIER_SYSTEM_PROMPT = """\
You are a financial query classifier. Analyze the user's question and return a JSON object.

## Query types
- single_ticker_qualitative: One ticker, qualitative question answered from transcript/document chunks. Example: "What did AAPL say about margins last quarter?"
- single_ticker_quantitative: One ticker, numerical question answered from structured financial tables. Example: "What was AAPL's gross margin in Q3 2024?"
- cross_ticker: Multiple tickers, comparison or aggregation. Example: "Compare guidance tone across my semiconductor names"
- screening: Broad universe, filter by criteria. Example: "Which tickers flagged supply chain risks this quarter?"
- trend_analysis: One ticker, multiple time periods. Example: "How has AAPL's China commentary changed over 8 quarters?"

## Output format
Return ONLY valid JSON matching this schema (no markdown, no preamble):
{{
  "query_type": "<one of the five types above>",
  "tickers": ["AAPL"],
  "list_references": [],
  "fiscal_periods": ["Q4_2024"],
  "topic": "gross margin outlook",
  "needs_structured_data": false,
  "needs_vector_search": true,
  "section_type_hint": null,
  "time_range_quarters": null
}}

## Rules
- Infer fiscal periods from natural language. Today is {today}.
  "last quarter" = current quarter - 1, "this year" = current fiscal year.
  Format periods as Q{{N}}_{{YYYY}} for quarterly, FY{{YYYY}} for annual.
- If the user references a named list (e.g., "my tech names", "semiconductor names"), put the name in list_references, NOT in tickers.
- Set section_type_hint when topic maps to a known section: "guidance" → "cfo_remarks", "risk" → "risk_factors", "strategy" → "ceo_remarks".
- For quantitative questions, set needs_structured_data=true. For qualitative, set needs_vector_search=true. For hybrid, set both.
- For trend_analysis, set time_range_quarters to the number of quarters requested.

## User's ticker lists
{ticker_lists}
"""


async def classify_query(
    message: str,
    history: list[dict[str, str]] | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    message_id: str | None = None,
    steps: StepCollector | None = None,
) -> ClassifiedQuery:
    """Classify a user message. Returns ClassifiedQuery."""
    import os
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

    # Get model from config
    config = await get_model_config("query_classifier")
    model = config["model"]

    # Get user's ticker lists
    ticker_lists_str = "None"
    if user_id:
        async with get_conn() as conn:
            rows = await conn.fetch(
                "SELECT list_name, tickers FROM user_ticker_lists WHERE user_id = $1",
                user_id,
            )
            if rows:
                ticker_lists_str = "\n".join(
                    f"- {r['list_name']}: {r['tickers']}" for r in rows
                )

    # Build messages
    today = datetime.now().strftime("%Y-%m-%d")
    system = CLASSIFIER_SYSTEM_PROMPT.format(today=today, ticker_lists=ticker_lists_str)

    messages = []
    if history:
        for turn in history[-4:]:  # Last 2 exchanges = 4 messages
            messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": message})

    # Call Haiku
    api_key = os.environ.get("GOLDMINE_ANTHROPIC_API_KEY", "")
    client = anthropic.Anthropic(api_key=api_key)

    t0 = time.time()
    response = client.messages.create(
        model=model,
        max_tokens=512,
        system=system,
        messages=messages,
    )
    classify_duration_ms = int((time.time() - t0) * 1000)

    raw = response.content[0].text.strip()
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens

    # Calculate and log cost
    cost = await calculate_cost(model, input_tokens, output_tokens)
    if steps:
        steps.add(
            label="Classifying your question",
            detail=f"Haiku classification ({input_tokens}+{output_tokens} tokens)",
            source="anthropic",
            model=model,
            cost_usd=cost,
            duration_ms=classify_duration_ms,
            result_summary="",
        )
    emit_cost_event(
        mode="mode_2",
        component="query_classifier",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        session_id=session_id,
        message_id=message_id,
        user_id=user_id,
    )

    # Parse JSON
    try:
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        data = json.loads(raw)
        return ClassifiedQuery(**data)
    except (json.JSONDecodeError, Exception) as e:
        logger.warning("Classifier returned invalid JSON: %s — %s", e, raw[:200])
        # Safe fallback
        return ClassifiedQuery(
            query_type="single_ticker_qualitative",
            tickers=[],
            needs_vector_search=True,
        )
