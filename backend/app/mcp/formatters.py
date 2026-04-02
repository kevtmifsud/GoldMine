"""Deterministic formatters for MCP tool results.

Each formatter converts raw rows into pre-formatted markdown that renders
identically in chat and pack tiles.

Adding a new tool:
1. Write a format_{tool_name}() function
2. Register it in FORMATTERS dict
3. Done — works in chat and packs automatically
"""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ─── Value formatters ────────────────────────────────────────────────────────

def fmt_currency(v: Any) -> str:
    """Format as currency. $12.1B / $608M / $25K / $4.06 (EPS)."""
    if v is None:
        return "—"
    try:
        n = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(n) >= 1_000_000_000:
        return f"${n / 1_000_000_000:.1f}B"
    if abs(n) >= 1_000_000:
        return f"${n / 1_000_000:.0f}M"
    if abs(n) >= 1_000:
        return f"${n / 1_000:.0f}K"
    return f"${n:.2f}"


def fmt_pct(v: Any, decimals: int = 1, sign: bool = True) -> str:
    """Format as percentage. +5.2% or -3.1%."""
    if v is None:
        return "—"
    try:
        n = float(v)
    except (TypeError, ValueError):
        return str(v)
    prefix = "+" if sign and n > 0 else ""
    return f"{prefix}{n:.{decimals}f}%"


def fmt_date(v: Any) -> str:
    """Format as YYYY-MM-DD."""
    if not v:
        return "—"
    return str(v)[:10]


def fmt_shares(v: Any) -> str:
    """Format share count."""
    if v is None:
        return "—"
    try:
        n = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(n) >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if abs(n) >= 1_000:
        return f"{n / 1_000:.0f}K"
    return f"{n:.0f}"


def fmt_weight(v: Any) -> str:
    """Format position weight as %. Input is decimal (0.05 → 5.00%)."""
    if v is None:
        return "—"
    try:
        n = float(v) * 100
    except (TypeError, ValueError):
        return str(v)
    return f"{n:.2f}%"


def fmt_str(v: Any) -> str:
    """Safe string with — for None/empty."""
    if v is None or v == "":
        return "—"
    return str(v).strip()


def fmt_analyst(firm: Any, analyst: Any) -> str:
    """Combine firm and analyst name."""
    f = fmt_str(firm)
    a = fmt_str(analyst)
    if f == "—" and a == "—":
        return "—"
    if f == "—":
        return a
    if a == "—":
        return f
    return f"{f} / {a}"


# ─── Markdown table builder ─────────────────────────────────────────────────

def md_table(headers: list[str], rows: list[list[str]]) -> str:
    """Build a markdown table string."""
    if not rows:
        return "_No data available._"
    header = "| " + " | ".join(headers) + " |"
    sep = "|" + "|".join("---" for _ in headers) + "|"
    body = "\n".join("| " + " | ".join(row) + " |" for row in rows)
    return f"{header}\n{sep}\n{body}"


def intro_line(*parts: str) -> str:
    """Build a one-line intro from non-empty parts."""
    return " — ".join(p for p in parts if p) + ":"


# ─── Estimates ───────────────────────────────────────────────────────────────

_SOURCE_ORDER = {"consensus": 0, "internal": 1, "sellside": 2, "buyside": 3}


