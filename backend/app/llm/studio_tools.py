from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from app.data_access.factory import get_data_provider
from app.data_access.models import FilterParams
from app.llm.data_resolver import resolve_data_source
from app.logging_config import get_logger
from app.studios.models import DataSource, StudioChartConfig, StudioWidget

logger = get_logger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "structured"
_FINANCIALS_DIR = _DATA_DIR / "financials"

# -- Anthropic tool definitions -----------------------------------------------

STUDIO_TOOLS = [
    {
        "name": "list_available_data",
        "description": (
            "List all available datasets and financial data sources. "
            "Returns a catalog of datasets with their fields, and available "
            "financial statement types and metrics."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "query_dataset",
        "description": (
            "Preview rows from any CSV dataset. Use this to explore data before "
            "creating a chart. Returns a sample of rows (up to limit)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dataset": {
                    "type": "string",
                    "description": "Dataset name (e.g. 'stocks', 'people')",
                },
                "filters": {
                    "type": "object",
                    "description": "Key-value filters to apply (e.g. {\"sector\": \"Technology\"})",
                    "additionalProperties": {"type": "string"},
                },
                "sort_by": {
                    "type": "string",
                    "description": "Column to sort by",
                },
                "sort_order": {
                    "type": "string",
                    "enum": ["asc", "desc"],
                    "description": "Sort order (default: asc)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max rows to return (default: 10, max: 25)",
                },
            },
            "required": ["dataset"],
        },
    },
    {
        "name": "get_financial_data",
        "description": (
            "Get financial statement data for a stock ticker. Returns time series "
            "data for the specified statement type and metrics."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol (e.g. 'AAPL')",
                },
                "statement_type": {
                    "type": "string",
                    "enum": ["income_statement", "balance_sheet", "cash_flow"],
                    "description": "Type of financial statement",
                },
                "period": {
                    "type": "string",
                    "enum": ["annual", "quarterly"],
                    "description": "Period type (default: annual)",
                },
                "metrics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Specific metrics to retrieve (e.g. ['total_revenue', 'net_income']). "
                        "If empty, returns all available metrics."
                    ),
                },
            },
            "required": ["ticker", "statement_type"],
        },
    },
    {
        "name": "get_price_history",
        "description": (
            "Get stock price history for a ticker. Returns daily closing prices."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol (e.g. 'AAPL')",
                },
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "remove_chart",
        "description": "Remove a chart widget from the canvas.",
        "input_schema": {
            "type": "object",
            "properties": {
                "widget_id": {
                    "type": "string",
                    "description": "ID of the widget to remove",
                },
            },
            "required": ["widget_id"],
        },
    },
    {
        "name": "create_echarts_chart",
        "description": (
            "Create a chart widget on the canvas using a raw ECharts option object. "
            "This is the ONLY chart creation tool — use it for ALL chart types.\n\n"
            "TWO MODES for providing data:\n"
            "1. Server-side (preferred for price_history / financials): pass data_sources array. "
            "The server resolves the data and injects it into echarts_option. You provide the chart "
            "structure with empty data arrays and series names matching tickers.\n"
            "2. Inline: embed small datasets directly in echarts_option (pie, gauge, small tables).\n\n"
            "Common patterns:\n"
            "- Bar: { xAxis: { type: 'category' }, yAxis: { type: 'value' }, series: [{ name: 'AAPL', type: 'bar' }] } "
            "+ data_sources\n"
            "- Line: { xAxis: { type: 'category' }, yAxis: { type: 'value' }, series: [{ name: 'AAPL', type: 'line', showSymbol: false }] } "
            "+ data_sources\n"
            "- Multi-series line: { xAxis: { type: 'category' }, yAxis: {}, legend: {}, "
            "series: [{ name: 'AAPL', type: 'line', showSymbol: false }, { name: 'MSFT', type: 'line', showSymbol: false }] } "
            "+ data_sources with indexed=true for relative performance\n"
            "- Pie: { series: [{ type: 'pie', data: [{ value: 100, name: 'A' }, ...] }] } (inline data)\n"
            "- Scatter: { xAxis: { type: 'value' }, yAxis: { type: 'value' }, series: [{ type: 'scatter', data: [[x,y], ...] }] }\n"
            "- Gauge: { series: [{ type: 'gauge', data: [{ value: 50 }] }] }\n"
            "- Radar: { radar: { indicator: [...] }, series: [{ type: 'radar', data: [...] }] }\n\n"
            "Use color palette: #3182ce, #e53e3e, #38a169, #d69e2e, #805ad5, #dd6b20, #319795\n"
            "Format dollar values with tooltip/axis formatters. Use valueFormatter or axisLabel formatter for currency/percent."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Chart title (descriptive, e.g. 'AAPL Revenue Breakdown by Segment')",
                },
                "echarts_option": {
                    "type": "object",
                    "description": (
                        "ECharts option object defining chart structure. Must contain 'series'. "
                        "When using data_sources, leave series[].data empty — the server will populate it. "
                        "Set series[].name to match the ticker from data_sources."
                    ),
                },
                "data_sources": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["price_history", "financials"],
                            },
                            "ticker": {
                                "type": "string",
                                "description": "Stock ticker symbol",
                            },
                            "statement_type": {
                                "type": "string",
                                "enum": ["income_statement", "balance_sheet", "cash_flow"],
                            },
                            "period": {
                                "type": "string",
                                "enum": ["annual", "quarterly"],
                            },
                            "metric": {
                                "type": "string",
                                "description": "Financial metric to chart (e.g. 'total_revenue', 'diluted_eps')",
                            },
                            "start_date": {
                                "type": "string",
                                "description": "Filter data on or after this date (YYYY-MM-DD)",
                            },
                            "end_date": {
                                "type": "string",
                                "description": "Filter data on or before this date (YYYY-MM-DD)",
                            },
                        },
                        "required": ["type", "ticker"],
                    },
                    "description": (
                        "Server-side data sources. Each entry is resolved and injected into the "
                        "matching series in echarts_option (matched by series name = ticker). "
                        "Dates populate xAxis.data automatically. No need to query data first."
                    ),
                },
                "indexed": {
                    "type": "boolean",
                    "description": (
                        "If true, index all price series to 100 from the first common date. "
                        "Use for relative performance comparisons (e.g. 'Mag 7 indexed returns'). Default: false."
                    ),
                },
            },
            "required": ["title", "echarts_option"],
        },
    },
]

