from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from app.api.entities import (
    _compute_daily_pnl_series,
    _compute_portfolio_holdings,
    _get_all_trading_dates,
    _get_latest_prices,
    _load_portfolio_trades,
    _price_on_date,
)
from app.data_access.factory import get_data_provider
from app.data_access.models import FilterParams

_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "structured"
_EARNINGS_CSV = _DATA_DIR / "earnings_calendar.csv"


def _load_earnings_by_date() -> dict[str, str]:
    """Return {ticker: report_date} for all earnings entries."""
    if not _EARNINGS_CSV.exists():
        return {}
    result: dict[str, str] = {}
    with open(_EARNINGS_CSV, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            result[row["ticker"]] = row.get("report_date", "")
    return result


def _fmt_currency(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"${value:,.0f}"
    return f"${value:,.2f}"


def _fmt_pct(value: float) -> str:
    return f"{value:+.2f}%"


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _html_section_header(title: str) -> str:
    return (
        f'<h2 style="font-size:16px;font-weight:700;color:#1a365d;'
        f'margin:20px 0 8px 0;border-bottom:2px solid #d4a843;'
        f'padding-bottom:4px;">{_escape(title)}</h2>'
    )


def _html_table_header(*cols: tuple[str, str]) -> str:
    """Render a table header. Each col is (label, align)."""
    cells = ""
    for label, align in cols:
        cells += (
            f'<th style="padding:6px 10px;color:#ffffff;font-size:12px;'
            f'text-align:{align};font-weight:600;background:#1a365d;">'
            f'{_escape(label)}</th>'
        )
    return f'<table style="width:100%;border-collapse:collapse;margin:12px 0;font-size:13px;"><tr>{cells}</tr>'


def _html_table_row(i: int, *cells: tuple[str, str, str]) -> str:
    """Render a table row. Each cell is (value, align, extra_style)."""
    bg = "#ffffff" if i % 2 == 0 else "#f7f8fa"
    result = f'<tr style="background:{bg};">'
    for value, align, extra in cells:
        result += (
            f'<td style="padding:6px 10px;border-bottom:1px solid #e2e8f0;'
            f'font-size:13px;text-align:{align};{extra}">{value}</td>'
        )
    return result + "</tr>"


def _pnl_color(value: float) -> str:
    return "#276749" if value >= 0 else "#c53030"


def render_daily_pnl_report(portfolio_name: str = "Flagship") -> tuple[str, str, str, list[tuple[str, bytes]]]:
    """Render the Daily PnL Report for a single portfolio.

    Returns (subject, html_body, text_body, images).
    """
    provider = get_data_provider()

    # --- Portfolio metadata ---
    portfolios = provider.query("portfolios", FilterParams(page=1, page_size=100)).data
    portfolio_meta = next((p for p in portfolios if p["name"] == portfolio_name), None)
    strategy = portfolio_meta.get("strategy", "") if portfolio_meta else ""

    # --- Determine report date (latest available in price data) ---
    all_trading_dates = _get_all_trading_dates()
    report_date = all_trading_dates[-1] if all_trading_dates else date.today().isoformat()
    prior_date = all_trading_dates[-2] if len(all_trading_dates) >= 2 else report_date
    report_date_display = date.fromisoformat(report_date).strftime("%B %d, %Y")
    prior_date_display = date.fromisoformat(prior_date).strftime("%B %d, %Y")

    # --- Holdings & daily PnL series (YTD / L30D only) ---
    holdings = _compute_portfolio_holdings(portfolio_name)
    daily_series = _compute_daily_pnl_series(portfolio_name)

    ytd_pnl = 0.0
    ytd_pnl_pct = 0.0
    l30d_pnl = 0.0
    l30d_pnl_pct = 0.0

    # --- Position-level detail with DAILY PnL (day-over-day) ---
    # All daily PnL values flow from position-level calculations so that
    # portfolio = sum of sides = sum of sectors (perfect decomposition).
    position_rows: list[dict[str, Any]] = []
    longs_daily_pnl = 0.0
    shorts_daily_pnl = 0.0
    longs_market_value = 0.0
    shorts_market_value = 0.0
    longs_prior_mv = 0.0
    shorts_prior_mv = 0.0

    # Load earnings for flagging
    all_earnings = _load_earnings_by_date()

    for h in holdings:
        ticker = h["ticker"]
        price_today = _price_on_date(ticker, report_date)
        price_prior = _price_on_date(ticker, prior_date)
        if price_today is None:
            price_today = h["avg_cost"]
        if price_prior is None:
            price_prior = price_today

        shares = h["shares"]
        mv = shares * price_today
        mv_prior = shares * price_prior
        # Daily PnL: side-adjusted so positive = made money, negative = lost money
        if h["side"] == "long":
            pos_daily_pnl = shares * (price_today - price_prior)
        else:
            pos_daily_pnl = shares * (price_prior - price_today)

        # Raw stock % change (not side-adjusted) — shows actual stock movement direction
        raw_pnl_pct = ((price_today - price_prior) / price_prior * 100) if price_prior else 0.0

        # Earnings: only flag if earnings on report_date or prior_date
        ticker_earnings_date = all_earnings.get(ticker, "")
        had_earnings_today = ticker_earnings_date in (report_date, prior_date)

        # For watchlist: earnings in next 4 days from report_date
        earnings_in_next_4 = False
        if ticker_earnings_date:
            try:
                days_until = (date.fromisoformat(ticker_earnings_date) - date.fromisoformat(report_date)).days
                earnings_in_next_4 = 1 <= days_until <= 4
            except ValueError:
                pass

        # Track side-level PnL and market value
        if h["side"] == "long":
            longs_daily_pnl += pos_daily_pnl
            longs_market_value += mv
            longs_prior_mv += mv_prior
        else:
            shorts_daily_pnl += pos_daily_pnl
            shorts_market_value += mv
            shorts_prior_mv += mv_prior

        position_rows.append({
            "ticker": ticker,
            "side": h["side"],
            "shares": shares,
            "price": round(price_today, 2),
            "daily_pnl": round(pos_daily_pnl, 2),
            "raw_pnl_pct": round(raw_pnl_pct, 2),
            "sector": h["sector"],
            "mv": mv,
            "had_earnings_today": had_earnings_today,
            "earnings_in_next_4": earnings_in_next_4,
            "earnings_date": ticker_earnings_date,
        })

    # --- Portfolio-level daily PnL derived from position sums ---
    total_market_value = longs_market_value + shorts_market_value
    prior_total_mv = longs_prior_mv + shorts_prior_mv
    daily_pnl = longs_daily_pnl + shorts_daily_pnl
    daily_pnl_pct = (daily_pnl / prior_total_mv * 100) if prior_total_mv else 0.0

    # Add weights now that we know total_market_value
    for p in position_rows:
        p["weight"] = round((p["mv"] / total_market_value * 100) if total_market_value else 0.0, 2)

    # Side-level PnL percentages (vs prior day market value for that side)
    longs_daily_pnl_pct = (longs_daily_pnl / longs_prior_mv * 100) if longs_prior_mv else 0.0
    shorts_daily_pnl_pct = (shorts_daily_pnl / shorts_prior_mv * 100) if shorts_prior_mv else 0.0

    # --- YTD / L30D: portfolio value change minus net capital deployed ---
    # Subtract net capital flow (buys - sells) during the period so that
    # rebalancing trades are not counted as investment PnL.
    if daily_series:
        # Find L30D and YTD start entries
        target_30d = (date.fromisoformat(report_date) - timedelta(days=30)).isoformat()
        l30d_entry = None
        for entry in daily_series:
            if entry["date"] <= target_30d:
                l30d_entry = entry
            else:
                break

        report_year = date.fromisoformat(report_date).year
        ytd_start = None
        for entry in daily_series:
            if date.fromisoformat(entry["date"]).year == report_year:
                ytd_start = entry
                break

        # Compute net capital deployed in each window from trade data
        all_trades = _load_portfolio_trades(portfolio_name)

        if l30d_entry:
            l30d_start_date = l30d_entry["date"]
            l30d_mv_start = float(l30d_entry["market_value"])
            l30d_net_capital = 0.0
            for t in all_trades:
                if t["date"] > l30d_start_date and t["date"] <= report_date:
                    amt = float(t["shares"]) * float(t["price"])
                    l30d_net_capital += amt if t["action"] == "buy" else -amt
            l30d_pnl = (total_market_value - l30d_mv_start) - l30d_net_capital
            l30d_pnl_pct = (l30d_pnl / l30d_mv_start * 100) if l30d_mv_start else 0.0

        if ytd_start:
            ytd_start_date = ytd_start["date"]
            ytd_mv_start = float(ytd_start["market_value"])
            ytd_net_capital = 0.0
            for t in all_trades:
                if t["date"] > ytd_start_date and t["date"] <= report_date:
                    amt = float(t["shares"]) * float(t["price"])
                    ytd_net_capital += amt if t["action"] == "buy" else -amt
            ytd_pnl = (total_market_value - ytd_mv_start) - ytd_net_capital
            ytd_pnl_pct = (ytd_pnl / ytd_mv_start * 100) if ytd_mv_start else 0.0

    # --- YTD PnL by side and sector (capital-flow adjusted) ---
    # Compute MV at YTD start by side/sector, and net capital deployed per group
    longs_ytd_pnl = 0.0
    longs_ytd_pnl_pct = 0.0
    shorts_ytd_pnl = 0.0
    shorts_ytd_pnl_pct = 0.0
    sector_ytd: dict[str, dict[str, float]] = {}  # sector -> {mv_start, net_capital, ytd_pnl, ytd_pnl_pct}

    if daily_series:
        report_year = date.fromisoformat(report_date).year
        ytd_start_entry = None
        for entry in daily_series:
            if date.fromisoformat(entry["date"]).year == report_year:
                ytd_start_entry = entry
                break

        if ytd_start_entry:
            ytd_start_date = ytd_start_entry["date"]

            # Holdings and prices at YTD start
            ytd_holdings = _compute_portfolio_holdings(portfolio_name, as_of_date=ytd_start_date)
            longs_mv_start = 0.0
            shorts_mv_start = 0.0
            sector_mv_start: dict[str, float] = {}
            for h in ytd_holdings:
                pr = _price_on_date(h["ticker"], ytd_start_date)
                if pr is None:
                    pr = h["avg_cost"]
                mv_s = h["shares"] * pr
                sec = h["sector"]
                sector_mv_start[sec] = sector_mv_start.get(sec, 0.0) + mv_s
                if h["side"] == "long":
                    longs_mv_start += mv_s
                else:
                    shorts_mv_start += mv_s

            # Net capital deployed per side/sector during YTD window
            all_trades_ytd = _load_portfolio_trades(portfolio_name)
            # Build sector map for trade tickers
            stocks_data = provider.query("stocks", FilterParams(page=1, page_size=600)).data
            ticker_sector = {s["ticker"]: s.get("sector", "Unknown") for s in stocks_data}

            longs_net_capital = 0.0
            shorts_net_capital = 0.0
            sector_net_capital: dict[str, float] = {}
            for t in all_trades_ytd:
                if t["date"] > ytd_start_date and t["date"] <= report_date:
                    amt = float(t["shares"]) * float(t["price"])
                    flow = amt if t["action"] == "buy" else -amt
                    sec = ticker_sector.get(t["ticker"], "Unknown")
                    sector_net_capital[sec] = sector_net_capital.get(sec, 0.0) + flow
                    if t["side"] == "long":
                        longs_net_capital += flow
                    else:
                        shorts_net_capital += flow

            # YTD PnL by side
            longs_ytd_pnl = (longs_market_value - longs_mv_start) - longs_net_capital
            longs_ytd_pnl_pct = (longs_ytd_pnl / longs_mv_start * 100) if longs_mv_start else 0.0
            shorts_ytd_pnl = (shorts_market_value - shorts_mv_start) - shorts_net_capital
            shorts_ytd_pnl_pct = (shorts_ytd_pnl / shorts_mv_start * 100) if shorts_mv_start else 0.0

            # YTD PnL by sector
            all_sectors = set(list(sector_mv_start.keys()) + [p["sector"] for p in position_rows])
            for sec in all_sectors:
                sec_mv_today = sum(abs(p["shares"] * p["price"]) for p in position_rows if p["sector"] == sec)
                sec_mv_s = sector_mv_start.get(sec, 0.0)
                sec_nc = sector_net_capital.get(sec, 0.0)
                sec_ytd = (sec_mv_today - sec_mv_s) - sec_nc
                sec_ytd_pct = (sec_ytd / sec_mv_s * 100) if sec_mv_s else 0.0
                sector_ytd[sec] = {
                    "ytd_pnl": sec_ytd,
                    "ytd_pnl_pct": sec_ytd_pct,
                }

    # --- Sector attribution: computed directly from position-level daily PnL ---
    sector_agg: dict[str, dict[str, float]] = {}
    for p in position_rows:
        sec = p["sector"]
        if sec not in sector_agg:
            sector_agg[sec] = {"mv": 0.0, "daily_pnl": 0.0}
        sector_agg[sec]["mv"] += abs(p["shares"] * p["price"])
        sector_agg[sec]["daily_pnl"] += p["daily_pnl"]

    sector_data: list[dict[str, Any]] = []
    for sec, agg in sector_agg.items():
        sector_mv = agg["mv"]
        sector_weight = (sector_mv / total_market_value * 100) if total_market_value else 0.0
        sector_daily_pnl_pct = (agg["daily_pnl"] / sector_mv * 100) if sector_mv else 0.0
        ytd_info = sector_ytd.get(sec, {"ytd_pnl": 0.0, "ytd_pnl_pct": 0.0})
        sector_data.append({
            "sector": sec,
            "weight": round(sector_weight, 2),
            "daily_pnl": round(agg["daily_pnl"]),
            "daily_pnl_pct": round(sector_daily_pnl_pct, 2),
            "ytd_pnl": round(ytd_info["ytd_pnl"]),
            "ytd_pnl_pct": round(ytd_info["ytd_pnl_pct"], 2),
        })
    sector_data.sort(key=lambda s: s["sector"])

    # --- Top contributors / detractors by DAILY PnL ---
    # Contributors: positions making money (daily_pnl > 0) — longs that went up OR shorts that went down
    # Detractors: positions losing money (daily_pnl < 0) — longs that went down OR shorts that went up
    contributors = sorted([r for r in position_rows if r["daily_pnl"] > 0], key=lambda r: r["daily_pnl"], reverse=True)
    detractors = sorted([r for r in position_rows if r["daily_pnl"] < 0], key=lambda r: r["daily_pnl"])
    top_contributors = contributors[:5]
    top_detractors = detractors[:5]

    # --- Recent trade activity: only trades from the report_date ---
    all_trades = _load_portfolio_trades(portfolio_name)
    recent_trades = [t for t in all_trades if t["date"] == report_date]

    # Classify trades
    holdings_before = {h["ticker"]: h for h in _compute_portfolio_holdings(portfolio_name, as_of_date=prior_date)}
    holdings_after = {h["ticker"]: h for h in holdings}

    trade_rows: list[dict[str, Any]] = []
    new_positions = 0
    full_exits = 0
    for t in recent_trades:
        ticker = t["ticker"]
        was_held = ticker in holdings_before
        is_held = ticker in holdings_after
        if not was_held and is_held:
            trade_type = "New Position"
            new_positions += 1
        elif was_held and not is_held:
            trade_type = "Full Exit"
            full_exits += 1
        elif t["action"] == "buy":
            trade_type = "Addition"
        else:
            trade_type = "Trim"
        notional = float(t["shares"]) * float(t["price"])
        trade_rows.append({
            "ticker": ticker,
            "action": t["action"],
            "side": t["side"],
            "shares": float(t["shares"]),
            "price": float(t["price"]),
            "notional": round(notional, 2),
            "type": trade_type,
        })

    # Sort trades: Action (buy first) → Side (long first) → Type → Shares desc
    action_order = {"sell": 0, "buy": 1}
    side_order = {"short": 0, "long": 1}
    trade_rows.sort(key=lambda t: (
        action_order.get(t["action"], 2),
        side_order.get(t["side"], 2),
        t["type"],
        -t["shares"],
    ))

    # --- Earnings watchlist: only next 4 days from report_date ---
    earnings_watchlist: list[dict[str, Any]] = []
    for p in position_rows:
        if p["earnings_in_next_4"]:
            earnings_watchlist.append({
                "ticker": p["ticker"],
                "report_date": p["earnings_date"],
                "weight": p["weight"],
                "side": p["side"],
            })
    earnings_watchlist.sort(key=lambda e: e["report_date"])

    # =========================================================================
    # HTML Rendering
    # =========================================================================
    sections_html: list[str] = []

    # --- Section 1: Performance Overview ---
    sections_html.append(_html_section_header("Portfolio Performance Overview"))
    sections_html.append(
        _html_table_header(("Metric", "left"), ("Daily", "right"), ("YTD", "right"), ("L30D", "right"))
    )
    sections_html.append(_html_table_row(0,
        ("PnL ($)", "left", "font-weight:600;"),
        (f'<span style="color:{_pnl_color(daily_pnl)};">{_fmt_currency(daily_pnl)}</span>', "right", ""),
        (f'<span style="color:{_pnl_color(ytd_pnl)};">{_fmt_currency(ytd_pnl)}</span>', "right", ""),
        (f'<span style="color:{_pnl_color(l30d_pnl)};">{_fmt_currency(l30d_pnl)}</span>', "right", ""),
    ))
    sections_html.append(_html_table_row(1,
        ("Return (%)", "left", "font-weight:600;"),
        (f'<span style="color:{_pnl_color(daily_pnl_pct)};">{_fmt_pct(daily_pnl_pct)}</span>', "right", ""),
        (f'<span style="color:{_pnl_color(ytd_pnl_pct)};">{_fmt_pct(ytd_pnl_pct)}</span>', "right", ""),
        (f'<span style="color:{_pnl_color(l30d_pnl_pct)};">{_fmt_pct(l30d_pnl_pct)}</span>', "right", ""),
    ))
    sections_html.append(_html_table_row(2,
        ("Market Value", "left", "font-weight:600;"),
        (_fmt_currency(total_market_value), "right", ""),
        ("", "right", ""),
        ("", "right", ""),
    ))
    sections_html.append("</table>")

    # --- Section 2: Side Attribution ---
    sections_html.append(_html_section_header("Side Attribution"))
    sections_html.append(
        _html_table_header(
            ("Side", "left"), ("Market Value", "right"),
            ("Daily PnL ($)", "right"), ("Daily PnL (%)", "right"),
            ("YTD PnL ($)", "right"), ("YTD PnL (%)", "right"),
        )
    )
    lc = _pnl_color(longs_daily_pnl)
    lyc = _pnl_color(longs_ytd_pnl)
    sc = _pnl_color(shorts_daily_pnl)
    syc = _pnl_color(shorts_ytd_pnl)
    sections_html.append(_html_table_row(0,
        ('<span style="color:#276749;font-weight:600;">LONG</span>', "left", ""),
        (_fmt_currency(longs_market_value), "right", ""),
        (f'<span style="color:{lc};">{_fmt_currency(longs_daily_pnl)}</span>', "right", ""),
        (f'<span style="color:{lc};">{_fmt_pct(longs_daily_pnl_pct)}</span>', "right", ""),
        (f'<span style="color:{lyc};">{_fmt_currency(longs_ytd_pnl)}</span>', "right", ""),
        (f'<span style="color:{lyc};">{_fmt_pct(longs_ytd_pnl_pct)}</span>', "right", ""),
    ))
    sections_html.append(_html_table_row(1,
        ('<span style="color:#c53030;font-weight:600;">SHORT</span>', "left", ""),
        (_fmt_currency(shorts_market_value), "right", ""),
        (f'<span style="color:{sc};">{_fmt_currency(shorts_daily_pnl)}</span>', "right", ""),
        (f'<span style="color:{sc};">{_fmt_pct(shorts_daily_pnl_pct)}</span>', "right", ""),
        (f'<span style="color:{syc};">{_fmt_currency(shorts_ytd_pnl)}</span>', "right", ""),
        (f'<span style="color:{syc};">{_fmt_pct(shorts_ytd_pnl_pct)}</span>', "right", ""),
    ))
    sections_html.append("</table>")

    # --- Section 3: Sector Attribution ---
    if sector_data:
        sections_html.append(_html_section_header("Sector Attribution"))
        sections_html.append(
            _html_table_header(
                ("Sector", "left"), ("Weight", "right"),
                ("Daily PnL ($)", "right"), ("Daily PnL (%)", "right"),
                ("YTD PnL ($)", "right"), ("YTD PnL (%)", "right"),
            )
        )
        for i, s in enumerate(sector_data):
            c = _pnl_color(s["daily_pnl"])
            yc = _pnl_color(s["ytd_pnl"])
            sections_html.append(_html_table_row(i,
                (_escape(s["sector"]), "left", "font-weight:600;"),
                (f'{s["weight"]:.1f}%', "right", ""),
                (f'<span style="color:{c};">{_fmt_currency(s["daily_pnl"])}</span>', "right", ""),
                (f'<span style="color:{c};">{_fmt_pct(s["daily_pnl_pct"])}</span>', "right", ""),
                (f'<span style="color:{yc};">{_fmt_currency(s["ytd_pnl"])}</span>', "right", ""),
                (f'<span style="color:{yc};">{_fmt_pct(s["ytd_pnl_pct"])}</span>', "right", ""),
            ))
        sections_html.append("</table>")

    # --- Section 3: Position-Level Drivers (DAILY PnL) ---
    def _render_position_table(title: str, rows: list[dict[str, Any]], is_contributor: bool) -> None:
        # All contributors green, all detractors red
        row_color = "#276749" if is_contributor else "#c53030"
        sections_html.append(f'<p style="font-size:14px;font-weight:600;color:#1a202c;margin:16px 0 4px 0;">{_escape(title)}</p>')
        sections_html.append(
            _html_table_header(
                ("Ticker", "left"), ("Side", "left"), ("Weight", "right"),
                ("Daily PnL ($)", "right"), ("Daily PnL (%)", "right"), ("Sector", "left"), ("Earnings", "left"),
            )
        )
        for i, r in enumerate(rows):
            # Only show earnings flag if ticker had earnings on report_date or prior_date
            ef = f'<span style="color:#d4a843;font-weight:600;">&#9733; Reported</span>' if r["had_earnings_today"] else ""
            # PnL% shows raw stock movement (positive if stock went up, negative if down)
            sections_html.append(_html_table_row(i,
                (_escape(r["ticker"]), "left", "font-weight:600;"),
                (r["side"].upper(), "left", ""),
                (f'{r["weight"]:.1f}%', "right", ""),
                (f'<span style="color:{row_color};">{_fmt_currency(r["daily_pnl"])}</span>', "right", ""),
                (f'<span style="color:{row_color};">{_fmt_pct(r["raw_pnl_pct"])}</span>', "right", ""),
                (_escape(r["sector"]), "left", ""),
                (ef, "left", ""),
            ))
        sections_html.append("</table>")

    sections_html.append(_html_section_header("Position-Level Drivers"))
    _render_position_table("Top 5 Contributors", top_contributors, is_contributor=True)
    _render_position_table("Top 5 Detractors", top_detractors, is_contributor=False)

    # --- Section 4: Recent Trade Activity (only if trades on report_date) ---
    if trade_rows:
        sections_html.append(_html_section_header("Recent Trade Activity"))
        sections_html.append(
            f'<p style="font-size:14px;color:#1a202c;margin:8px 0;">'
            f'Trade date: <strong>{_escape(report_date)}</strong> &mdash; '
            f'{len(recent_trades)} trades, {new_positions} new positions, {full_exits} exits</p>'
        )
        sections_html.append(
            _html_table_header(
                ("Ticker", "left"), ("Action", "left"), ("Side", "left"),
                ("Shares", "right"), ("Price", "right"), ("Notional", "right"), ("Type", "left"),
            )
        )
        for i, t in enumerate(trade_rows):
            # Color code: BUY=green, SELL=red
            action_color = "#276749" if t["action"] == "buy" else "#c53030"
            # Color code: LONG=green, SHORT=red
            side_color = "#276749" if t["side"] == "long" else "#c53030"
            sections_html.append(_html_table_row(i,
                (_escape(t["ticker"]), "left", "font-weight:600;"),
                (f'<span style="color:{action_color};font-weight:600;">{t["action"].upper()}</span>', "left", ""),
                (f'<span style="color:{side_color};font-weight:600;">{t["side"].upper()}</span>', "left", ""),
                (f'{t["shares"]:,.0f}', "right", ""),
                (f'${t["price"]:,.2f}', "right", ""),
                (_fmt_currency(t["notional"]), "right", ""),
                (_escape(t["type"]), "left", ""),
            ))
        sections_html.append("</table>")

    # --- Section 5: Earnings Watchlist (next 4 days only) ---
    sections_html.append(_html_section_header("Earnings Watchlist"))
    if earnings_watchlist:
        sections_html.append(
            f'<p style="font-size:13px;color:#718096;margin:0 0 4px 0;">'
            f'Positions reporting within 4 days of {_escape(report_date)}</p>'
        )
        sections_html.append(
            _html_table_header(
                ("Ticker", "left"), ("Report Date", "left"),
                ("Weight", "right"), ("Side", "left"),
            )
        )
        for i, e in enumerate(earnings_watchlist):
            side_color = "#276749" if e["side"] == "long" else "#c53030"
            sections_html.append(_html_table_row(i,
                (_escape(e["ticker"]), "left", "font-weight:600;"),
                (_escape(e["report_date"]), "left", ""),
                (f'{e["weight"]:.1f}%', "right", ""),
                (f'<span style="color:{side_color};font-weight:600;">{e["side"].upper()}</span>', "left", ""),
            ))
        sections_html.append("</table>")
    else:
        sections_html.append('<p style="font-size:14px;color:#718096;font-style:italic;">No upcoming earnings in the next 4 days.</p>')

    # --- Notes section ---
    sections_html.append(
        f'<div style="margin-top:24px;padding:12px 16px;background:#f7f8fa;border-radius:6px;border:1px solid #e2e8f0;">'
        f'<p style="font-size:11px;color:#718096;margin:0 0 4px 0;font-weight:600;text-transform:uppercase;">Report Notes</p>'
        f'<p style="font-size:12px;color:#718096;margin:0;">'
        f'Daily PnL computed as of <strong>{_escape(report_date)}</strong> vs prior day <strong>{_escape(prior_date)}</strong>. '
        f'Data reflects the latest available prices in stock_history.csv. '
        f'Report generated on {_escape(date.today().isoformat())}.</p>'
        f'</div>'
    )

    # =========================================================================
    # Compose full HTML
    # =========================================================================
    subject = f"GoldMine: {portfolio_name} Daily PnL Report \u2014 {report_date_display}"
    content_html = "\n".join(sections_html)

    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,Helvetica,sans-serif;background:#f7f8fa;margin:0;padding:20px;">
<div style="max-width:800px;margin:0 auto;background:#ffffff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.12);overflow:hidden;">
  <div style="background:#1a365d;padding:16px 24px;">
    <h1 style="color:#d4a843;margin:0;font-size:20px;">GoldMine</h1>
  </div>
  <div style="padding:24px;">
    <div style="margin-bottom:16px;">
      <span style="font-size:22px;font-weight:700;color:#1a202c;">{_escape(portfolio_name)} Daily PnL Report</span>
      <span style="background:#fffbeb;color:#975a16;font-size:11px;font-weight:600;text-transform:uppercase;padding:3px 8px;border-radius:4px;margin-left:8px;">REPORT</span>
    </div>
    <table style="margin-bottom:16px;"><tr>
      <td style="padding:4px 16px 4px 0;vertical-align:top;">
        <span style="color:#718096;font-size:11px;text-transform:uppercase;">As Of</span><br>
        <span style="color:#1a202c;font-weight:500;">{_escape(report_date_display)}</span>
      </td>
      <td style="padding:4px 16px 4px 0;vertical-align:top;">
        <span style="color:#718096;font-size:11px;text-transform:uppercase;">Portfolio</span><br>
        <span style="color:#1a202c;font-weight:500;">{_escape(portfolio_name)}</span>
      </td>
      <td style="padding:4px 16px 4px 0;vertical-align:top;">
        <span style="color:#718096;font-size:11px;text-transform:uppercase;">Strategy</span><br>
        <span style="color:#1a202c;font-weight:500;">{_escape(strategy)}</span>
      </td>
    </tr></table>
    {content_html}
    <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0 12px 0;">
    <p style="color:#718096;font-size:11px;">This is an automated email from GoldMine. Data reflects the latest available at time of delivery.</p>
  </div>
</div>
</body>
</html>"""

    # =========================================================================
    # Plain text fallback
    # =========================================================================
    text_lines = [
        f"GoldMine: {portfolio_name} Daily PnL Report",
        f"As Of: {report_date_display}",
        f"Portfolio: {portfolio_name} ({strategy})",
        "",
        "=== Performance Overview ===",
        f"{'Metric':<20}{'Daily':>15}{'YTD':>15}{'L30D':>15}",
        f"{'PnL ($)':<20}{_fmt_currency(daily_pnl):>15}{_fmt_currency(ytd_pnl):>15}{_fmt_currency(l30d_pnl):>15}",
        f"{'Return (%)':<20}{_fmt_pct(daily_pnl_pct):>15}{_fmt_pct(ytd_pnl_pct):>15}{_fmt_pct(l30d_pnl_pct):>15}",
        f"{'Market Value':<20}{_fmt_currency(total_market_value):>15}",
        "",
        "",
        "=== Side Attribution ===",
        f"{'Side':<8}{'Market Value':>16}{'Daily PnL ($)':>16}{'Daily PnL (%)':>14}{'YTD PnL ($)':>16}{'YTD PnL (%)':>12}",
        f"{'LONG':<8}{_fmt_currency(longs_market_value):>16}{_fmt_currency(longs_daily_pnl):>16}{_fmt_pct(longs_daily_pnl_pct):>14}{_fmt_currency(longs_ytd_pnl):>16}{_fmt_pct(longs_ytd_pnl_pct):>12}",
        f"{'SHORT':<8}{_fmt_currency(shorts_market_value):>16}{_fmt_currency(shorts_daily_pnl):>16}{_fmt_pct(shorts_daily_pnl_pct):>14}{_fmt_currency(shorts_ytd_pnl):>16}{_fmt_pct(shorts_ytd_pnl_pct):>12}",
        "",
    ]

    if sector_data:
        text_lines.append("=== Sector Attribution ===")
        text_lines.append(f"{'Sector':<25}{'Weight':>8}{'Daily PnL ($)':>16}{'Daily (%)':>12}{'YTD PnL ($)':>16}{'YTD (%)':>10}")
        for s in sector_data:
            text_lines.append(f'{s["sector"]:<25}{s["weight"]:>7.1f}%{_fmt_currency(s["daily_pnl"]):>16}{_fmt_pct(s["daily_pnl_pct"]):>12}{_fmt_currency(s["ytd_pnl"]):>16}{_fmt_pct(s["ytd_pnl_pct"]):>10}')
        text_lines.append("")

    text_lines.append("=== Top 5 Contributors (Daily) ===")
    text_lines.append(f"{'Ticker':<8}{'Side':<6}{'Weight':>7}{'Daily PnL ($)':>16}{'Daily PnL (%)':>12}{'Sector':<20}")
    for r in top_contributors:
        ef = " [E]" if r["had_earnings_today"] else ""
        text_lines.append(f'{r["ticker"]:<8}{r["side"]:<6}{r["weight"]:>6.1f}%{_fmt_currency(r["daily_pnl"]):>16}{_fmt_pct(r["raw_pnl_pct"]):>12}  {r["sector"]}{ef}')
    text_lines.append("")

    text_lines.append("=== Top 5 Detractors (Daily) ===")
    text_lines.append(f"{'Ticker':<8}{'Side':<6}{'Weight':>7}{'Daily PnL ($)':>16}{'Daily PnL (%)':>12}{'Sector':<20}")
    for r in top_detractors:
        ef = " [E]" if r["had_earnings_today"] else ""
        text_lines.append(f'{r["ticker"]:<8}{r["side"]:<6}{r["weight"]:>6.1f}%{_fmt_currency(r["daily_pnl"]):>16}{_fmt_pct(r["raw_pnl_pct"]):>12}  {r["sector"]}{ef}')
    text_lines.append("")

    if trade_rows:
        text_lines.append("=== Recent Trade Activity ===")
        text_lines.append(f"Trade date: {report_date} -- {len(recent_trades)} trades, {new_positions} new, {full_exits} exits")
        text_lines.append(f"{'Ticker':<8}{'Action':<6}{'Side':<6}{'Shares':>10}{'Price':>10}{'Notional':>14}  {'Type':<15}")
        for t in trade_rows:
            text_lines.append(f'{t["ticker"]:<8}{t["action"]:<6}{t["side"]:<6}{t["shares"]:>10,.0f}{t["price"]:>10,.2f}{_fmt_currency(t["notional"]):>14}  {t["type"]}')
        text_lines.append("")

    text_lines.append("=== Earnings Watchlist (Next 4 Days) ===")
    if earnings_watchlist:
        text_lines.append(f"{'Ticker':<8}{'Date':<12}{'Weight':>7}  {'Side':<6}")
        for e in earnings_watchlist:
            text_lines.append(f'{e["ticker"]:<8}{e["report_date"]:<12}{e["weight"]:>6.1f}%  {e["side"]}')
    else:
        text_lines.append("No upcoming earnings in the next 4 days.")
    text_lines.append("")
    text_lines.append(f"--- Notes ---")
    text_lines.append(f"Daily PnL as of {report_date} vs prior day {prior_date}.")
    text_lines.append(f"Report generated on {date.today().isoformat()}.")
    text_lines.append("")
    text_lines.append("---")
    text_lines.append("This is an automated email from GoldMine.")

    text_body = "\n".join(text_lines)

    return subject, html_body, text_body, []
