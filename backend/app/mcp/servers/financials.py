"""Financials MCP server — reported actuals, price history, and guidance.

Replaces the legacy get_financial_metrics, get_stock_history, and
get_guidance tools with native MCP implementations that delegate
to existing retrieval functions.
"""
from __future__ import annotations

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


class FinancialsServer(MCPServer):
    """Historical financial metrics, price history, and management guidance."""

    namespace = "financials"
    display_name = "Financials"
    description = (
        "Historical financial metrics, price history, and management guidance. "
        "Sourced from financial_metrics, stock_history, and guidance tables."
    )

    def list_tools(self) -> list[MCPTool]:
        return [
            MCPTool(
                name="get_financial_metrics",
                namespace=self.namespace,
                description=(
                    "Get reported company financials from financial_metrics table. "
                    "Returns actual reported figures — not forward estimates.\n\n"
                    "Pass a topic string to auto-select relevant metrics, or pass "
                    "explicit metric names.\n\n"
                    "NEVER use for portfolio P&L — use get_daily_pnl instead."
                ),
                parameters=[
                    MCPToolParameter(
                        name="tickers",
                        type="array",
                        description="Ticker symbols.",
                        required=True,
                    ),
                    MCPToolParameter(
                        name="topic",
                        type="string",
                        description=(
                            "Topic to auto-select metrics. Examples: 'revenue margins', "
                            "'debt balance sheet', 'cash flow capex'. "
                            "Ignored if metrics is provided."
                        ),
                        required=False,
                    ),
                    MCPToolParameter(
                        name="metrics",
                        type="array",
                        description=(
                            "Explicit metric names. Options: total_revenue, gross_profit, "
                            "operating_income, net_income, diluted_eps, ebitda, "
                            "free_cash_flow, operating_cash_flow, capital_expenditure, "
                            "total_assets, total_debt, cash_and_cash_equivalents. "
                            "Overrides topic if both provided."
                        ),
                        required=False,
                    ),
                    MCPToolParameter(
                        name="fiscal_periods",
                        type="array",
                        description="Optional fiscal period filter.",
                        required=False,
                    ),
                ],
                preferred_presentation="table",
            ),
            MCPTool(
                name="get_stock_history",
                namespace=self.namespace,
                description=(
                    "Get stock price history from stock_history table.\n\n"
                    "Returns close price and EPS actuals by date.\n\n"
                    "NEVER use for portfolio P&L — use get_daily_pnl instead.\n\n"
                    "No citation required for stock price data."
                ),
                parameters=[
                    MCPToolParameter(
                        name="tickers",
                        type="array",
                        description="Ticker symbols.",
                        required=True,
                    ),
                    MCPToolParameter(
                        name="lookback_days",
                        type="number",
                        description="Days of history. Default 365.",
                        required=False,
                        default=365,
                        min_value=7,
                        max_value=1825,
                    ),
                ],
                preferred_presentation="chart",
                chart_config={
                    "type": "line",
                    "x_column": "date",
                    "y_column": "close",
                    "series_column": "ticker",
                    "title": "Price History",
                    "y_label": "Price ($)",
                    "formatters": {"close": "currency"},
                },
            ),
            MCPTool(
                name="get_guidance",
                namespace=self.namespace,
                description=(
                    "Get management guidance from guidance table.\n\n"
                    "Forward-looking statements from management about expected "
                    "performance. Different from analyst estimates — this is what "
                    "the company itself has said."
                ),
                parameters=[
                    MCPToolParameter(
                        name="tickers",
                        type="array",
                        description="Ticker symbols.",
                        required=True,
                    ),
                    MCPToolParameter(
                        name="fiscal_periods",
                        type="array",
                        description="Fiscal periods e.g. ['2026Q1','2026A']. Empty = all.",
                        required=False,
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
        if tool_name == "get_financial_metrics":
            return await self._get_financial_metrics(params, steps)
        elif tool_name == "get_stock_history":
            return await self._get_stock_history(params, steps)
        elif tool_name == "get_guidance":
            return await self._get_guidance(params, steps)
        return MCPToolResult(
            tool_name=tool_name,
            namespace=self.namespace,
            rows=[],
            row_count=0,
            columns=[],
            preferred_presentation="table",
            error=f"Unknown tool: {tool_name}",
        )

    async def _get_financial_metrics(
        self,
        params: dict,
        steps: Any | None = None,
    ) -> MCPToolResult:
        """Delegate to _structured_query() in retrieval.py."""
        from app.mode2.retrieval import _structured_query

        tickers = params.get("tickers") or []
        if not tickers:
            return MCPToolResult(
                tool_name="get_financial_metrics",
                namespace=self.namespace,
                rows=[], row_count=0, columns=[],
                preferred_presentation="table",
                error="tickers is required",
            )

        # Use explicit metrics as topic override if provided
        explicit_metrics = params.get("metrics")
        if explicit_metrics:
            topic = " ".join(explicit_metrics)
        else:
            topic = params.get("topic") or "revenue margins"

        rows = await _structured_query(
            tickers=tickers,
            topic=topic,
            fiscal_periods=params.get("fiscal_periods"),
            steps=steps,
        )

        results = [
            {k: _serialize_value(v) for k, v in r.items()}
            for r in rows
        ]

        return MCPToolResult(
            tool_name="get_financial_metrics",
            namespace=self.namespace,
            rows=results,
            row_count=len(results),
            columns=["metric_name", "period_end", "period_type", "value"],
            preferred_presentation="table",
        )

    async def _get_stock_history(
        self,
        params: dict,
        steps: Any | None = None,
    ) -> MCPToolResult:
        """Delegate to _query_stock_history() in retrieval.py."""
        from app.mode2.retrieval import _query_stock_history

        tickers = params.get("tickers") or []
        if not tickers:
            return MCPToolResult(
                tool_name="get_stock_history",
                namespace=self.namespace,
                rows=[], row_count=0, columns=[],
                preferred_presentation="chart",
                error="tickers is required",
            )

        lookback_days = int(params.get("lookback_days") or 365)

        rows = await _query_stock_history(
            tickers=tickers,
            lookback_days=lookback_days,
            steps=steps,
        )

        results = [
            {k: _serialize_value(v) for k, v in r.items()}
            for r in rows
        ]

        ticker_label = tickers[0] if len(tickers) == 1 else ", ".join(tickers[:3])

        return MCPToolResult(
            tool_name="get_stock_history",
            namespace=self.namespace,
            rows=results,
            row_count=len(results),
            columns=["ticker", "date", "close", "eps_estimate", "eps_actual"],
            preferred_presentation="chart",
            chart_config={
                "type": "line",
                "x_column": "date",
                "y_column": "close",
                "series_column": "ticker",
                "title": f"{ticker_label} Price History",
                "y_label": "Price ($)",
                "formatters": {"close": "currency"},
            },
        )

    async def _get_guidance(
        self,
        params: dict,
        steps: Any | None = None,
    ) -> MCPToolResult:
        """Delegate to _query_guidance() in retrieval.py."""
        from app.mode2.retrieval import _query_guidance
        from app.mode2.models import ClassifiedQuery

        tickers = params.get("tickers") or []
        if not tickers:
            return MCPToolResult(
                tool_name="get_guidance",
                namespace=self.namespace,
                rows=[], row_count=0, columns=[],
                preferred_presentation="table",
                error="tickers is required",
            )

        classified = ClassifiedQuery(
            query_type="single_ticker_quantitative",
            tickers=tickers,
            fiscal_periods=params.get("fiscal_periods") or [],
        )

        rows = await _query_guidance(
            tickers=tickers,
            classified=classified,
            steps=steps,
        )

        results = [
            {k: _serialize_value(v) for k, v in r.items()}
            for r in rows
        ]

        return MCPToolResult(
            tool_name="get_guidance",
            namespace=self.namespace,
            rows=results,
            row_count=len(results),
            columns=[
                "ticker", "metric", "period", "value", "unit",
                "guidance_type", "source", "issued_date",
            ],
            preferred_presentation="table",
        )