# -- Tool execution -----------------------------------------------------------


def execute_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    widgets: list[StudioWidget],
    row_columns: list[int],
) -> dict[str, Any]:
    """Execute a studio tool and return the result content block."""
    try:
        result = _TOOL_HANDLERS[tool_name](tool_input, widgets, row_columns)
    except Exception as e:
        logger.error("tool_execution_error", tool=tool_name, error=str(e))
        result = f"Error executing {tool_name}: {str(e)}"
    return result


def _handle_list_available_data(
    _input: dict[str, Any],
    _widgets: list[StudioWidget],
    _row_columns: list[int],
) -> str:
    """Return a catalog of available data sources."""
    lines: list[str] = ["## Available Datasets\n"]

    # CSV datasets
    try:
        provider = get_data_provider()
        datasets = provider.list_datasets()
        for ds in datasets:
            lines.append(f"- **{ds.name}** ({ds.display_name}): {ds.description} [{ds.record_count} records]")
            # Get column names from first row
            try:
                result = provider.query(ds.name, FilterParams(page=1, page_size=1))
                if result.data:
                    cols = list(result.data[0].keys())
                    lines.append(f"  Fields: {', '.join(cols)}")
            except Exception:
                pass
    except Exception:
        lines.append("(Could not load dataset catalog)")

    lines.append("\n## Financial Statements\n")
    lines.append("Available for any stock ticker (e.g. AAPL, MSFT, GOOGL):")
    lines.append("- **income_statement** (annual/quarterly): total_revenue, gross_profit, operating_income, ebitda, net_income, diluted_eps, etc.")
    lines.append("- **balance_sheet** (annual/quarterly): total_assets, total_debt, stockholders_equity, cash_and_cash_equivalents, etc.")
    lines.append("- **cash_flow** (annual/quarterly): operating_cash_flow, free_cash_flow, capital_expenditure, etc.")

    lines.append("\n## Price History\n")
    lines.append("Daily closing prices available for all stocks in the universe.")

    lines.append("\n## Portfolio PnL\n")
    lines.append("Daily PnL series available for portfolios: Flagship, Long Only")

    return "\n".join(lines)