def format_get_estimates(rows: list[dict], params: dict) -> str:
    """Format estimates as markdown table."""
    if not rows:
        return "_No estimates found._"

    tickers = list(dict.fromkeys(r.get("ticker", "") for r in rows))
    metrics = list(dict.fromkeys(r.get("metric", "") for r in rows))
    periods = list(dict.fromkeys(r.get("period", "") for r in rows))
    is_single = len(tickers) == 1

    metric_label = metrics[0].replace("_", " ").title() if metrics else ""
    period_label = " & ".join(periods) if periods else ""

    if is_single:
        intro = intro_line(f"{tickers[0]} {metric_label} {period_label} estimates")
    else:
        intro = intro_line(f"{metric_label} {period_label} estimates", f"{len(tickers)} tickers")

    sorted_rows = sorted(
        rows,
        key=lambda r: (
            r.get("period", ""),
            _SOURCE_ORDER.get(r.get("source", ""), 99),
            r.get("firm") or "",
            r.get("analyst_name") or "",
        ),
    )

    def _fmt_est(r: dict) -> str:
        v = r.get("value")
        if v is None:
            return "—"
        if "eps" in (r.get("metric") or "").lower():
            return f"${float(v):.2f}"
        return fmt_currency(v)

    if is_single:
        headers = ["Source", "Firm / Analyst", "Period", "Estimate", "vs Prior Yr", "Est. Date"]
        table_rows = [
            [
                fmt_str(r.get("source", "")).title(),
                fmt_analyst(r.get("firm"), r.get("analyst_name")),
                fmt_str(r.get("period")),
                _fmt_est(r),
                fmt_pct(r.get("yoy_vs_actual")),
                fmt_date(r.get("estimate_date") or r.get("as_of_date")),
            ]
            for r in sorted_rows
        ]
    else:
        headers = ["Ticker", "Source", "Firm / Analyst", "Period", "Estimate", "vs Prior Yr", "Est. Date"]
        table_rows = [
            [
                fmt_str(r.get("ticker")),
                fmt_str(r.get("source", "")).title(),
                fmt_analyst(r.get("firm"), r.get("analyst_name")),
                fmt_str(r.get("period")),
                _fmt_est(r),
                fmt_pct(r.get("yoy_vs_actual")),
                fmt_date(r.get("estimate_date") or r.get("as_of_date")),
            ]
            for r in sorted_rows
        ]

    staleness_note = ""
    max_staleness = max((r.get("staleness_days") or 0) for r in rows)
    if max_staleness > 90:
        staleness_note = f"\n_(oldest estimate is {max_staleness} days old)_"

    return f"{intro}\n\n{md_table(headers, table_rows)}{staleness_note}"


# ─── Portfolio ───────────────────────────────────────────────────────────────

def format_get_daily_pnl(rows: list[dict], params: dict) -> str:
    """Format P&L as markdown table, grouped by portfolio."""
    if not rows:
        return "_No P&L data available._"

    by_portfolio: dict[str, list] = {}
    for r in rows:
        p = r.get("portfolio", "Unknown")
        by_portfolio.setdefault(p, []).append(r)

    sections = []
    for portfolio, port_rows in by_portfolio.items():
        port_rows.sort(key=lambda r: float(r.get("unrealized_pnl") or 0), reverse=True)

        as_of = fmt_date(port_rows[0].get("date") if port_rows else None)
        headers = ["Ticker", "Side", "Shares", "Mkt Value", "Unrealized", "YTD P&L", "Daily Ret"]
        table_rows = [
            [
                fmt_str(r.get("ticker")),
                fmt_str(r.get("side", "")).upper(),
                fmt_shares(r.get("shares_held")),
                fmt_currency(r.get("market_value")),
                fmt_currency(r.get("unrealized_pnl")),
                fmt_currency(r.get("ytd_pnl")),
                fmt_pct(r.get("daily_return")) if r.get("daily_return") is not None else "—",
            ]
            for r in port_rows
        ]
        sections.append(f"**{portfolio}** — as of {as_of}\n\n{md_table(headers, table_rows)}")

    return "\n\n---\n\n".join(sections)


