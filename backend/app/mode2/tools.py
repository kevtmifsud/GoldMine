"""Tool definitions and dispatch for the agentic Mode 2 pipeline.

Defines tool registry with always-loaded and deferred (on-demand) tools.
The search_tools tool lets Claude discover deferred tools dynamically,
reducing context token usage while maintaining access to the full library.

Public API:
  get_always_loaded_tools()  — tools sent in every API call
  get_tool_definitions(names) — full definitions for specific tools
  get_all_tools()            — all tool definitions (backwards compat)
  execute_tool()             — routes tool calls to retrieval.py
  GOLDMINE_TOOLS             — backwards-compatible alias for get_all_tools()
"""
from __future__ import annotations

import json
import logging
import re
import traceback as _traceback
import uuid as _uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from .models import ClassifiedQuery
from .steps import StepCollector

logger = logging.getLogger(__name__)

# Friendly labels for tool names shown to users
_TOOL_LABELS: dict[str, str] = {
    "search_tools": "tool search",
    "search_documents": "document search",
    "get_financial_metrics": "financial metrics",
    "get_all_estimates": "estimates",
    "get_daily_pnl": "portfolio P&L",
    "get_portfolio_concentration": "portfolio concentration",
    "get_portfolio_risk": "portfolio risk",
    "get_trade_requests": "trade requests",
    "get_stock_history": "stock price history",
    "get_guidance": "guidance",
    "get_alt_data": "alternative data",
    "get_model_outputs": "model outputs",
    "get_workflow_registry": "workflow registry",
    "run_workflow": "workflow execution",
    "get_workflow_output": "workflow output",
    "model_edit": "model edit",
}

# ---------------------------------------------------------------------------
# Tool search configuration
# ---------------------------------------------------------------------------

# Tools always sent to the API (high-frequency, core path)
ALWAYS_LOADED_TOOL_NAMES: set[str] = {
    "search_tools",
    "search_documents",
    "get_financial_metrics",
    "get_all_estimates",
    "get_daily_pnl",
}

# Keyword index for deferred tool discovery (substring matching)
_DEFERRED_TOOL_INDEX: dict[str, list[str]] = {
    "get_portfolio_concentration": [
        "concentration", "exposure", "weight", "sector weight",
        "position weight", "neutrality",
    ],
    "get_portfolio_risk": [
        "risk", "beta", "beta exposure", "weighted beta",
    ],
    "get_trade_requests": [
        "trade", "trades", "order", "pending", "trade request",
    ],
    "get_stock_history": [
        "stock price", "price history", "close price", "performance",
        "stock history", "price",
    ],
    "get_guidance": [
        "guidance", "forward guidance", "outlook", "raised", "lowered",
        "withdrawn", "company guidance",
    ],
    "get_alt_data": [
        "alt data", "alternative data", "credit card", "web traffic",
        "app downloads", "google trends", "email receipts", "medical claims",
    ],
    "get_model_outputs": [
        "model", "model output", "assumptions", "scenario", "kpi",
        "financial model", "valuation",
    ],
    "get_workflow_registry": [
        "workflow", "registry", "available workflows", "list workflows",
    ],
    "run_workflow": [
        "run workflow", "execute workflow", "earnings preview",
        "generate model", "docs sync",
    ],
    "get_workflow_output": [
        "workflow output", "prior workflow", "previous workflow",
        "workflow result",
    ],
    "model_edit": [
        "edit model", "change assumption", "modify model", "update assumption",
        "model edit",
    ],
}


def _safe_json_dumps(obj: Any) -> str:
    """JSON serialize with safe handling of asyncpg/database types.

    Converts: Decimal → float, datetime/date → isoformat, UUID → str.
    """
    def _default(o: Any) -> Any:
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if isinstance(o, _uuid.UUID):
            return str(o)
        return str(o)

    return json.dumps(obj, default=_default)


# ---------------------------------------------------------------------------
# Tool definitions (Anthropic tool-use format)
# ---------------------------------------------------------------------------