def _handle_query_dataset(
    tool_input: dict[str, Any],
    _widgets: list[StudioWidget],
    _row_columns: list[int],
) -> str:
    """Preview rows from a dataset."""
    dataset = tool_input.get("dataset", "")
    filters = tool_input.get("filters", {})
    sort_by = tool_input.get("sort_by")
    sort_order = tool_input.get("sort_order", "asc")
    limit = min(tool_input.get("limit", 10), 25)

    provider = get_data_provider()
    params = FilterParams(
        page=1,
        page_size=limit,
        sort_by=sort_by,
        sort_order=sort_order,
        filters=filters,
    )
    result = provider.query(dataset, params)

    if not result.data:
        return f"No data found in dataset '{dataset}' with the given filters."

    lines: list[str] = [f"Dataset: {dataset} ({result.total_records} total records, showing {len(result.data)})\n"]
    # Show as simple text table
    cols = list(result.data[0].keys())
    lines.append(" | ".join(cols))
    lines.append("-" * 80)
    for row in result.data:
        vals = [str(row.get(c, ""))[:30] for c in cols]
        lines.append(" | ".join(vals))

    return "\n".join(lines)


def _handle_get_financial_data(
    tool_input: dict[str, Any],
    _widgets: list[StudioWidget],
    _row_columns: list[int],
) -> str:
    """Preview financial data for a ticker."""
    ds = DataSource(
        type="financials",
        ticker=tool_input.get("ticker"),
        statement_type=tool_input.get("statement_type"),
        period=tool_input.get("period", "annual"),
        metrics=tool_input.get("metrics"),
    )
    data = resolve_data_source(ds)

    if not data:
        return f"No financial data found for {ds.ticker} ({ds.statement_type}, {ds.period})."

    # Show sample
    lines: list[str] = [
        f"Financial data for {ds.ticker} ({ds.statement_type}, {ds.period}): {len(data)} periods\n"
    ]
    cols = list(data[0].keys())
    lines.append(" | ".join(cols))
    lines.append("-" * 80)
    # Show first 10 rows
    for row in data[:10]:
        vals = [str(row.get(c, ""))[:20] for c in cols]
        lines.append(" | ".join(vals))
    if len(data) > 10:
        lines.append(f"... ({len(data) - 10} more rows)")

    return "\n".join(lines)


def _handle_get_price_history(
    tool_input: dict[str, Any],
    _widgets: list[StudioWidget],
    _row_columns: list[int],
) -> str:
    """Preview price history for a ticker."""
    ds = DataSource(
        type="price_history",
        ticker=tool_input.get("ticker"),
    )
    data = resolve_data_source(ds)

    if not data:
        return f"No price history found for {ds.ticker}."

    lines: list[str] = [
        f"Price history for {ds.ticker}: {len(data)} data points\n"
    ]
    # Show last 10 rows
    sample = data[-10:]
    lines.append("date | close")
    lines.append("-" * 30)
    for row in sample:
        lines.append(f"{row['date']} | {row['close']}")
    if len(data) > 10:
        lines.append(f"(showing last 10 of {len(data)} data points)")

    return "\n".join(lines)