def format_get_portfolio_concentration(rows: list[dict], params: dict) -> str:
    """Format concentration as markdown table."""
    if not rows:
        return "_No concentration data._"

    by_portfolio: dict[str, list] = {}
    for r in rows:
        p = r.get("portfolio", "Unknown")
        by_portfolio.setdefault(p, []).append(r)

    sections = []
    for portfolio, port_rows in by_portfolio.items():
        port_rows.sort(key=lambda r: float(r.get("position_weight") or 0), reverse=True)
        headers = ["Ticker", "Side", "Sector", "Position Wt", "Sector Wt"]
        table_rows = [
            [
                fmt_str(r.get("ticker")),
                fmt_str(r.get("side", "")).upper(),
                fmt_str(r.get("sector")),
                fmt_weight(r.get("position_weight")),
                fmt_weight(r.get("sector_weight")),
            ]
            for r in port_rows
        ]
        sections.append(f"**{portfolio}**\n\n{md_table(headers, table_rows)}")

    return "\n\n---\n\n".join(sections)


def format_get_portfolio_risk(rows: list[dict], params: dict) -> str:
    """Format risk as markdown table."""
    if not rows:
        return "_No risk data available._"

    headers = ["Ticker", "Portfolio", "Side", "Beta", "Weighted Beta"]
    table_rows = [
        [
            fmt_str(r.get("ticker")),
            fmt_str(r.get("portfolio")),
            fmt_str(r.get("side", "")).upper(),
            fmt_str(r.get("beta")),
            fmt_str(r.get("weighted_beta_contribution")),
        ]
        for r in rows
    ]
    return md_table(headers, table_rows)


def format_get_trade_requests(rows: list[dict], params: dict) -> str:
    """Format trade requests as markdown table."""
    if not rows:
        return "_No trade requests found._"

    headers = ["Ticker", "Portfolio", "Action", "Side", "Target %", "Status", "Requested", "Executed"]
    table_rows = [
        [
            fmt_str(r.get("ticker")),
            fmt_str(r.get("portfolio")),
            fmt_str(r.get("action")),
            fmt_str(r.get("side", "")).upper(),
            fmt_str(r.get("target_pct")),
            fmt_str(r.get("status")),
            fmt_date(r.get("created_at")),
            fmt_date(r.get("executed_at")),
        ]
        for r in rows
    ]
    return md_table(headers, table_rows)


# ─── Financials ──────────────────────────────────────────────────────────────

_METRIC_ORDER = [
    "total_revenue", "gross_profit", "operating_income", "ebitda",
    "net_income", "diluted_eps", "free_cash_flow", "operating_cash_flow",
    "capital_expenditure", "total_assets", "total_debt", "cash_and_cash_equivalents",
]


def format_get_financial_metrics(rows: list[dict], params: dict) -> str:
    """Format financial metrics as a pivoted table (metrics × periods)."""
    if not rows:
        return "_No financial data._"

    tickers = list(dict.fromkeys(r.get("ticker", "") for r in rows))
    sections = []

    for ticker in tickers:
        ticker_rows = [r for r in rows if r.get("ticker") == ticker]

        by_metric: dict[str, list] = {}
        for r in ticker_rows:
            m = r.get("metric_name", "")
            by_metric.setdefault(m, []).append(r)

        periods = sorted(list(dict.fromkeys(str(r.get("period_end", "")) for r in ticker_rows)))
        periods = periods[-8:]  # last 8

        headers = ["Metric"] + [p[:7] for p in periods]

        ordered = [m for m in _METRIC_ORDER if m in by_metric] + [m for m in by_metric if m not in _METRIC_ORDER]

        table_rows = []
        for metric in ordered:
            by_period = {str(r.get("period_end", "")): r for r in by_metric[metric]}
            is_eps = "eps" in metric.lower()
            label = metric.replace("_", " ").title()
            row_data = [label]
            for period in periods:
                r = by_period.get(period)
                if r is None:
                    row_data.append("—")
                elif is_eps:
                    v = r.get("value")
                    row_data.append(f"${float(v):.2f}" if v is not None else "—")
                else:
                    row_data.append(fmt_currency(r.get("value")))
            table_rows.append(row_data)

        ptype = (ticker_rows[0].get("period_type", "quarterly") if ticker_rows else "quarterly")
        sections.append(f"**{ticker}** ({ptype.title()})\n\n{md_table(headers, table_rows)}")

    return "\n\n---\n\n".join(sections)


