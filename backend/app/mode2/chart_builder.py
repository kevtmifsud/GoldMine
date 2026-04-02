"""Chart spec builder for inline ECharts in chat responses.

Builds ECharts option JSON from tool result data. Claude never constructs
chart JSON directly — it includes pre-built chart specs via ```chart blocks.
"""
from __future__ import annotations

from collections import defaultdict

CHART_COLORS = [
    "#5470c6",  # blue — consensus/primary
    "#91cc75",  # green — internal/positive
    "#fac858",  # amber — buyside
    "#ee6666",  # red — sellside/negative
    "#73c0de",  # light blue
    "#3ba272",  # dark green
    "#fc8452",  # orange
    "#9a60b4",  # purple
    "#ea7ccc",  # pink
]

SOURCE_COLORS = {
    "consensus": "#5470c6",
    "internal": "#91cc75",
    "buyside": "#fac858",
    "sellside": "#ee6666",
}


def _y_axis_label(y_format: str) -> dict:
    """Return axisLabel config for the given format.

    Uses ECharts-native string templates where possible.
    Stores a _format hint for the frontend to apply JS formatters.
    """
    return {"fontSize": 11, "_format": y_format}


def _detect_y_format(sample_val: float, unit: str = "") -> tuple[str, str]:
    if unit and "%" in str(unit):
        return "percent", "Value (%)"
    abs_val = abs(sample_val)
    if abs_val > 1e9:
        return "billions", "Value ($B)"
    if abs_val > 1e6:
        return "millions", "Value ($M)"
    return "number", "Value"


def build_line_chart(
    title: str,
    series_data: list[dict],
    y_format: str = "number",
    y_label: str = "",
    x_label: str = "",
) -> dict:
    """Build ECharts line chart option.

    series_data: list of {name, color (optional), data: [[date_str, value], ...]}
    y_format: "currency" | "percent" | "number" | "billions" | "millions"
    """
    return {
        "title": {
            "text": title,
            "textStyle": {"fontSize": 13, "fontWeight": "500"},
            "top": 8, "left": 12,
        },
        "tooltip": {
            "trigger": "axis",
            "axisPointer": {"type": "cross"},
        },
        "legend": {
            "bottom": 0,
            "type": "scroll",
            "textStyle": {"fontSize": 11},
        },
        "grid": {
            "top": 48, "bottom": 48,
            "left": 60, "right": 20,
            "containLabel": True,
        },
        "xAxis": {
            "type": "time",
            "name": x_label,
            "nameTextStyle": {"fontSize": 11},
            "axisLabel": {"formatter": "{yyyy}-{MM}-{dd}", "fontSize": 11},
        },
        "yAxis": {
            "type": "value",
            "name": y_label,
            "nameTextStyle": {"fontSize": 11},
            "axisLabel": _y_axis_label(y_format),
            "scale": True,
        },
        "series": [
            {
                "name": s["name"],
                "type": "line",
                "data": s["data"],
                "smooth": True,
                "color": s.get("color") or CHART_COLORS[i % len(CHART_COLORS)],
                "lineStyle": {"width": 2},
                "symbol": "circle",
                "symbolSize": 4,
                "emphasis": {"focus": "series"},
            }
            for i, s in enumerate(series_data)
        ],
    }


def build_bar_chart(
    title: str,
    categories: list[str],
    series_data: list[dict],
    y_format: str = "number",
    y_label: str = "",
    x_label: str = "",
) -> dict:
    """Build ECharts bar chart option.

    categories: list of x-axis labels
    series_data: list of {name, color (optional), data: [values...]}
    """
    return {
        "title": {
            "text": title,
            "textStyle": {"fontSize": 13, "fontWeight": "500"},
            "top": 8, "left": 12,
        },
        "tooltip": {
            "trigger": "axis",
            "axisPointer": {"type": "shadow"},
        },
        "legend": {
            "bottom": 0,
            "type": "scroll",
            "textStyle": {"fontSize": 11},
        },
        "grid": {
            "top": 48, "bottom": 48,
            "left": 60, "right": 20,
            "containLabel": True,
        },
        "xAxis": {
            "type": "category",
            "data": categories,
            "name": x_label,
            "axisLabel": {
                "fontSize": 11,
                "rotate": 30 if len(categories) > 6 else 0,
            },
        },
        "yAxis": {
            "type": "value",
            "name": y_label,
            "axisLabel": _y_axis_label(y_format),
        },
        "series": [
            {
                "name": s["name"],
                "type": "bar",
                "data": s["data"],
                "color": s.get("color") or CHART_COLORS[i % len(CHART_COLORS)],
                "emphasis": {"focus": "series"},
                "barMaxWidth": 60,
            }
            for i, s in enumerate(series_data)
        ],
    }


def format_estimates_for_line_chart(
    estimates_rows: list[dict],
    metric: str,
    period: str,
) -> dict | None:
    """Convert daily_estimates rows into a line chart showing estimate
    evolution over time for a specific metric+period."""
    filtered = [
        r for r in estimates_rows
        if r.get("metric") == metric and r.get("period") == period
    ]
    if not filtered:
        return None

    series_map: dict[str, list] = defaultdict(list)
    color_map: dict[str, str] = {}

    for row in sorted(filtered, key=lambda x: str(x.get("as_of_date", ""))):
        source = row.get("source", "")
        firm = row.get("firm") or ""
        analyst = row.get("analyst_name") or ""

        if source == "consensus":
            key = "Consensus"
            color = SOURCE_COLORS["consensus"]
        elif source == "internal":
            name = analyst or "Internal"
            key = f"Internal / {name}"
            color = SOURCE_COLORS["internal"]
        elif firm and analyst:
            key = f"{firm} / {analyst}"
            color = SOURCE_COLORS.get(source)
        elif firm:
            key = firm
            color = SOURCE_COLORS.get(source)
        else:
            key = source.title()
            color = SOURCE_COLORS.get(source)

        series_map[key].append([str(row.get("as_of_date", "")), float(row["value"])])
        if color:
            color_map[key] = color

    sample_val = float(filtered[0]["value"])
    unit = str(filtered[0].get("unit", ""))
    y_format, y_label = _detect_y_format(sample_val, unit)

    ticker = filtered[0].get("ticker", "")
    title = f"{ticker} {metric.replace('_', ' ').title()} Estimates — {period}"

    series_data = [
        {"name": key, "data": points, "color": color_map.get(key)}
        for key, points in series_map.items()
    ]

    return build_line_chart(
        title=title, series_data=series_data,
        y_format=y_format, y_label=y_label, x_label="Date",
    )


