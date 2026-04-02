"""Search & Research MCP server — semantic document search and universe lookup.

Replaces the legacy search_documents tool with a native MCP implementation
that delegates to _vector_search() in retrieval.py. Also adds search_universe
for finding tickers by name, sector, or industry.

search_documents requires query_embedding from kwargs, which the generator
pre-computes once per user message and passes through the registry.
"""
from __future__ import annotations

import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog

from ..base import MCPServer
from ..types import MCPTool, MCPToolParameter, MCPToolResult

logger = structlog.get_logger(__name__)


def _serialize_value(v: Any) -> Any:
    """Convert DB types to JSON-safe values."""
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, UUID):
        return str(v)
    return v


class SearchServer(MCPServer):
    """Search and retrieve content from research documents and stock universe."""

    namespace = "search"
    display_name = "Research & Search"
    description = (
        "Search and retrieve content from earnings transcripts, SEC filings, "
        "analyst notes, and other research documents. Powered by pgvector "
        "semantic similarity search on the chunks table."
    )

    def list_tools(self) -> list[MCPTool]:
        return [
            MCPTool(
                name="search_documents",
                namespace=self.namespace,
                description=(
                    "Search financial document chunks via vector similarity. "
                    "Returns relevant passages from earnings transcripts, SEC filings "
                    "(10-K, 10-Q, 8-K), analyst notes, buyside notes, and sellside notes. "
                    "You MUST specify doc_types to filter which document types to search."
                    "\n\nSOURCE ISOLATION RULES (critical):\n"
                    "- For internal analyst note queries: use doc_types=['analyst_note'] ONLY. "
                    "NEVER include 'sellside_note' or 'buyside_note' in the same call.\n"
                    "- For sellside note queries: use doc_types=['sellside_note'] ONLY.\n"
                    "- For buyside note queries: use doc_types=['buyside_note'] ONLY.\n"
                    "- For general qualitative queries: use "
                    "doc_types=['earnings_transcript'] or doc_types=['10-K','10-Q','8-K'].\n"
                    "\nEvery passage returned must be cited inline using "
                    "[TICKER | DOCUMENT_TYPE | PERIOD | SECTION] format."
                ),
                parameters=[
                    MCPToolParameter(
                        name="tickers",
                        type="array",
                        description="Ticker symbols to search. Empty array searches all tickers.",
                        required=True,
                    ),
                    MCPToolParameter(
                        name="doc_types",
                        type="array",
                        description=(
                            "Document types to search. Required. Options: "
                            "earnings_transcript, 10-K, 10-Q, 8-K, "
                            "analyst_note, sellside_note, buyside_note."
                        ),
                        required=True,
                    ),
                    MCPToolParameter(
                        name="limit_per_ticker",
                        type="number",
                        description=(
                            "Max chunks per ticker. Default 6 for single ticker, "
                            "3 for multi-ticker."
                        ),
                        required=False,
                        default=6,
                        min_value=1,
                        max_value=20,
                    ),
                    MCPToolParameter(
                        name="section_type",
                        type="string",
                        description=(
                            "Optional section filter (e.g. 'cfo_remarks', "
                            "'risk_factors', 'ceo_remarks')."
                        ),
                        required=False,
                    ),
                    MCPToolParameter(
                        name="fiscal_periods",
                        type="array",
                        description="Optional fiscal period filter (e.g. ['Q4_2024', 'Q3_2024']).",
                        required=False,
                    ),
                ],
                preferred_presentation="text",
            ),
            MCPTool(
                name="search_universe",
                namespace=self.namespace,
                description=(
                    "Search the stock universe for tickers matching criteria. "
                    "Use to find tickers by name, sector, or industry.\n\n"
                    "Use for:\n"
                    "- 'Find all restaurant stocks'\n"
                    "- 'What semiconductor companies are in the universe?'\n"
                    "- 'Find NVIDIA's ticker'"
                ),
                parameters=[
                    MCPToolParameter(
                        name="query",
                        type="string",
                        description="Company name, sector, industry, or keyword.",
                        required=True,
                    ),
                    MCPToolParameter(
                        name="sector",
                        type="string",
                        description=(
                            "Filter by GICS sector e.g. 'Technology', "
                            "'Consumer Discretionary'."
                        ),
                        required=False,
                    ),
                    MCPToolParameter(
                        name="industry",
                        type="string",
                        description="Filter by industry e.g. 'Restaurants', 'Software'.",
                        required=False,
                    ),
                    MCPToolParameter(
                        name="limit",
                        type="number",
                        description="Max results. Default 20.",
                        required=False,
                        default=20,
                        min_value=1,
                        max_value=100,
                    ),
                ],
                preferred_presentation="table",
            ),
        ]

    async def call_tool(
        self,
        tool_name: str,
        params: dict,
        **kwargs: object,
    ) -> MCPToolResult:
        steps = kwargs.get("steps")
        if tool_name == "search_documents":
            query_embedding = kwargs.get("query_embedding") or []
            return await self._search_documents(params, query_embedding, steps)
        elif tool_name == "search_universe":
            return await self._search_universe(params, steps)
        return MCPToolResult(
            tool_name=tool_name,
            namespace=self.namespace,
            rows=[],
            row_count=0,
            columns=[],
            preferred_presentation="text",
            error=f"Unknown tool: {tool_name}",
        )

    async def _search_documents(
        self,
        params: dict,
        query_embedding: Any,
        steps: Any | None = None,
    ) -> MCPToolResult:
        """Delegate to existing _vector_search() in retrieval.py."""
        from app.mode2.retrieval import _vector_search

        tickers = params.get("tickers") or []
        doc_types = params.get("doc_types") or []
        limit_per_ticker = int(params.get("limit_per_ticker") or 6)
        section_type = params.get("section_type")
        fiscal_periods = params.get("fiscal_periods")

        if not query_embedding:
            return MCPToolResult(
                tool_name="search_documents",
                namespace=self.namespace,
                rows=[],
                row_count=0,
                columns=[],
                preferred_presentation="text",
                error="No query embedding available for document search.",
            )

        chunks = await _vector_search(
            query_embedding=query_embedding,
            tickers=tickers,
            limit_per_ticker=limit_per_ticker,
            section_type=section_type,
            fiscal_periods=fiscal_periods,
            doc_types=doc_types,
            steps=steps,
        )

        rows = [c.model_dump() for c in chunks]

        columns = [
            "ticker", "document_type", "fiscal_period",
            "section_name", "section_type",
            "chunk_text", "word_count", "similarity",
        ]

        return MCPToolResult(
            tool_name="search_documents",
            namespace=self.namespace,
            rows=rows,
            row_count=len(rows),
            columns=columns,
            preferred_presentation="text",
        )

    async def _search_universe(
        self,
        params: dict,
        steps: Any | None = None,
    ) -> MCPToolResult:
        """Search stocks table for matching tickers."""
        from app.mode2.db import get_conn
        from app.mode2.steps import format_sql

        query = params.get("query", "")
        sector = params.get("sector")
        industry = params.get("industry")
        limit = int(params.get("limit") or 20)

        if not query and not sector and not industry:
            return MCPToolResult(
                tool_name="search_universe",
                namespace=self.namespace,
                rows=[],
                row_count=0,
                columns=[],
                preferred_presentation="table",
                error="At least one of query, sector, or industry is required.",
            )

        t0 = time.time()

        conditions: list[str] = []
        query_params: list[Any] = []
        idx = 1

        if query:
            conditions.append(
                f"(ticker ILIKE ${idx} OR company_name ILIKE ${idx})"
            )
            query_params.append(f"%{query}%")
            idx += 1

        if sector:
            conditions.append(f"sector ILIKE ${idx}")
            query_params.append(f"%{sector}%")
            idx += 1

        if industry:
            conditions.append(f"industry ILIKE ${idx}")
            query_params.append(f"%{industry}%")
            idx += 1

        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        sql = f"""SELECT ticker, company_name, sector, industry, exchange
            FROM stocks
            {where}
            ORDER BY ticker
            LIMIT ${idx}"""
        query_params.append(limit)

        async with get_conn() as conn:
            rows = await conn.fetch(sql, *query_params)

        results = [
            {k: _serialize_value(v) for k, v in dict(r).items()}
            for r in rows
        ]
        duration_ms = int((time.time() - t0) * 1000)

        if steps:
            steps.add(
                label="Searching universe",
                detail=f"stocks: {len(results)} matches",
                source="supabase",
                duration_ms=duration_ms,
                result_summary=f"{len(results)} tickers found",
                query=format_sql(sql, query_params),
            )

        return MCPToolResult(
            tool_name="search_universe",
            namespace=self.namespace,
            rows=results,
            row_count=len(results),
            columns=["ticker", "company_name", "sector", "industry", "exchange"],
            preferred_presentation="table",
        )