def format_get_guidance(rows: list[dict], params: dict) -> str:
    """Format management guidance."""
    if not rows:
        return "_No guidance available._"

    headers = ["Ticker", "Metric", "Period", "Guidance", "Type", "Issued"]
    table_rows = [
        [
            fmt_str(r.get("ticker")),
            fmt_str(r.get("metric", "").replace("_", " ").title()),
            fmt_str(r.get("period")),
            fmt_currency(r.get("value")),
            fmt_str(r.get("guidance_type")),
            fmt_date(r.get("issued_date")),
        ]
        for r in rows
    ]
    return md_table(headers, table_rows)


# ─── Alt Data / Search / Workflows ──────────────────────────────────────────

def format_list_alt_data(rows: list[dict], params: dict) -> str:
    """Format alt data availability table."""
    if not rows:
        return "_No alt data available._"

    headers = ["Ticker", "Signal", "Frequency", "Vendor", "Points", "Earliest", "Latest"]
    table_rows = [
        [
            fmt_str(r.get("ticker")),
            fmt_str(r.get("data_type", "").replace("_", " ")),
            fmt_str(r.get("date_frequency")),
            fmt_str(r.get("source_vendor")),
            fmt_str(r.get("data_points")),
            fmt_date(r.get("earliest")),
            fmt_date(r.get("latest")),
        ]
        for r in rows
    ]
    return md_table(headers, table_rows)


def format_search_universe(rows: list[dict], params: dict) -> str:
    """Format stock universe search results."""
    if not rows:
        return f"_No stocks found matching '{params.get('query', '')}'._"

    headers = ["Ticker", "Company", "Sector", "Industry", "Exchange"]
    table_rows = [
        [
            fmt_str(r.get("ticker")),
            fmt_str(r.get("company_name")),
            fmt_str(r.get("sector")),
            fmt_str(r.get("industry")),
            fmt_str(r.get("exchange")),
        ]
        for r in rows
    ]
    return md_table(headers, table_rows)


def format_get_workflow_registry(rows: list[dict], params: dict) -> str:
    """Format workflow registry."""
    if not rows:
        return "_No workflows registered._"

    headers = ["Workflow", "Description", "Trigger", "Active"]
    table_rows = [
        [
            fmt_str(r.get("display_name") or r.get("workflow_name")),
            fmt_str(r.get("description")),
            fmt_str(r.get("trigger_type")),
            "Yes" if r.get("is_active") else "No",
        ]
        for r in rows
    ]
    return md_table(headers, table_rows)


# ─── Formatter Registry ─────────────────────────────────────────────────────

FORMATTERS: dict[str, Callable[[list[dict], dict], str]] = {
    "get_estimates": format_get_estimates,
    "get_daily_pnl": format_get_daily_pnl,
    "get_portfolio_concentration": format_get_portfolio_concentration,
    "get_portfolio_risk": format_get_portfolio_risk,
    "get_trade_requests": format_get_trade_requests,
    "get_financial_metrics": format_get_financial_metrics,
    "get_guidance": format_get_guidance,
    "list_alt_data": format_list_alt_data,
    "search_universe": format_search_universe,
    "get_workflow_registry": format_get_workflow_registry,
}


def format_tool_result(tool_name: str, rows: list[dict], params: dict) -> str | None:
    """Format a tool result as markdown.

    Returns formatted markdown string, or None if no formatter exists
    (chart tools, text tools handle their own presentation).
    """
    formatter = FORMATTERS.get(tool_name)
    if formatter is None:
        return None
    try:
        return formatter(rows, params)
    except Exception as e:
        logger.warning("formatter_error", extra={"tool": tool_name, "error": str(e)})
        return None
