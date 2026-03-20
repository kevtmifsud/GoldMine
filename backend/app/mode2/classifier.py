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
- portfolio: Questions about positions, P&L, concentration, risk, or trade requests. Example: "What are my top 5 holdings by unrealized gain?"
- estimates: Questions about forward estimates from any source. Example: "What is AAPL Q4 revenue estimate?"
- alt_data: Questions involving alternative data signals. Example: "Show me credit card trends for SBUX"
- model_query: Questions about a ticker's financial model assumptions or scenarios. Example: "What are AAPL's base case assumptions?"
- model_edit: Request to change a model assumption. Example: "Change base case 2027 revenue growth to 15%"
- workflow: Request to run a named workflow. Example: "Run earnings preview for NVDA"

## Required sources
You MUST output a required_sources[] list. This tells the retrieval layer which data sources to query. Available sources:
- financial_metrics: Reported company financials (revenue, margins, EPS, balance sheet, cash flow)
- chunks_earnings_transcript: Earnings call transcripts (vector search)
- chunks_10k, chunks_10q, chunks_8k: SEC filings (vector search)
- chunks_analyst_note: Internal analyst notes (vector search)
- chunks_buyside_note: External buyside firm notes (vector search)
- chunks_sellside_note: Sellside firm notes (vector search)
- internal_estimates, buyside_estimates, consensus_estimates, sellside_estimates: Forward estimates
- guidance: Company-issued forward guidance
- daily_pnl: Portfolio P&L data
- portfolio_concentration: Portfolio exposure/weights
- portfolio_risk: Beta exposures
- trade_requests: Pending/historical trade requests
- stock_history: Historical price data
- alt_data: Alternative data (must also set alt_data_types[])
- model_outputs: Financial model assumptions/scenarios
- workflow_registry: Workflow lookup (for workflow type)

## Source routing rules (critical — follow exactly)
1. Portfolio queries → only daily_pnl, portfolio_concentration, portfolio_risk, trade_requests. NEVER include financial_metrics or stock_history.
2. Internal analyst note queries → only chunks_analyst_note. NEVER include chunks_sellside_note or chunks_buyside_note.
3. Sellside queries → only chunks_sellside_note. NEVER include chunks_analyst_note or chunks_buyside_note.
4. Buyside queries → only chunks_buyside_note. NEVER include chunks_analyst_note or chunks_sellside_note.
5. Estimates queries → ALWAYS include ALL FOUR: internal_estimates, buyside_estimates, consensus_estimates, sellside_estimates. Never present a single source alone.
6. Alt data → ALWAYS set alt_data_types[] with the specific type(s). Never query alt_data without a type filter.
7. Stock price/performance → stock_history only. Self-contained.
8. Multi-source queries are the norm — include all relevant sources.

## Alt data keyword mapping
Map natural language terms to alt_data_types values:
- credit card, card data, transaction data, consumer spend, CC data, card trends, card spend → credit_card
- web traffic, website visits, web visits, site traffic, online traffic → web_traffic
- app downloads, download data, app installs, mobile downloads, app activity → app_downloads
- google trends, search trends, search data, search interest → google_trends
- email receipts, receipt data, email data, purchase receipts → email_receipts
- medical claims, claims data, healthcare data, Rx data → medical_claims
If the user mentions an alt data type not in this list, set alt_data_types to an empty array.

## Output format
Return ONLY valid JSON matching this schema (no markdown, no preamble):
{{
  "query_type": "<one of the types above>",
  "tickers": ["AAPL"],
  "list_references": [],
  "fiscal_periods": ["Q4_2024"],
  "topic": "gross margin outlook",
  "needs_structured_data": false,
  "needs_vector_search": true,
  "section_type_hint": null,
  "time_range_quarters": null,
  "required_sources": ["financial_metrics", "chunks_earnings_transcript"],
  "alt_data_types": [],
  "workflow_name": null
}}

## Rules
- Infer fiscal periods from natural language. Today is {today}.
  "last quarter" = current quarter - 1, "this year" = current fiscal year.
  Format periods as Q{{N}}_{{YYYY}} for quarterly, FY{{YYYY}} for annual.
- If the user references a named list (e.g., "my tech names", "semiconductor names"), put the name in list_references, NOT in tickers.
- Set section_type_hint when topic maps to a known section: "guidance" → "cfo_remarks", "risk" → "risk_factors", "strategy" → "ceo_remarks".
- For quantitative questions, set needs_structured_data=true. For qualitative, set needs_vector_search=true. For hybrid, set both.
- For trend_analysis, set time_range_quarters to the number of quarters requested.
- For workflow queries, set workflow_name to the machine name (e.g. "earnings_preview", "financial_model_generation").

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
        classified = ClassifiedQuery(**data)
    except (json.JSONDecodeError, Exception) as e:
        logger.warning("Classifier returned invalid JSON: %s — %s", e, raw[:200])
        # Safe fallback
        classified = ClassifiedQuery(
            query_type="single_ticker_qualitative",
            tickers=[],
            needs_vector_search=True,
        )

    # Enforce routing rules deterministically
    classified.required_sources = resolve_required_sources(classified)
    return classified


