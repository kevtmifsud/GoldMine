"""Estimates MCP server — real MCP implementation for forward estimates.

Replaces the legacy get_estimates tool with a native MCP implementation
that calls _query_estimates() from retrieval.py for the snapshot tool,
and queries daily_estimates directly for the history/revision tool.

Tool names kept compatible: Claude calls "get_estimates" by name,
the registry routes it here via the legacy name fallback.
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


class EstimatesServer(MCPServer):
    """Forward estimates from all sources — consensus, buyside, internal, sellside.

    Always returns individual rows per analyst/source, never aggregated.
    Includes YoY vs prior year actual enrichment.
    """

    namespace = "estimates"
    display_name = "Estimates"
    description = (
        "Forward estimates from all sources — consensus, buyside "
        "(individual analysts), internal, and sellside (individual analysts). "
        "Always returns individual rows per analyst/source, never aggregated. "
        "Includes YoY vs prior year actual enrichment."
    )

    def list_tools(self) -> list[MCPTool]:
        return [
            MCPTool(
                name="get_estimates",
                namespace=self.namespace,
                description=(
                    "Get forward estimates for one or many tickers from all sources."
                    "\n\nReturns individual rows — one per source/firm/analyst. "
                    "Never averages or aggregates."
                    "\n\nUse cases:\n"
                    "Single ticker deep dive:\n"
                    "  tickers=['CMG'], periods=['2027A']\n"
                    "  → all analysts for CMG 2027A\n"
                    "\nMulti-ticker screening:\n"
                    "  tickers=['CMG','SBUX','DPZ'], sources=['consensus']\n"
                    "  → consensus for all three\n"
                    "\nReturns per row:\n"
                    "- ticker, metric, period\n"
                    "- source: consensus/buyside/internal/sellside\n"
                    "- firm, analyst_name\n"
                    "- value, unit\n"
                    "- yoy_vs_actual: % vs prior year actual\n"
                    "- prior_year_actual\n"
                    "- as_of_date, staleness_days"
                ),
                parameters=[
                    MCPToolParameter(
                        name="tickers",
                        type="array",
                        description=(
                            "Ticker symbols. One for deep dive, many for screening. "
                            "Required — pass at least one ticker."
                        ),
                        required=True,
                    ),
                    MCPToolParameter(
                        name="metrics",
                        type="array",
                        description=(
                            "Metrics to retrieve. Options: total_revenue, diluted_eps, "
                            "ebitda, gross_profit, operating_income, free_cash_flow. "
                            "Aliases: eps, revenue, fcf. Empty = all metrics."
                        ),
                        required=False,
                    ),
                    MCPToolParameter(
                        name="periods",
                        type="array",
                        description=(
                            "Fiscal periods e.g. ['2026Q1','2026A']. "
                            "Accepts FY2026, 2026, Q4_2026 formats. Empty = all periods."
                        ),
                        required=False,
                    ),
                    MCPToolParameter(
                        name="sources",
                        type="array",
                        description=(
                            "Filter by source: consensus, buyside, internal, sellside. "
                            "Empty = all sources."
                        ),
                        required=False,
                    ),
                ],
                preferred_presentation="table",
            ),
            MCPTool(
                name="get_estimate_history",
                namespace=self.namespace,
                description=(
                    "Get how estimates evolved over time for a single ticker + "
                    "metric + period. Returns one row per as_of_date showing how "
                    "each source's estimate changed."
                    "\n\nUse for 'Plot Over Time' and revision trend analysis."
                ),
                parameters=[
                    MCPToolParameter(
                        name="ticker",
                        type="string",
                        description="Single ticker symbol.",
                        required=True,
                    ),
                    MCPToolParameter(
                        name="metric",
                        type="string",
                        description=(
                            "Single metric e.g. total_revenue, diluted_eps."
                        ),
                        required=True,
                    ),
                    MCPToolParameter(
                        name="period",
                        type="string",
                        description="Single fiscal period e.g. 2026A, 2026Q1.",
                        required=True,
                    ),
                    MCPToolParameter(
                        name="sources",
                        type="array",
                        description=(
                            "Filter by source. Empty = all sources."
                        ),
                        required=False,
                    ),
                    MCPToolParameter(
                        name="lookback_days",
                        type="number",
                        description="How many days of history. Default 365.",
                        required=False,
                        default=365,
                    ),
                ],
                preferred_presentation="chart",
                chart_config={
                    "type": "line",
                    "x_column": "as_of_date",
                    "y_column": "value",
                    "series_column": "source_label",
                    "title": "Estimate Revisions",
                    "y_label": "Estimate Value",
                },
            ),
        ]

    async def call_tool(
        self,
        tool_name: str,
        params: dict,
        **kwargs: object,
    ) -> MCPToolResult:
        steps = kwargs.get("steps")
        if tool_name == "get_estimates":
            return await self._get_estimates(params, steps)
        elif tool_name == "get_estimate_history":
            return await self._get_estimate_history(params, steps)
        return MCPToolResult(
            tool_name=tool_name,
            namespace=self.namespace,
            rows=[],
            row_count=0,
            columns=[],
            preferred_presentation="table",
            error=f"Unknown tool: {tool_name}",
        )

    async def _get_estimates(
        self,
        params: dict,
        steps: Any | None = None,
    ) -> MCPToolResult:
        """Call the existing _query_estimates() from retrieval.py —
        reuse all logic including YoY enrichment."""
        from app.mode2.retrieval import _query_estimates

        tickers = params.get("tickers") or []
        metrics = params.get("metrics") or None
        periods = params.get("periods") or None
        sources = params.get("sources") or None

        rows = await _query_estimates(
            tickers=tickers,
            metrics=metrics if metrics else None,
            periods=periods if periods else None,
            sources=sources if sources else None,
            steps=steps,
        )

        columns = [
            "ticker", "metric", "period",
            "period_start_date", "period_end_date",
            "source", "firm", "analyst_name",
            "value", "unit",
            "yoy_vs_actual", "prior_year_actual", "prior_year_period",
            "estimate_date", "as_of_date", "staleness_days",
        ]

        return MCPToolResult(
            tool_name="get_estimates",
            namespace=self.namespace,
            rows=rows,
            row_count=len(rows),
            columns=columns,
            preferred_presentation="table",
        )

    async def _get_estimate_history(
        self,
        params: dict,
        steps: Any | None = None,
    ) -> MCPToolResult:
        """Query daily_estimates across all as_of_dates for a single
        ticker+metric+period to show how estimates evolved over time."""
        from app.mode2.db import get_conn
        from app.mode2.retrieval import _normalize_estimate_period
        from app.mode2.steps import format_sql

        ticker = (params.get("ticker") or "").upper()
        metric = params.get("metric") or ""
        period = params.get("period") or ""
        sources = params.get("sources") or []
        lookback_days = int(params.get("lookback_days") or 365)

        if not all([ticker, metric, period]):
            return MCPToolResult(
                tool_name="get_estimate_history",
                namespace=self.namespace,
                rows=[],
                row_count=0,
                columns=[],
                preferred_presentation="chart",
                error="ticker, metric, and period are all required",
            )

        period = _normalize_estimate_period(period)
        t0 = time.time()

        conditions = [
            "ticker = $1",
            "metric = $2",
            "period = $3",
            f"as_of_date >= CURRENT_DATE - INTERVAL '{lookback_days} days'",
        ]
        query_params: list[Any] = [ticker, metric, period]
        idx = 4

        if sources:
            conditions.append(f"source = ANY(${idx})")
            query_params.append(sources)
            idx += 1

        where = " AND ".join(conditions)

        sql = f"""SELECT
                as_of_date, source, firm, analyst_name,
                value, unit, estimate_date, staleness_days,
                CASE
                    WHEN source = 'consensus' THEN 'Consensus'
                    WHEN source = 'internal' THEN 'Internal'
                    WHEN firm IS NOT NULL AND analyst_name IS NOT NULL
                        THEN firm || ' / ' || analyst_name
                    WHEN firm IS NOT NULL THEN firm
                    ELSE source
                END as source_label
            FROM daily_estimates
            WHERE {where}
            ORDER BY as_of_date ASC, source, firm, analyst_name"""

        async with get_conn() as conn:
            rows = await conn.fetch(sql, *query_params)

        results = [
            {k: _serialize_value(v) for k, v in dict(r).items()}
            for r in rows
        ]

        duration_ms = int((time.time() - t0) * 1000)
        metric_label = metric.replace("_", " ").title()

        if steps:
            steps.add(
                label="Fetching estimate history",
                detail=(
                    f"daily_estimates: {ticker} {metric} {period} — "
                    f"{len(results)} rows"
                ),
                source="supabase",
                duration_ms=duration_ms,
                result_summary=f"{len(results)} history rows",
                query=format_sql(sql, query_params),
            )

        title = f"{ticker} {metric_label} Estimate Revisions — {period}"

        columns = [
            "as_of_date", "source", "source_label", "firm",
            "analyst_name", "value", "unit",
            "estimate_date", "staleness_days",
        ]

        return MCPToolResult(
            tool_name="get_estimate_history",
            namespace=self.namespace,
            rows=results,
            row_count=len(results),
            columns=columns,
            preferred_presentation="chart",
            chart_config={
                "type": "line",
                "x_column": "as_of_date",
                "y_column": "value",
                "series_column": "source_label",
                "title": title,
                "y_label": metric_label,
            },
            metadata={
                "ticker": ticker,
                "metric": metric,
                "period": period,
            },
        )