def _find_next_empty_cell(
    widgets: list[StudioWidget],
    row_columns: list[int],
) -> tuple[int, int]:
    """Find the next empty cell in the grid. Appends a new row if full."""
    occupied = {(w.row, w.col) for w in widgets}
    for row_idx, col_count in enumerate(row_columns):
        for col_idx in range(col_count):
            if (row_idx, col_idx) not in occupied:
                return row_idx, col_idx
    # Grid is full — append new row
    new_row = len(row_columns)
    row_columns.append(2)
    return new_row, 0


def _handle_remove_chart(
    tool_input: dict[str, Any],
    widgets: list[StudioWidget],
    _row_columns: list[int],
) -> str:
    """Remove a chart widget."""
    widget_id = tool_input.get("widget_id", "")

    for i, w in enumerate(widgets):
        if w.widget_id == widget_id:
            removed = widgets.pop(i)
            return f"Removed chart '{removed.title}'."

    return f"Widget '{widget_id}' not found."


def _sanitize_echarts_option(option: dict[str, Any]) -> None:
    """Sanitize an ECharts option generated by the LLM.

    JSON cannot represent JavaScript functions, so any ECharts property that
    only accepts a function (e.g. tooltip.valueFormatter) will be a broken
    string.  Strip those out and inject performance defaults.
    """
    # Remove function-only properties that the LLM set as strings
    tooltip = option.get("tooltip")
    if isinstance(tooltip, dict):
        if isinstance(tooltip.get("valueFormatter"), str):
            del tooltip["valueFormatter"]

    for s in option.get("series", []):
        if not isinstance(s, dict):
            continue
        # series-level tooltip
        s_tooltip = s.get("tooltip")
        if isinstance(s_tooltip, dict) and isinstance(s_tooltip.get("valueFormatter"), str):
            del s_tooltip["valueFormatter"]
        # label.formatter — string templates are valid, but functions are not
        label = s.get("label")
        if isinstance(label, dict) and isinstance(label.get("formatter"), str):
            # ECharts supports string templates like '{b}: {c}' so keep those;
            # only remove if it looks like a broken function reference
            pass

    # Default tooltip to axis trigger for multi-series readability
    option.setdefault("tooltip", {"trigger": "axis"})

    # Default grid for proper margins
    option.setdefault("grid", {"left": 60, "right": 16, "top": 30, "bottom": 30})

    # Disable animation for charts with many data points
    series_list = option.get("series", [])
    total_points = sum(
        len(s.get("data", [])) for s in series_list if isinstance(s, dict)
    )
    if total_points > 400:
        option.setdefault("animation", False)

    # Ensure showSymbol: false on line series with many points
    for s in series_list:
        if isinstance(s, dict) and s.get("type") == "line" and len(s.get("data", [])) > 50:
            s.setdefault("showSymbol", False)