def format_estimates_for_bar_chart(
    estimates_rows: list[dict],
    metric: str,
    period: str | None = None,
) -> dict | None:
    """Convert daily_estimates rows into a grouped bar chart.

    X-axis = periods, series = sources. Every row in the data is represented.
    If only one period, falls back to sources on x-axis.
    """
    if not estimates_rows:
        return None

    # Filter to the requested metric
    filtered = [r for r in estimates_rows if r.get("metric") == metric]
    if not filtered:
        return None

    # Get unique periods and sources
    periods = list(dict.fromkeys(r.get("period", "") for r in filtered))
    source_keys: list[str] = []
    source_labels: dict[str, str] = {}

    for row in filtered:
        source = row.get("source", "")
        firm = row.get("firm") or ""
        analyst = row.get("analyst_name") or ""
        # Build a unique key per source/firm/analyst
        if source in ("consensus", "internal"):
            key = source
            label = source.title()
        elif analyst:
            key = f"{source}:{firm}:{analyst}"
            label = f"{firm} / {analyst}"
        elif firm:
            key = f"{source}:{firm}"
            label = firm
        else:
            key = source
            label = source.title()
        if key not in source_labels:
            source_keys.append(key)
            source_labels[key] = label

    # Build lookup: (period, source_key) -> value
    value_map: dict[tuple[str, str], float] = {}
    for row in filtered:
        source = row.get("source", "")
        firm = row.get("firm") or ""
        analyst = row.get("analyst_name") or ""
        if source in ("consensus", "internal"):
            key = source
        elif analyst:
            key = f"{source}:{firm}:{analyst}"
        elif firm:
            key = f"{source}:{firm}"
        else:
            key = source
        p = row.get("period", "")
        val = row.get("value")
        if val is not None:
            value_map[(p, key)] = float(val)

    # Detect value magnitude for formatting
    sample_val = abs(next(iter(value_map.values()), 0))
    y_format, y_label = _detect_y_format(sample_val)

    ticker = filtered[0].get("ticker", "")
    metric_label = metric.replace("_", " ").title()

    if len(periods) > 1:
        # Grouped bar: periods on x-axis, sources as series
        categories = periods
        series_data = []
        for sk in source_keys:
            data = [value_map.get((p, sk), 0) for p in periods]
            series_data.append({"name": source_labels[sk], "data": data})

        title = f"{ticker} {metric_label} — {' & '.join(periods)}"

        chart = build_bar_chart(
            title=title,
            categories=categories,
            series_data=series_data,
            y_format=y_format, y_label=y_label,
        )
    else:
        # Single period: sources on x-axis
        single_period = periods[0] if periods else period or ""
        categories = [source_labels[sk] for sk in source_keys]
        values = [value_map.get((single_period, sk), 0) for sk in source_keys]
        colors = [SOURCE_COLORS.get(sk.split(":")[0], CHART_COLORS[0]) for sk in source_keys]

        title = f"{ticker} {metric_label} — {single_period} Estimates"

        chart = build_bar_chart(
            title=title,
            categories=categories,
            series_data=[{"name": "Estimate", "data": values}],
            y_format=y_format, y_label=y_label,
        )
        # Per-bar colors for single-period
        chart["series"][0]["data"] = [
            {"value": v, "itemStyle": {"color": c}}
            for v, c in zip(values, colors)
    ]

    return chart


def format_pnl_for_line_chart(
    pnl_rows: list[dict],
    metric: str = "itd_pnl",
) -> dict | None:
    """Convert daily_pnl rows into a line chart showing P&L over time."""
    valid_metrics = ["itd_pnl", "ytd_pnl", "unrealized_pnl", "daily_return"]
    if metric not in valid_metrics:
        metric = "itd_pnl"

    if not pnl_rows:
        return None

    series_map: dict[str, list] = defaultdict(list)

    for row in sorted(pnl_rows, key=lambda x: str(x.get("date", ""))):
        port = row.get("portfolio", "Portfolio")
        date_str = str(row.get("date", ""))
        value = float(row.get(metric, 0) or 0)
        series_map[port].append([date_str, value])

    sample_val = abs(float(pnl_rows[0].get(metric, 0) or 0))
    y_format, y_label = _detect_y_format(sample_val)
    if "pnl" in metric:
        y_label = y_label.replace("Value", "P&L")

    portfolio_colors = {"Flagship": "#5470c6", "Long Only": "#91cc75"}
    metric_label = metric.replace("_", " ").upper()
    title = f"Portfolio {metric_label} Over Time"

    series_data = [
        {"name": port, "data": points, "color": portfolio_colors.get(port)}
        for port, points in series_map.items()
    ]

    return build_line_chart(
        title=title, series_data=series_data,
        y_format=y_format, y_label=y_label, x_label="Date",
    )
