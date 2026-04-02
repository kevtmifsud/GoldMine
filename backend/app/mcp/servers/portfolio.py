"""Portfolio MCP server — positions, P&L, concentration, and risk.

Replaces the legacy get_daily_pnl, get_portfolio_concentration, and
get_portfolio_risk tools with native MCP implementations that delegate
to the existing retrieval functions.
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


class PortfolioServer(MCPServer):
    """Portfolio positions, P&L, concentration, and risk data.

    Covers Flagship and Long Only portfolios.
    Never aggregates across portfolios — always presented separately.
    """

    namespace = "portfolio"
    display_name = "Portfolio"
    description = (
        "Portfolio positions, P&L, concentration, and risk data. "
        "Covers Flagship and Long Only portfolios. "
        "Never aggregates across portfolios — always presented separately."
    )

    def list_tools(self) -> list[MCPTool]:
        return [
            MCPTool(
                name="get_daily_pnl",
                namespace=self.namespace,
                description=(
                    "Get portfolio P&L from daily_pnl table. Returns position-level "
                    "or portfolio-level P&L.\n\n"
                    "Portfolios are NEVER mixed or aggregated — always shown separately.\n\n"
                    "Key fields: unrealized_pnl (mark-to-market on open positions), "
                    "daily_realized_pnl (closed today only), ytd_pnl (Jan 1 to today), "
                    "itd_pnl (inception to date), market_value, daily_return %.\n\n"
                    "For portfolio queries, ONLY use portfolio tools. "
                    "NEVER combine with get_financial_metrics or get_stock_history.\n\n"
                    "No citation required for portfolio data."
                ),
                parameters=[
                    MCPToolParameter(
                        name="portfolio",
                        type="string",
                        description=(
                            "Which portfolio. 'Flagship', 'Long Only', or 'all' for both "
                            "separately. Default 'all'."
                        ),
                        required=False,
                        default="all",
                        enum=["Flagship", "Long Only", "all"],
                    ),
                    MCPToolParameter(
                        name="ticker",
                        type="string",
                        description="Filter to single ticker. Omit for all positions.",
                        required=False,
                    ),
                    MCPToolParameter(
                        name="date",
                        type="string",
                        description="Specific date YYYY-MM-DD. Default = most recent.",
                        required=False,
                    ),
                    MCPToolParameter(
                        name="order_by",
                        type="string",
                        description="Sort column. Default 'unrealized_pnl'.",
                        required=False,
                        default="unrealized_pnl",
                    ),
                    MCPToolParameter(
                        name="order_dir",
                        type="string",
                        description="Sort direction. Default 'desc'.",
                        required=False,
                        default="desc",
                        enum=["asc", "desc"],
                    ),
                    MCPToolParameter(
                        name="limit",
                        type="number",
                        description="Max rows. Default 100.",
                        required=False,
                        default=100,
                    ),
                    MCPToolParameter(
                        name="group_by",
                        type="array",
                        description=(
                            "Columns to group by for aggregation: "
                            "portfolio, side, sector, industry, ticker, date."
                        ),
                        required=False,
                    ),
                ],
                preferred_presentation="table",
            ),
            MCPTool(
                name="get_pnl_history",
                namespace=self.namespace,
                description=(
                    "Get portfolio P&L over time as a time series. Returns one row "
                    "per date per portfolio showing P&L trend.\n\n"
                    "Use for 'Plot Over Time' on portfolio P&L questions."
                ),
                parameters=[
                    MCPToolParameter(
                        name="portfolio",
                        type="string",
                        description="'Flagship', 'Long Only', or 'all'. Default 'all'.",
                        required=False,
                        default="all",
                        enum=["Flagship", "Long Only", "all"],
                    ),
                    MCPToolParameter(
                        name="ticker",
                        type="string",
                        description="Single ticker for position-level history. Omit for portfolio total.",
                        required=False,
                    ),
                    MCPToolParameter(
                        name="metric",
                        type="string",
                        description=(
                            "Which metric to plot. Options: itd_pnl, ytd_pnl, "
                            "unrealized_pnl, daily_return. Default 'itd_pnl'."
                        ),
                        required=False,
                        default="itd_pnl",
                        enum=["itd_pnl", "ytd_pnl", "unrealized_pnl", "daily_return"],
                    ),
                    MCPToolParameter(
                        name="lookback_days",
                        type="number",
                        description="Days of history. Default 365.",
                        required=False,
                        default=365,
                    ),
                ],
                preferred_presentation="chart",
                chart_config={
                    "type": "line",
                    "x_column": "date",
                    "y_column": "value",
                    "series_column": "portfolio",
                    "title": "Portfolio P&L Over Time",
                    "y_label": "P&L ($)",
                    "formatters": {"value": "millions"},
                },
            ),
            MCPTool(
                name="get_portfolio_concentration",
                namespace=self.namespace,
                description=(
                    "Get portfolio concentration — position weights, sector weights, "
                    "industry weights, and market neutrality compliance.\n\n"
                    "Portfolio values: 'Flagship', 'Long Only', or omit for both.\n\n"
                    "No citation required for portfolio data."
                ),
                parameters=[
                    MCPToolParameter(
                        name="portfolio",
                        type="string",
                        description="'Flagship', 'Long Only', or omit for both.",
                        required=False,
                        enum=["Flagship", "Long Only"],
                    ),
                    MCPToolParameter(
                        name="ticker",
                        type="string",
                        description="Filter to single ticker.",
                        required=False,
                    ),
                ],
                preferred_presentation="table",
            ),
            MCPTool(
                name="get_portfolio_risk",
                namespace=self.namespace,
                description=(
                    "Get portfolio risk data — beta exposures and weighted beta "
                    "contributions.\n\n"
                    "Portfolio values: 'Flagship', 'Long Only', or omit for both.\n\n"
                    "No citation required for portfolio data."
                ),
                parameters=[
                    MCPToolParameter(
                        name="portfolio",
                        type="string",
                        description="'Flagship', 'Long Only', or omit for both.",
                        required=False,
                        enum=["Flagship", "Long Only"],
                    ),
                    MCPToolParameter(
                        name="ticker",
                        type="string",
                        description="Filter to single ticker.",
                        required=False,
                    ),
                ],
                preferred_presentation="table",
            ),
            MCPTool(
                name="get_trade_requests",
                namespace=self.namespace,
                description=(
                    "Get trade requests and order history from the trade_requests table. "
                    "Returns pending, executed, and cancelled orders.\n\n"
                    "Use for:\n"
                    "- 'Show me pending trades'\n"
                    "- 'What trades were executed today?'\n"
                    "- 'Show trade history for AAPL'\n\n"
                    "No citation required for trade request data."
                ),
                parameters=[
                    MCPToolParameter(
                        name="ticker",
                        type="string",
                        description="Filter to single ticker. Empty = all tickers.",
                        required=False,
                    ),
                    MCPToolParameter(
                        name="status",
                        type="string",
                        description=(
                            "Filter by status: pending, executed, cancelled. "
                            "Empty = all statuses."
                        ),
                        required=False,
                        enum=["pending", "executed", "cancelled"],
                    ),
                    MCPToolParameter(
                        name="portfolio",
                        type="string",
                        description="Filter by portfolio. Empty = all portfolios.",
                        required=False,
                    ),
                    MCPToolParameter(
                        name="limit",
                        type="number",
                        description="Max rows. Default 50.",
                        required=False,
                        default=50,
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
        if tool_name == "get_daily_pnl":
            return await self._get_pnl(params, steps)
        elif tool_name == "get_pnl_history":
            return await self._get_pnl_history(params, steps)
        elif tool_name == "get_portfolio_concentration":
            return await self._get_concentration(params, steps)
        elif tool_name == "get_portfolio_risk":
            return await self._get_risk(params, steps)
        elif tool_name == "get_trade_requests":
            return await self._get_trade_requests(params, steps)
        return MCPToolResult(
            tool_name=tool_name,
            namespace=self.namespace,
            rows=[],
            row_count=0,
            columns=[],
            preferred_presentation="table",
            error=f"Unknown tool: {tool_name}",
        )

    async def _get_pnl(self, params: dict, steps: Any | None = None) -> MCPToolResult:
        """Delegate to existing _query_daily_pnl() in retrieval.py."""
        from app.mode2.retrieval import _query_daily_pnl

        rows = await _query_daily_pnl(
            tickers=[params["ticker"]] if params.get("ticker") else [],
            steps=steps,
            portfolio=params.get("portfolio", "all"),
            date=params.get("date"),
            date_range=params.get("date_range"),
            group_by=params.get("group_by"),
            ticker=params.get("ticker"),
            limit=params.get("limit"),
            order_by=params.get("order_by", "unrealized_pnl"),
            order_dir=params.get("order_dir", "desc"),
        )

        # Serialize DB types
        results = [
            {k: _serialize_value(v) for k, v in r.items()}
            for r in rows
        ]

        columns = [
            "ticker", "portfolio", "side", "date", "shares_held",
            "market_value", "cost_basis", "unrealized_pnl",
            "daily_realized_pnl", "ytd_pnl", "itd_pnl",
            "daily_return", "contribution_to_portfolio",
        ]

        return MCPToolResult(
            tool_name="get_daily_pnl",
            namespace=self.namespace,
            rows=results,
            row_count=len(results),
            columns=columns,
            preferred_presentation="table",
        )

    async def _get_pnl_history(self, params: dict, steps: Any | None = None) -> MCPToolResult:
        """Query daily_pnl across dates for time series charting."""
        from app.mode2.db import get_conn
        from app.mode2.retrieval import _normalize_portfolio

        portfolio = params.get("portfolio", "all")
        ticker = params.get("ticker")
        metric = params.get("metric", "itd_pnl")
        lookback_days = int(params.get("lookback_days") or 365)

        valid_metrics = ["itd_pnl", "ytd_pnl", "unrealized_pnl", "daily_return"]
        if metric not in valid_metrics:
            metric = "itd_pnl"

        t0 = time.time()

        conditions = [f"date >= CURRENT_DATE - INTERVAL '{lookback_days} days'"]
        query_params: list[Any] = []
        idx = 1

        norm_portfolio = _normalize_portfolio(portfolio)
        if norm_portfolio:
            conditions.append(f"portfolio = ${idx}")
            query_params.append(norm_portfolio)
            idx += 1

        if ticker:
            conditions.append(f"ticker = ${idx}")
            query_params.append(ticker.upper())
            idx += 1

        where = " AND ".join(conditions)

        async with get_conn() as conn:
            rows = await conn.fetch(
                f"""SELECT date, portfolio, SUM({metric}) as value
                    FROM daily_pnl
                    WHERE {where}
                    GROUP BY date, portfolio
                    ORDER BY date ASC, portfolio""",
                *query_params,
            )

        results = [
            {k: _serialize_value(v) for k, v in dict(r).items()}
            for r in rows
        ]
        duration_ms = int((time.time() - t0) * 1000)

        if steps:
            steps.add(
                label="Fetching P&L history",
                detail=f"daily_pnl: {metric} — {len(results)} rows",
                source="supabase",
                duration_ms=duration_ms,
                result_summary=f"{len(results)} daily rows",
            )

        metric_label = metric.replace("_", " ").upper()
        title = f"Portfolio {metric_label} Over Time"
        if ticker:
            title = f"{ticker} {metric_label} Over Time"

        return MCPToolResult(
            tool_name="get_pnl_history",
            namespace=self.namespace,
            rows=results,
            row_count=len(results),
            columns=["date", "portfolio", "value"],
            preferred_presentation="chart",
            chart_config={
                "type": "line",
                "x_column": "date",
                "y_column": "value",
                "series_column": "portfolio",
                "title": title,
                "y_label": metric_label,
                "formatters": {"value": "millions"},
            },
        )

    async def _get_concentration(self, params: dict, steps: Any | None = None) -> MCPToolResult:
        """Delegate to existing _query_portfolio_concentration()."""
        from app.mode2.retrieval import _query_portfolio_concentration

        rows = await _query_portfolio_concentration(
            tickers=[params["ticker"]] if params.get("ticker") else [],
            portfolio=params.get("portfolio"),
            ticker=params.get("ticker"),
            steps=steps,
        )

        results = [
            {k: _serialize_value(v) for k, v in r.items()}
            for r in rows
        ]

        columns = [
            "ticker", "portfolio", "side", "sector", "industry",
            "position_weight", "sector_weight", "industry_weight",
            "is_market_neutral_compliant",
        ]

        return MCPToolResult(
            tool_name="get_portfolio_concentration",
            namespace=self.namespace,
            rows=results,
            row_count=len(results),
            columns=columns,
            preferred_presentation="table",
        )

    async def _get_risk(self, params: dict, steps: Any | None = None) -> MCPToolResult:
        """Delegate to existing _query_portfolio_risk()."""
        from app.mode2.retrieval import _query_portfolio_risk

        rows = await _query_portfolio_risk(
            tickers=[params["ticker"]] if params.get("ticker") else [],
            portfolio=params.get("portfolio"),
            ticker=params.get("ticker"),
            steps=steps,
        )

        results = [
            {k: _serialize_value(v) for k, v in r.items()}
            for r in rows
        ]

        columns = [
            "ticker", "portfolio", "date", "side", "sector",
            "beta", "weighted_beta_contribution",
        ]

        return MCPToolResult(
            tool_name="get_portfolio_risk",
            namespace=self.namespace,
            rows=results,
            row_count=len(results),
            columns=columns,
            preferred_presentation="table",
        )

    async def _get_trade_requests(self, params: dict, steps: Any | None = None) -> MCPToolResult:
        """Delegate to existing _query_trade_requests()."""
        from app.mode2.retrieval import _query_trade_requests

        rows = await _query_trade_requests(
            ticker=params.get("ticker"),
            status=params.get("status"),
            portfolio=params.get("portfolio"),
            limit=int(params.get("limit") or 50),
            steps=steps,
        )

        results = [
            {k: _serialize_value(v) for k, v in r.items()}
            for r in rows
        ]

        columns = [
            "ticker", "portfolio", "action", "side", "target_pct",
            "status", "created_at", "executed_at",
        ]

        return MCPToolResult(
            tool_name="get_trade_requests",
            namespace=self.namespace,
            rows=results,
            row_count=len(results),
            columns=columns,
            preferred_presentation="table",
        )