def _handle_create_echarts_chart(
    tool_input: dict[str, Any],
    widgets: list[StudioWidget],
    row_columns: list[int],
) -> str:
    """Create a chart widget from a raw ECharts option."""
    title = tool_input.get("title", "Chart")
    echarts_option = tool_input.get("echarts_option", {})
    data_sources = tool_input.get("data_sources", [])
    indexed = tool_input.get("indexed", False)

    # -- Server-side data resolution ------------------------------------------
    if data_sources:
        resolved: list[dict[str, Any]] = []
        for ds_spec in data_sources:
            ds_type = ds_spec.get("type", "price_history")
            ticker = ds_spec.get("ticker", "")
            start_date = ds_spec.get("start_date")
            end_date = ds_spec.get("end_date")

            if ds_type == "price_history":
                ds = DataSource(type="price_history", ticker=ticker)
                data = resolve_data_source(ds)
                if not data:
                    continue
                if start_date:
                    data = [d for d in data if d.get("date", "") >= start_date]
                if end_date:
                    data = [d for d in data if d.get("date", "") <= end_date]
                resolved.append({
                    "name": ticker.upper(),
                    "dates": [d["date"] for d in data],
                    "values": [d["close"] for d in data],
                })
            elif ds_type == "financials":
                metric = ds_spec.get("metric", "value")
                ds = DataSource(
                    type="financials",
                    ticker=ticker,
                    statement_type=ds_spec.get("statement_type", "income_statement"),
                    period=ds_spec.get("period", "annual"),
                    metrics=[metric] if metric != "value" else None,
                )
                data = resolve_data_source(ds)
                if not data:
                    continue
                if start_date:
                    data = [d for d in data if d.get("date", "") >= start_date]
                if end_date:
                    data = [d for d in data if d.get("date", "") <= end_date]
                resolved.append({
                    "name": ticker.upper(),
                    "dates": [d["date"] for d in data],
                    "values": [d.get(metric, d.get("value", 0)) for d in data],
                })

        if not resolved:
            return "Error: no data could be resolved from data_sources."

        # Align to common dates across all sources
        common_dates_set = set(resolved[0]["dates"])
        for r in resolved[1:]:
            common_dates_set &= set(r["dates"])
        common_dates = sorted(common_dates_set)

        if not common_dates:
            return "Error: no common dates found across data sources."

        for r in resolved:
            date_to_val = dict(zip(r["dates"], r["values"]))
            r["values"] = [date_to_val[d] for d in common_dates]
            r["dates"] = common_dates

        # Index to 100 if requested
        if indexed:
            for r in resolved:
                base = r["values"][0] if r["values"] else None
                if base and base != 0:
                    r["values"] = [round(v / base * 100, 2) for v in r["values"]]

        # Inject dates into xAxis.data
        x_axis = echarts_option.get("xAxis")
        if isinstance(x_axis, dict):
            x_axis["data"] = common_dates
        elif isinstance(x_axis, list) and x_axis:
            x_axis[0]["data"] = common_dates
        else:
            echarts_option["xAxis"] = {"type": "category", "data": common_dates}

        # Inject values into matching series (match by name = ticker)
        series_list = echarts_option.get("series", [])
        for r in resolved:
            matched = False
            for s in series_list:
                if isinstance(s, dict) and s.get("name", "").upper() == r["name"]:
                    s["data"] = r["values"]
                    matched = True
                    break
            # Single source + single series: inject regardless of name
            if not matched and len(resolved) == 1 and len(series_list) == 1:
                series_list[0]["data"] = r["values"]

    # -- Sanitize and inject defaults -----------------------------------------
    _sanitize_echarts_option(echarts_option)

    # -- Validate -------------------------------------------------------------
    if "series" not in echarts_option and "dataset" not in echarts_option:
        return "Error: echarts_option must contain 'series' or 'dataset'."

    # Find placement
    row, col = _find_next_empty_cell(widgets, row_columns)

    widget = StudioWidget(
        widget_id=str(uuid.uuid4()),
        title=title,
        chart_type="echarts",
        chart_config=StudioChartConfig(x_key="", y_key=""),
        data_source=DataSource(type="none"),
        data=[],
        echarts_option=echarts_option,
        row=row,
        col=col,
    )
    widgets.append(widget)

    # Summarize series types
    series = echarts_option.get("series", [])
    if isinstance(series, list) and series:
        types = {s.get("type", "unknown") for s in series if isinstance(s, dict)}
        type_str = ", ".join(sorted(types))
    else:
        type_str = "custom"

    data_points = sum(len(s.get("data", [])) for s in series if isinstance(s, dict))
    return f"Created {type_str} chart '{title}' at row {row + 1}, col {col + 1} ({data_points} data points)."


_TOOL_HANDLERS = {
    "list_available_data": _handle_list_available_data,
    "query_dataset": _handle_query_dataset,
    "get_financial_data": _handle_get_financial_data,
    "get_price_history": _handle_get_price_history,
    "remove_chart": _handle_remove_chart,
    "create_echarts_chart": _handle_create_echarts_chart,
}