_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "search_tools",
        "description": (
            "Search for additional data tools by keyword. Returns full tool "
            "definitions for matching tools so you can use them in subsequent "
            "calls. Use this when you need a tool that isn't in your current "
            "tool set — for example, tools for stock prices, guidance, alt data, "
            "portfolio risk/concentration, trade requests, workflows, or model editing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Keywords describing the data you need "
                        "(e.g. 'stock price history', 'portfolio risk', "
                        "'workflow', 'guidance', 'alt data', 'model edit')."
                    ),
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_documents",
        "description": (
            "Search financial document chunks via vector similarity. "
            "Returns relevant passages from earnings transcripts, SEC filings "
            "(10-K, 10-Q, 8-K), analyst notes, buyside notes, and sellside notes. "
            "You MUST specify doc_types to filter which document types to search. "
            "\n\nSOURCE ISOLATION RULES (critical):\n"
            "- For internal analyst note queries: use doc_types=['analyst_note'] ONLY. "
            "NEVER include 'sellside_note' or 'buyside_note' in the same call.\n"
            "- For sellside note queries: use doc_types=['sellside_note'] ONLY. "
            "NEVER include 'analyst_note' or 'buyside_note' in the same call.\n"
            "- For buyside note queries: use doc_types=['buyside_note'] ONLY. "
            "NEVER include 'analyst_note' or 'sellside_note' in the same call.\n"
            "- For general qualitative queries (earnings, filings): use "
            "doc_types=['earnings_transcript'] or doc_types=['10-K','10-Q','8-K'] as needed.\n"
            "\nEvery passage returned must be cited inline using "
            "[TICKER | DOCUMENT_TYPE | PERIOD | SECTION] format."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tickers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ticker symbols to search. Empty array searches all tickers.",
                },
                "doc_types": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "earnings_transcript",
                            "10-K", "10-Q", "8-K",
                            "analyst_note",
                            "buyside_note",
                            "sellside_note",
                        ],
                    },
                    "description": "Document types to search. Required.",
                },
                "limit_per_ticker": {
                    "type": "integer",
                    "description": "Max chunks per ticker. Default 6 for single ticker, 3 for multi-ticker.",
                    "default": 6,
                },
                "section_type": {
                    "type": "string",
                    "description": "Optional section filter (e.g. 'cfo_remarks', 'risk_factors', 'ceo_remarks').",
                },
                "fiscal_periods": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional fiscal period filter (e.g. ['Q4_2024', 'Q3_2024']).",
                },
            },
            "required": ["tickers", "doc_types"],
        },
    },
    {
        "name": "get_financial_metrics",
        "description": (
            "Query reported company financials (revenue, margins, EPS, balance sheet, "
            "cash flow) from the financial_metrics table. Returns actual reported figures only. "
            "\n\nNEVER use this tool for portfolio P&L queries — use get_daily_pnl instead. "
            "These are company-reported financials, not portfolio performance data."
            "\n\nCite every figure as [TICKER | Financials | Period]."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tickers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ticker symbols to query.",
                },
                "topic": {
                    "type": "string",
                    "description": (
                        "Topic to determine which metrics to fetch. "
                        "Examples: 'revenue margins', 'debt balance sheet', 'cash flow capex'."
                    ),
                },
                "fiscal_periods": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional fiscal period filter.",
                },
            },
            "required": ["tickers", "topic"],
        },
    },
    {
        "name": "get_all_estimates",
        "description": (
            "Returns forward estimates from daily_estimates table. "
            "For screening/ranking across the full universe, omit tickers entirely — "
            "the query runs against ALL tickers without filtering. "
            "For specific tickers, pass them all in a single call. "
            "Always returns all four sources side by side: consensus (no firm), buyside "
            "(by firm and analyst), internal (by analyst), sellside (by firm and analyst). "
            "\n\nWhen querying many tickers or the full universe, ALWAYS set the metric "
            "filter (e.g. 'eps', 'revenue') to keep results compact. "
            "\n\nstaleness_days shows how many days since the estimate was last updated. "
            "High staleness (>90 days) means the estimate may be outdated. "
            "\n\nAll four sources always returned — never present a single source alone. "
            "If a source has no estimate for a metric it is absent from results, not an error."
            "\n\nPresent all sources side by side. Highlight the spread between them. "
            "Cite each value with its source: "
            "[TICKER | Internal | analyst_name | Period], "
            "[TICKER | firm | analyst_name | Period], "
            "[TICKER | Consensus | Period | as of as_of_date], "
            "[TICKER | firm | analyst_name | Period]. "
            "Always note staleness if staleness_days > 90: '(estimate is N days old)'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tickers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ticker symbols to query. Omit or pass empty array to query ALL tickers (for screening/ranking across the full universe).",
                },
                "metric": {
                    "type": "string",
                    "description": "Filter to a single metric. DB values: 'diluted_eps', 'total_revenue', 'ebitda', 'gross_profit', 'operating_income', 'free_cash_flow'. Aliases also accepted: 'eps', 'revenue', 'fcf'. Strongly recommended when querying many tickers or the full universe.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_daily_pnl",
        "description": (
            "Query portfolio P&L data from daily_pnl table. Use for any question about "
            "portfolio performance, P&L, daily returns, holdings, or contribution to portfolio. "
            "\n\nReturns per position: unrealized_pnl (mark-to-market on open positions), "
            "daily_realized_pnl (P&L from positions closed TODAY only), "
            "ytd_pnl (year-to-date total P&L since Jan 1), "
            "itd_pnl (inception-to-date total P&L since first trade), "
            "market_value (current dollar value), daily_return (today's return %)."
            "\n\nFor portfolio-wide queries (e.g. 'top 5 holdings'), omit ticker to get all positions. "
            "Defaults to most recent date. Supports grouping by portfolio, side, sector."
            "\n\nPortfolio values: 'Flagship', 'Long Only', or 'all' for both — "
            "they will never be mixed or aggregated together."
            "\n\nFor portfolio queries, ONLY use portfolio tools (get_daily_pnl, "
            "get_portfolio_concentration, get_portfolio_risk, get_trade_requests). "
            "NEVER combine with get_financial_metrics or get_stock_history."
            "\n\nNo citation required for portfolio data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Single ticker to filter. Omit for all positions.",
                },
                "portfolio": {
                    "type": "string",
                    "description": "Which portfolio to query. Use 'Flagship' or 'Long Only' for a specific portfolio. Use 'all' to see both portfolios separately — they will never be mixed or aggregated together. Default: 'all'.",
                },
                "order_by": {
                    "type": "string",
                    "description": "Column to sort by. Options: unrealized_pnl, realized_pnl, market_value, cost_basis, daily_return, cumulative_return, contribution_to_portfolio, shares_held, ticker. Default: unrealized_pnl.",
                },
                "order_dir": {
                    "type": "string",
                    "enum": ["asc", "desc"],
                    "description": "Sort direction. Default: desc.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max rows to return. Default: 100.",
                },
                "group_by": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Columns to group by for aggregation: portfolio, side, sector, industry, ticker, date.",
                },
                "date": {
                    "type": "string",
                    "description": "Specific date (YYYY-MM-DD). Default: most recent date.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_portfolio_concentration",
        "description": (
            "Query portfolio concentration and exposure data. Returns position weights, "
            "sector weights, industry weights, and market neutrality compliance. "
            "\n\nPortfolio values: 'Flagship', 'Long Only', or omit for both."
            "\n\nFor portfolio queries, ONLY use portfolio tools. "
            "NEVER combine with get_financial_metrics or get_stock_history."
            "\n\nNo citation required for portfolio data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Single ticker to filter. Omit for full portfolio.",
                },
                "portfolio": {
                    "type": "string",
                    "description": "Portfolio filter: 'Flagship', 'Long Only', or omit for both.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_portfolio_risk",
        "description": (
            "Query portfolio risk data including beta exposures and weighted beta "
            "contributions. "
            "\n\nPortfolio values: 'Flagship', 'Long Only', or omit for both."
            "\n\nFor portfolio queries, ONLY use portfolio tools. "
            "NEVER combine with get_financial_metrics or get_stock_history."
            "\n\nNo citation required for portfolio data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Single ticker to filter. Omit for full portfolio.",
                },
                "portfolio": {
                    "type": "string",
                    "description": "Portfolio filter: 'Flagship', 'Long Only', or omit for both.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_trade_requests",
        "description": (
            "Query pending and historical trade requests. Read-only — you cannot create "
            "or modify trade requests."
            "\n\nNo citation required for trade request data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tickers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ticker symbols to filter trade requests.",
                },
            },
            "required": ["tickers"],
        },
    },
    {
        "name": "get_stock_history",
        "description": (
            "Query historical stock price data (close price, EPS estimate, EPS actual) "
            "for the last 90 days. Use for price and performance questions, and for "
            "comparing EPS estimates vs actuals."
            "\n\nNEVER use this tool for portfolio P&L queries — use get_daily_pnl instead."
            "\n\nNo citation required for stock price data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tickers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ticker symbols to query price history for.",
                },
            },
            "required": ["tickers"],
        },
    },
    {
        "name": "get_guidance",
        "description": (
            "Query company-issued forward guidance. Returns guidance metrics, "
            "ranges (low/high), and guidance type (initial, raised, lowered, withdrawn)."
            "\n\nCite as [TICKER | Guidance | Period | Date]."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tickers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ticker symbols to query guidance for.",
                },
                "fiscal_periods": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional fiscal period filter.",
                },
            },
            "required": ["tickers"],
        },
    },
    {
        "name": "get_alt_data",
        "description": (
            "Retrieve alternative data signals for a ticker. Returns raw values "
            "exactly as stored — never aggregates, calculates, or transforms the data. "
            "Always show the raw values from the database to the analyst."
            "\n\nAvailable signals by industry:"
            "\nRestaurants (CMG, DPZ, SBUX):"
            "\n  credit_card_sss_yoy — same-store sales YoY % (daily, 3-day lag)"
            "\n  credit_card_txn_yoy — transaction count YoY % (daily, 3-day lag)"
            "\n  credit_card_spv_yoy — spend per visit YoY % (daily, 3-day lag)"
            "\n  foot_traffic_yoy — store visits YoY % (weekly, 1-week lag)"
            "\n  app_downloads_yoy — app downloads YoY % (weekly, 1-week lag)"
            "\n  web_traffic_yoy — web traffic YoY % (weekly, 1-week lag)"
            "\n  reservations_yoy — reservations YoY % (weekly, 2-week lag, CMG and SBUX only)"
            "\n  job_postings_yoy — job postings YoY % (monthly, 2-week lag)"
            "\n\nIMPORTANT: Never aggregate or transform values. Always show raw values "
            "as stored. Include date, value, growth, unit, and source_vendor. "
            "Always note the data lag when presenting results."
            "\n\nCite as [TICKER | Alt Data | SIGNAL_NAME | DATE]."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol.",
                },
                "data_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Signal names to query. Empty list = all available signals for this ticker.",
                },
                "date_from": {
                    "type": "string",
                    "description": "Start date YYYY-MM-DD. Default: signal-appropriate lookback.",
                },
                "date_to": {
                    "type": "string",
                    "description": "End date YYYY-MM-DD. Default: most recent available.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max rows per signal. Default: 30 for daily, 12 for weekly/monthly.",
                },
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_model_outputs",
        "description": (
            "Query financial model assumptions, scenario outputs, and KPIs. "
            "Returns the most recent model version per ticker."
            "\n\nCite as [TICKER | Model | Date]."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tickers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ticker symbols to query model outputs for.",
                },
            },
            "required": ["tickers"],
        },
    },
    {
        "name": "get_workflow_registry",
        "description": (
            "Look up available workflows by name. Use when the user requests "
            "running a workflow (e.g. earnings preview, financial model generation)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "workflow_name": {
                    "type": "string",
                    "description": "Machine name of the workflow (e.g. 'earnings_preview'). Omit to list all active workflows.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "run_workflow",
        "description": (
            "Execute a registered workflow. Use when the user explicitly requests "
            "running a workflow (e.g. 'run earnings preview for AAPL Q1 2026'). "
            "The workflow must exist in workflow_registry and be active. "
            "Required inputs depend on the workflow — check get_workflow_registry first "
            "if unsure what inputs are needed."
            "\n\nThis tool triggers the full workflow execution pipeline: "
            "validates inputs, creates a workflow_runs row, executes all sections, "
            "writes output to the workflow's output table, and returns the structured result."
            "\n\nDo NOT call this tool for simple data queries — use the specific "
            "data tools instead. Only call run_workflow when the user wants a full "
            "structured workflow output (earnings preview, financial model, etc.)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "workflow_name": {
                    "type": "string",
                    "description": "Machine name of the workflow (e.g. 'earnings_preview').",
                },
                "inputs": {
                    "type": "object",
                    "description": (
                        "Workflow inputs. Keys depend on the workflow. "
                        "For earnings_preview: {ticker, reporting_period, forward_period}. "
                        "For financial_model_generation: {ticker, key_kpis}. "
                        "For docs_sync: {} (no inputs required)."
                    ),
                },
            },
            "required": ["workflow_name", "inputs"],
        },
    },
    {
        "name": "get_workflow_output",
        "description": (
            "Retrieve the most recent stored output for a workflow. "
            "Use this to check if a prior workflow output exists before running "
            "a new one, or to surface prior results to the user."
            "\n\nFor ticker-specific workflows (earnings_preview, financial_model_generation), "
            "provide the ticker. For tickerless workflows (docs_sync), omit ticker to get "
            "the most recent run."
            "\n\nReturns the full structured output from the workflow's output table."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "workflow_name": {
                    "type": "string",
                    "description": "Machine name of the workflow (e.g. 'earnings_preview', 'docs_sync').",
                },
                "ticker": {
                    "type": "string",
                    "description": "Ticker to look up. Omit for tickerless workflows like docs_sync.",
                },
            },
            "required": ["workflow_name"],
        },
    },
    {
        "name": "model_edit",
        "description": (
            "Edit a financial model assumption and regenerate the model. "
            "Use when the user asks to change a model assumption "
            "(e.g. 'change base case 2027 revenue growth to 15%'). "
            "\n\nThis reads the current ASSUMPTIONS sheet from model_outputs, "
            "applies the edit, and triggers a full model regeneration with "
            "the updated assumptions. Returns the new version number and "
            "confirmation of the change."
            "\n\nDo NOT use this for reading model data — use get_model_outputs instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Ticker symbol to edit the model for.",
                },
                "assumption_key": {
                    "type": "string",
                    "description": (
                        "The assumption row name to edit. Must match exactly: "
                        "e.g. 'Revenue Growth Rate (%)', 'Gross Margin (%)', 'WACC (%)'."
                    ),
                },
                "scenario": {
                    "type": "string",
                    "enum": ["base", "bull", "bear"],
                    "description": "Which scenario to edit.",
                },
                "new_value": {
                    "type": "number",
                    "description": "The new value for the assumption (e.g. 0.15 for 15%).",
                },
                "period": {
                    "type": "string",
                    "description": "Optional period to apply the edit to (e.g. 'FY2027E'). If omitted, applies to all forward periods.",
                },
            },
            "required": ["ticker", "assumption_key", "scenario", "new_value"],
        },
    },
]