# ---------------------------------------------------------------------------
# Alt data keyword → data_type mapping (authoritative, from chatbot.md)
# ---------------------------------------------------------------------------
ALT_DATA_KEYWORD_MAP: dict[str, str] = {
    "credit card": "credit_card",
    "card data": "credit_card",
    "transaction data": "credit_card",
    "consumer spend": "credit_card",
    "cc data": "credit_card",
    "card trends": "credit_card",
    "card spend": "credit_card",
    "web traffic": "web_traffic",
    "website visits": "web_traffic",
    "web visits": "web_traffic",
    "site traffic": "web_traffic",
    "online traffic": "web_traffic",
    "app downloads": "app_downloads",
    "download data": "app_downloads",
    "app installs": "app_downloads",
    "mobile downloads": "app_downloads",
    "app activity": "app_downloads",
    "google trends": "google_trends",
    "search trends": "google_trends",
    "search data": "google_trends",
    "search interest": "google_trends",
    "email receipts": "email_receipts",
    "receipt data": "email_receipts",
    "email data": "email_receipts",
    "purchase receipts": "email_receipts",
    "medical claims": "medical_claims",
    "claims data": "medical_claims",
    "healthcare data": "medical_claims",
    "rx data": "medical_claims",
}

# All four estimate sources — always queried together, never in isolation
_ALL_ESTIMATE_SOURCES = [
    "internal_estimates",
    "buyside_estimates",
    "consensus_estimates",
    "sellside_estimates",
]

# Portfolio-only sources
_PORTFOLIO_SOURCES = [
    "daily_pnl",
    "portfolio_concentration",
    "portfolio_risk",
    "trade_requests",
]

# Sources that must never appear together (mutual exclusion groups)
_NOTE_TYPES = {"chunks_analyst_note", "chunks_buyside_note", "chunks_sellside_note"}


def resolve_required_sources(classified: ClassifiedQuery) -> list[str]:
    """Enforce routing rules from chatbot.md on top of LLM output.

    The LLM's ``required_sources`` is treated as a starting suggestion.
    This function adds mandatory sources, removes prohibited ones, and
    enforces isolation rules deterministically.
    """
    sources = list(classified.required_sources)
    qtype = classified.query_type

    # ----- Query-type-driven defaults when LLM returns empty list -----
    if not sources:
        if qtype == "portfolio":
            sources = list(_PORTFOLIO_SOURCES)
        elif qtype == "estimates":
            sources = list(_ALL_ESTIMATE_SOURCES)
        elif qtype == "alt_data":
            sources = ["alt_data"]
        elif qtype == "model_query":
            sources = ["model_outputs"]
        elif qtype == "model_edit":
            sources = ["model_outputs"]
        elif qtype == "workflow":
            sources = ["workflow_registry"]
        elif qtype == "single_ticker_quantitative":
            sources = ["financial_metrics"]
        elif qtype == "single_ticker_qualitative":
            sources = ["chunks_earnings_transcript"]
        elif qtype in ("cross_ticker", "screening", "trend_analysis"):
            sources = ["chunks_earnings_transcript"]
            if classified.needs_structured_data:
                sources.append("financial_metrics")

    # ----- Rule 1: Portfolio isolation -----
    if qtype == "portfolio":
        sources = [s for s in sources if s in _PORTFOLIO_SOURCES]
        if not sources:
            sources = list(_PORTFOLIO_SOURCES)

    # ----- Rule 2-4: Note type isolation -----
    present_notes = _NOTE_TYPES & set(sources)
    if len(present_notes) > 1:
        # Keep only the first one found (in deterministic order)
        for note in ("chunks_analyst_note", "chunks_sellside_note", "chunks_buyside_note"):
            if note in present_notes:
                sources = [s for s in sources if s not in _NOTE_TYPES or s == note]
                break

    # ----- Rule 5: Estimates always all four -----
    has_any_estimate = any(s in _ALL_ESTIMATE_SOURCES for s in sources)
    if has_any_estimate or qtype == "estimates":
        for est in _ALL_ESTIMATE_SOURCES:
            if est not in sources:
                sources.append(est)

    # ----- Rule 6: Alt data requires type filter -----
    if "alt_data" in sources and not classified.alt_data_types:
        # Remove alt_data if no types specified — can't query without filter
        sources = [s for s in sources if s != "alt_data"]

    # Deduplicate while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for s in sources:
        if s not in seen:
            seen.add(s)
            deduped.append(s)

    return deduped
