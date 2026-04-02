"""Alt Data MCP server — first real (non-legacy) MCP server.

Replaces the legacy get_alt_data tool with a native MCP implementation
that queries the alt_data table directly, bypassing retrieval.py.

Tool names kept compatible with the existing chatbot pipeline:
Claude discovers "get_alt_data" via search_tools and calls it by name.
The registry routes it here via the legacy name fallback in find_server().
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

AVAILABLE_SIGNALS = [
    "credit_card_sss_yoy",
    "credit_card_txn_yoy",
    "credit_card_spv_yoy",
    "foot_traffic_yoy",
    "app_downloads_yoy",
    "web_traffic_yoy",
    "reservations_yoy",
    "job_postings_yoy",
]

AVAILABLE_TICKERS = ["CMG", "DPZ", "SBUX"]

SIGNAL_DESCRIPTIONS = {
    "credit_card_sss_yoy": "Same-store sales YoY % (daily, 3-day lag, Second Measure)",
    "credit_card_txn_yoy": "Transaction count YoY % (daily, 3-day lag, Second Measure)",
    "credit_card_spv_yoy": "Spend per visit YoY % (daily, 3-day lag, Second Measure)",
    "foot_traffic_yoy": "Store visits YoY % (weekly, 1-week lag, Placer.ai)",
    "app_downloads_yoy": "App downloads YoY % (weekly, 1-week lag, Sensor Tower)",
    "web_traffic_yoy": "Web traffic YoY % (weekly, 1-week lag, SimilarWeb)",
    "reservations_yoy": "Reservations YoY % (weekly, 2-week lag, OpenTable). CMG and SBUX only.",
    "job_postings_yoy": "Job postings YoY % (monthly, 2-week lag, Revelio Labs)",
}


def _serialize_value(v: Any) -> Any:
    """Convert DB types to JSON-safe values."""
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, UUID):
        return str(v)
    return v


class AltDataServer(MCPServer):
    """Alternative data signals from third-party vendors.

    Currently available for restaurant names (CMG, DPZ, SBUX).
    Signals include credit card transactions, foot traffic,
    app downloads, web traffic, reservations, and job postings.
    """

    namespace = "altdata"
    display_name = "Alternative Data"
    description = (
        "Alternative data signals from third-party vendors. "
        "Currently available for restaurant names (CMG, DPZ, SBUX). "
        "Signals include credit card transactions, foot traffic, "
        "app downloads, web traffic, reservations, and job postings."
    )

    def list_tools(self) -> list[MCPTool]:
        signal_lines = "\n".join(
            f"  {k} — {v}" for k, v in SIGNAL_DESCRIPTIONS.items()
        )
        return [
            MCPTool(
                name="get_alt_data",
                namespace=self.namespace,
                description=(
                    "Retrieve alternative data signals for a ticker. Returns raw values "
                    "exactly as stored — never aggregates, calculates, or transforms the data. "
                    "Always show the raw values from the database to the analyst."
                    "\n\nDefault behavior: returns last 150 weeks (~3 years) of weekly data. "
                    "For short-term credit card analysis, use preferred_frequency='daily' and "
                    "lookback_days=90."
                    "\n\nAvailable signals by industry:"
                    "\nRestaurants (CMG, DPZ, SBUX):"
                    f"\n{signal_lines}"
                    "\n\nIMPORTANT: Never aggregate or transform values. Always show raw values "
                    "as stored. Include date, value, growth, unit, and source_vendor. "
                    "Always note the data lag when presenting results."
                    "\n\nCite as [TICKER | Alt Data | SIGNAL_NAME | DATE]."
                ),
                parameters=[
                    MCPToolParameter(
                        name="ticker",
                        type="string",
                        description="Stock ticker symbol.",
                        required=True,
                        enum=AVAILABLE_TICKERS,
                    ),
                    MCPToolParameter(
                        name="data_types",
                        type="array",
                        description=(
                            "Signal names to query. Empty list = all available "
                            "signals for this ticker."
                        ),
                        required=False,
                    ),
                    MCPToolParameter(
                        name="preferred_frequency",
                        type="string",
                        description=(
                            "Which data frequency to return. Default 'weekly' — best for "
                            "trend analysis over months/years. Use 'daily' for short-term "
                            "credit card analysis (last 30-90 days). Use 'monthly' for job "
                            "postings. Note: not all signals have all frequencies — credit "
                            "card signals are daily only, foot traffic and app downloads are "
                            "weekly only, job postings are monthly only. Signals without data "
                            "at the requested frequency automatically fall back to their "
                            "native frequency."
                        ),
                        required=False,
                        default="weekly",
                        enum=["daily", "weekly", "monthly"],
                    ),
                    MCPToolParameter(
                        name="lookback_days",
                        type="number",
                        description=(
                            "Days of history to return. Default 1050 (~150 weeks / ~3yrs). "
                            "For daily signals use smaller values e.g. 90 for 3 months of "
                            "daily data. Max 1825 (5 years)."
                        ),
                        required=False,
                        default=1050,
                        min_value=7,
                        max_value=1825,
                    ),
                    MCPToolParameter(
                        name="date_from",
                        type="string",
                        description="Start date YYYY-MM-DD. Overrides lookback_days.",
                        required=False,
                    ),
                    MCPToolParameter(
                        name="date_to",
                        type="string",
                        description="End date YYYY-MM-DD. Default: most recent available.",
                        required=False,
                    ),
                ],
                preferred_presentation="chart",
                chart_config={
                    "type": "line",
                    "x_column": "date",
                    "y_column": "growth",
                    "y_label": "YoY %",
                    "series_column": "data_type",
                    "title": "{ticker} Alt Data Signals",
                    "formatters": {
                        "growth": "percent",
                        "value": "number",
                    },
                },
            ),
            MCPTool(
                name="list_alt_data",
                namespace=self.namespace,
                description=(
                    "List all available alt data signals and tickers with their "
                    "data ranges and lag information."
                ),
                parameters=[
                    MCPToolParameter(
                        name="ticker",
                        type="string",
                        description="Filter by ticker. Omit for all tickers.",
                        required=False,
                        enum=AVAILABLE_TICKERS,
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
        if tool_name == "get_alt_data":
            return await self._get_alt_data(params, steps)
        elif tool_name == "list_alt_data":
            return await self._list_available(params)
        return MCPToolResult(
            tool_name=tool_name,
            namespace=self.namespace,
            rows=[],
            row_count=0,
            columns=[],
            preferred_presentation="table",
            error=f"Unknown tool: {tool_name}",
        )

    async def _get_alt_data(
        self,
        params: dict,
        steps: Any | None = None,
    ) -> MCPToolResult:
        from app.mode2.db import get_conn

        ticker = (params.get("ticker") or "").upper()
        data_types = params.get("data_types") or []
        preferred_frequency = params.get("preferred_frequency", "weekly")
        lookback_days = int(params.get("lookback_days") or 1050)
        date_from = params.get("date_from")
        date_to = params.get("date_to")

        if not ticker:
            return MCPToolResult(
                tool_name="get_alt_data",
                namespace=self.namespace,
                rows=[],
                row_count=0,
                columns=[],
                preferred_presentation="chart",
                error="ticker is required",
            )

        t0 = time.time()

        # Step 1: Query with preferred frequency filter
        conditions = ["ticker = $1"]
        query_params: list[Any] = [ticker]
        idx = 2

        if data_types:
            conditions.append(f"data_type = ANY(${idx})")
            query_params.append(data_types)
            idx += 1

        conditions.append(f"date_frequency = ${idx}")
        query_params.append(preferred_frequency)
        idx += 1

        if date_from:
            conditions.append(f"date >= ${idx}::date")
            query_params.append(date_from)
            idx += 1
        elif not date_to:
            conditions.append(
                f"date >= CURRENT_DATE - INTERVAL '{lookback_days} days'"
            )

        if date_to:
            conditions.append(f"date <= ${idx}::date")
            query_params.append(date_to)
            idx += 1

        where = " AND ".join(conditions)

        query = f"""
            SELECT ticker, data_type, date_frequency, date,
                   value, growth, unit, source_vendor,
                   data_as_of_date, as_of_date
            FROM alt_data
            WHERE {where}
            ORDER BY data_type, date DESC
        """

        async with get_conn() as conn:
            primary_rows = await conn.fetch(query, *query_params)

            # Step 2: Smart fallback — find signals that returned 0 rows
            # at the preferred frequency and retry with their native frequency
            fallback_rows: list = []
            if data_types:
                found_types = {r["data_type"] for r in primary_rows}
                missing_types = [dt for dt in data_types if dt not in found_types]

                if missing_types:
                    fb_conditions = ["ticker = $1", "data_type = ANY($2)"]
                    fb_params: list[Any] = [ticker, missing_types]
                    fb_idx = 3

                    if date_from:
                        fb_conditions.append(f"date >= ${fb_idx}::date")
                        fb_params.append(date_from)
                        fb_idx += 1
                    elif not date_to:
                        fb_conditions.append(
                            f"date >= CURRENT_DATE - INTERVAL '{lookback_days} days'"
                        )

                    if date_to:
                        fb_conditions.append(f"date <= ${fb_idx}::date")
                        fb_params.append(date_to)
                        fb_idx += 1

                    fb_where = " AND ".join(fb_conditions)
                    fallback_rows = await conn.fetch(
                        f"""SELECT ticker, data_type, date_frequency, date,
                                   value, growth, unit, source_vendor,
                                   data_as_of_date, as_of_date
                            FROM alt_data
                            WHERE {fb_where}
                            ORDER BY data_type, date DESC""",
                        *fb_params,
                    )
            else:
                # No specific signals requested — also fetch signals that
                # don't exist at the preferred frequency
                found_types = {r["data_type"] for r in primary_rows}
                fb_conditions = [
                    "ticker = $1",
                    f"date_frequency != ${2}",
                ]
                fb_params_all: list[Any] = [ticker, preferred_frequency]
                fb_idx = 3

                if found_types:
                    fb_conditions.append(f"NOT (data_type = ANY(${fb_idx}))")
                    fb_params_all.append(list(found_types))
                    fb_idx += 1

                if date_from:
                    fb_conditions.append(f"date >= ${fb_idx}::date")
                    fb_params_all.append(date_from)
                    fb_idx += 1
                elif not date_to:
                    fb_conditions.append(
                        f"date >= CURRENT_DATE - INTERVAL '{lookback_days} days'"
                    )

                if date_to:
                    fb_conditions.append(f"date <= ${fb_idx}::date")
                    fb_params_all.append(date_to)
                    fb_idx += 1

                fb_where = " AND ".join(fb_conditions)
                fallback_rows = await conn.fetch(
                    f"""SELECT ticker, data_type, date_frequency, date,
                               value, growth, unit, source_vendor,
                               data_as_of_date, as_of_date
                        FROM alt_data
                        WHERE {fb_where}
                        ORDER BY data_type, date DESC""",
                    *fb_params_all,
                )

        # Step 3: Combine results
        all_rows = list(primary_rows) + list(fallback_rows)

        results = [
            {k: _serialize_value(v) for k, v in dict(r).items()}
            for r in all_rows
        ]
        duration_ms = int((time.time() - t0) * 1000)

        # Count per signal for step logging
        signal_counts: dict[str, int] = {}
        for r in results:
            dt = r["data_type"]
            signal_counts[dt] = signal_counts.get(dt, 0) + 1
        summary = ", ".join(f"{k}({v})" for k, v in signal_counts.items())

        if steps:
            fallback_note = ""
            if fallback_rows:
                fb_types = {r["data_type"] for r in fallback_rows}
                fallback_note = f" (fallback for: {', '.join(fb_types)})"
            steps.add(
                label="Fetching alt data",
                detail=(
                    f"alt_data: {ticker} — {len(results)} rows across "
                    f"{len(signal_counts)} signals{fallback_note}"
                ),
                source="supabase",
                duration_ms=duration_ms,
                result_summary=summary or f"{len(results)} rows",
            )

        columns = [
            "ticker", "data_type", "date_frequency", "date",
            "value", "growth", "unit", "source_vendor",
            "data_as_of_date", "as_of_date",
        ]

        return MCPToolResult(
            tool_name="get_alt_data",
            namespace=self.namespace,
            rows=results,
            row_count=len(results),
            columns=columns,
            preferred_presentation="chart",
            chart_config={
                "type": "line",
                "x_column": "date",
                "y_column": "growth",
                "y_label": "YoY %",
                "series_column": "data_type",
                "title": f"{ticker} Alt Data Signals",
            },
            metadata={
                "ticker": ticker,
                "signals": list(signal_counts.keys()),
                "lag_note": (
                    "Credit card data: 3-day lag. "
                    "Weekly signals: 1-week lag. "
                    "Reservations: 2-week lag. "
                    "Monthly signals: 2-week lag."
                ),
            },
        )

    async def _list_available(self, params: dict) -> MCPToolResult:
        from app.mode2.db import get_conn

        ticker_filter = (params.get("ticker") or "").upper() or None

        async with get_conn() as conn:
            if ticker_filter:
                rows = await conn.fetch(
                    """SELECT ticker, data_type, date_frequency, source_vendor,
                              COUNT(*) as data_points,
                              MIN(date) as earliest,
                              MAX(date) as latest
                       FROM alt_data
                       WHERE ticker = $1
                       GROUP BY ticker, data_type, date_frequency, source_vendor
                       ORDER BY ticker, data_type""",
                    ticker_filter,
                )
            else:
                rows = await conn.fetch(
                    """SELECT ticker, data_type, date_frequency, source_vendor,
                              COUNT(*) as data_points,
                              MIN(date) as earliest,
                              MAX(date) as latest
                       FROM alt_data
                       GROUP BY ticker, data_type, date_frequency, source_vendor
                       ORDER BY ticker, data_type""",
                )

        results = [
            {k: _serialize_value(v) for k, v in dict(r).items()}
            for r in rows
        ]

        return MCPToolResult(
            tool_name="list_alt_data",
            namespace=self.namespace,
            rows=results,
            row_count=len(results),
            columns=[
                "ticker", "data_type", "date_frequency",
                "source_vendor", "data_points", "earliest", "latest",
            ],
            preferred_presentation="table",
        )