# ---------------------------------------------------------------------------
# Tool registry — keyed by name for fast lookup
# ---------------------------------------------------------------------------

_ALL_TOOLS: dict[str, dict[str, Any]] = {t["name"]: t for t in _TOOL_DEFINITIONS}


def get_always_loaded_tools() -> list[dict[str, Any]]:
    """Return tool definitions that are sent in every API call."""
    return [_ALL_TOOLS[name] for name in ALWAYS_LOADED_TOOL_NAMES if name in _ALL_TOOLS]


def get_tool_definitions(names: set[str]) -> list[dict[str, Any]]:
    """Return full tool definitions for the given tool names."""
    return [_ALL_TOOLS[n] for n in names if n in _ALL_TOOLS]


def get_all_tools() -> list[dict[str, Any]]:
    """Return all tool definitions (backwards-compatible)."""
    return list(_ALL_TOOLS.values())


# Backwards-compatible alias
GOLDMINE_TOOLS: list[dict[str, Any]] = get_all_tools()


# ---------------------------------------------------------------------------
# Tool search implementation
# ---------------------------------------------------------------------------

def _search_tools(query: str) -> list[dict[str, Any]]:
    """Search deferred tools by keyword matching.

    Returns full tool definitions for matching deferred tools.
    Uses substring matching against the keyword index.
    Falls back to returning all deferred tools if no matches found.
    """
    query_lower = query.lower()
    matched_names: set[str] = set()

    for tool_name, keywords in _DEFERRED_TOOL_INDEX.items():
        # Match against keywords
        for kw in keywords:
            if kw in query_lower:
                matched_names.add(tool_name)
                break
        # Match against tool name (underscores → spaces)
        if tool_name.replace("_", " ") in query_lower:
            matched_names.add(tool_name)

    # Fallback: return all deferred tools if no keyword match
    if not matched_names:
        matched_names = set(_DEFERRED_TOOL_INDEX.keys())

    return get_tool_definitions(matched_names)


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------

async def execute_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    classified: ClassifiedQuery,
    query_embedding: list[float],
    steps: StepCollector | None = None,
) -> str:
    """Execute a tool call and return the result as a JSON string.

    Routes each tool to the correct _query_* function in retrieval.py.
    The search_documents tool uses query_embedding which is embedded once
    at the start of the agentic loop in generator.py.

    Read-only enforcement: only calls _query_* functions. Never calls
    any function that writes to source tables.
    """
    from . import retrieval

    try:
        if tool_name == "search_tools":
            results = _search_tools(tool_input.get("query", ""))
            return _safe_json_dumps({
                "matching_tools": [
                    {"name": t["name"], "description": t["description"]}
                    for t in results
                ],
                "tool_count": len(results),
                "instruction": (
                    "These tools are now available. Call them with the "
                    "parameters shown in their definitions."
                ),
            })

        elif tool_name == "search_documents":
            chunks = await retrieval._vector_search(
                query_embedding=query_embedding,
                tickers=tool_input.get("tickers", []),
                limit_per_ticker=tool_input.get("limit_per_ticker", 6),
                section_type=tool_input.get("section_type"),
                fiscal_periods=tool_input.get("fiscal_periods"),
                doc_types=tool_input.get("doc_types"),
                steps=steps,
            )
            return _safe_json_dumps(
                [c.model_dump() for c in chunks],
            )

        elif tool_name == "get_financial_metrics":
            rows = await retrieval._structured_query(
                tickers=tool_input.get("tickers", []),
                topic=tool_input.get("topic", ""),
                fiscal_periods=tool_input.get("fiscal_periods"),
                steps=steps,
            )
            return _safe_json_dumps(rows)

        elif tool_name == "get_all_estimates":
            rows = await retrieval._query_estimates(
                tickers=tool_input.get("tickers", []),
                classified=classified,
                steps=steps,
                metric=tool_input.get("metric"),
            )
            return _safe_json_dumps(rows)

        elif tool_name == "get_daily_pnl":
            rows = await retrieval._query_daily_pnl(
                tickers=[tool_input["ticker"]] if tool_input.get("ticker") else [],
                classified=classified,
                steps=steps,
                portfolio=tool_input.get("portfolio", "all"),
                date=tool_input.get("date"),
                date_range=tool_input.get("date_range"),
                group_by=tool_input.get("group_by"),
                ticker=tool_input.get("ticker"),
                limit=tool_input.get("limit"),
                order_by=tool_input.get("order_by", "unrealized_pnl"),
                order_dir=tool_input.get("order_dir", "desc"),
            )
            return _safe_json_dumps(rows)

        elif tool_name == "get_portfolio_concentration":
            rows = await retrieval._query_portfolio_concentration(
                tickers=[tool_input["ticker"]] if tool_input.get("ticker") else [],
                classified=classified,
                steps=steps,
                portfolio=tool_input.get("portfolio"),
                ticker=tool_input.get("ticker"),
            )
            return _safe_json_dumps(rows)

        elif tool_name == "get_portfolio_risk":
            rows = await retrieval._query_portfolio_risk(
                tickers=[tool_input["ticker"]] if tool_input.get("ticker") else [],
                classified=classified,
                steps=steps,
                portfolio=tool_input.get("portfolio"),
                ticker=tool_input.get("ticker"),
            )
            return _safe_json_dumps(rows)

        elif tool_name == "get_trade_requests":
            rows = await retrieval._query_trade_requests(
                tickers=tool_input.get("tickers", []),
                classified=classified,
                steps=steps,
            )
            return _safe_json_dumps(rows)

        elif tool_name == "get_stock_history":
            rows = await retrieval._query_stock_history(
                tickers=tool_input.get("tickers", []),
                classified=classified,
                steps=steps,
            )
            return _safe_json_dumps(rows)

        elif tool_name == "get_guidance":
            # Temporarily override fiscal_periods on classified for the query
            original_periods = classified.fiscal_periods
            if tool_input.get("fiscal_periods"):
                classified.fiscal_periods = tool_input["fiscal_periods"]
            rows = await retrieval._query_guidance(
                tickers=tool_input.get("tickers", []),
                classified=classified,
                steps=steps,
            )
            classified.fiscal_periods = original_periods
            return _safe_json_dumps(rows)

        elif tool_name == "get_alt_data":
            rows = await retrieval._query_alt_data(
                ticker=tool_input.get("ticker", ""),
                data_types=tool_input.get("data_types", []),
                date_from=tool_input.get("date_from"),
                date_to=tool_input.get("date_to"),
                limit=tool_input.get("limit"),
                steps=steps,
            )
            return _safe_json_dumps(rows)

        elif tool_name == "get_model_outputs":
            rows = await retrieval._query_model_outputs(
                tickers=tool_input.get("tickers", []),
                classified=classified,
                steps=steps,
            )
            return _safe_json_dumps(rows)

        elif tool_name == "get_workflow_registry":
            # Temporarily override workflow_name on classified for the query
            original_name = classified.workflow_name
            if tool_input.get("workflow_name"):
                classified.workflow_name = tool_input["workflow_name"]
            rows = await retrieval._query_workflow_registry(
                tickers=[],
                classified=classified,
                steps=steps,
            )
            classified.workflow_name = original_name
            return _safe_json_dumps(rows)

        elif tool_name == "run_workflow":
            from app.workflows.registry import get_workflow
            wf_name = tool_input.get("workflow_name", "")
            wf_inputs = tool_input.get("inputs", {})

            workflow = await get_workflow(wf_name)
            if workflow is None:
                return _safe_json_dumps({
                    "error": f"Workflow '{wf_name}' not found or inactive.",
                })

            # Extract user_id from classified context (set by router)
            user_id = getattr(classified, "_user_id", "anonymous")
            triggered_by = user_id

            result = await workflow.run(
                inputs=wf_inputs,
                triggered_by=triggered_by,
                user_id=user_id,
                steps=steps,
            )
            return _safe_json_dumps(result)

        elif tool_name == "get_workflow_output":
            wf_name = tool_input.get("workflow_name", "")
            ticker = tool_input.get("ticker", "").upper() if tool_input.get("ticker") else None

            # Map workflow_name → output table
            from app.workflows.registry import get_workflow_registry_entry
            entry = await get_workflow_registry_entry(wf_name)
            if not entry:
                return _safe_json_dumps({
                    "error": f"Workflow '{wf_name}' not found in registry.",
                })

            output_table = entry["output_table"]
            # Validate table name to prevent injection (only allow known pattern)
            if not output_table.startswith("workflow_outputs_"):
                return _safe_json_dumps({"error": "Invalid output table."})

            from app.mode2.db import get_conn as get_mode2_conn
            async with get_mode2_conn() as conn:
                if ticker:
                    row = await conn.fetchrow(
                        f"SELECT * FROM {output_table} "
                        f"WHERE ticker = $1 "
                        f"ORDER BY created_at DESC LIMIT 1",
                        ticker,
                    )
                else:
                    # Tickerless workflows (e.g. docs_sync)
                    row = await conn.fetchrow(
                        f"SELECT * FROM {output_table} "
                        f"ORDER BY created_at DESC LIMIT 1",
                    )
            if not row:
                label = f" for {ticker}" if ticker else ""
                return _safe_json_dumps({
                    "message": f"No prior {wf_name} output found{label}.",
                })
            return _safe_json_dumps(dict(row))

        elif tool_name == "model_edit":
            ticker = (tool_input.get("ticker") or "").upper()
            assumption_key = tool_input.get("assumption_key", "")
            scenario = tool_input.get("scenario", "base")
            new_value = tool_input.get("new_value")
            period = tool_input.get("period")

            if not ticker or not assumption_key or new_value is None:
                return _safe_json_dumps({
                    "error": "ticker, assumption_key, and new_value are required.",
                })

            # 1. Read current assumptions from model_outputs
            from app.mode2.db import get_conn as get_mode2_conn
            async with get_mode2_conn() as conn:
                rows = await conn.fetch(
                    """SELECT DISTINCT ON (metric, scenario)
                              metric, scenario, value
                       FROM model_outputs
                       WHERE ticker = $1 AND sheet = 'assumptions'
                       ORDER BY metric, scenario, as_of_date DESC""",
                    ticker,
                )

            if not rows:
                return _safe_json_dumps({
                    "error": f"No existing model found for {ticker}. Generate one first.",
                })

            # 2. Build assumptions dict
            assumptions: dict[str, dict[str, float]] = {}
            for r in rows:
                metric = r["metric"]
                scen = r["scenario"]
                val = float(r["value"]) if r["value"] is not None else 0.0
                if metric not in assumptions:
                    assumptions[metric] = {}
                assumptions[metric][scen] = val

            # 3. Apply the edit
            if assumption_key not in assumptions:
                return _safe_json_dumps({
                    "error": f"Assumption '{assumption_key}' not found in current model. "
                             f"Available: {sorted(assumptions.keys())}",
                })

            assumptions[assumption_key][scenario] = float(new_value)

            # 4. Flatten to base_assumptions override dict
            base_overrides = {
                metric: vals.get("base")
                for metric, vals in assumptions.items()
                if vals.get("base") is not None
            }

            # 5. Trigger regeneration
            from app.workflows.financial_model_generation import FinancialModelGenerationWorkflow
            workflow = FinancialModelGenerationWorkflow()

            user_id = getattr(classified, "_user_id", "anonymous")

            result = await workflow.run(
                inputs={
                    "ticker": ticker,
                    "base_assumptions": base_overrides,
                },
                triggered_by=user_id,
                user_id=user_id,
                steps=steps,
            )

            return _safe_json_dumps({
                "message": (
                    f"Model updated. New version {result.get('version')} generated. "
                    f"{result.get('model_outputs_rows', 0)} rows written to model_outputs."
                ),
                "ticker": ticker,
                "version": result.get("version"),
                "assumption_edited": assumption_key,
                "scenario": scenario,
                "new_value": new_value,
                "s3_path": result.get("s3_path"),
            }, default=str)

        else:
            return _safe_json_dumps({
                "error": f"Unknown tool: {tool_name}. This tool does not exist.",
            })

    except Exception as e:
        friendly_label = _TOOL_LABELS.get(tool_name, tool_name.replace("_", " "))
        logger.error(
            "tool_execution_failed tool=%s ticker=%s error=%s\n%s",
            tool_name,
            tool_input.get("tickers", tool_input.get("ticker")),
            str(e),
            _traceback.format_exc(),
        )
        return _safe_json_dumps({
            "error": True,
            "tool_name": tool_name,
            "user_message": f"Could not retrieve {friendly_label} data.",
        })
