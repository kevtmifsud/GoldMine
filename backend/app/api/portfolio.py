from __future__ import annotations

import bisect
from datetime import date as _date_type
from typing import Any

from fastapi import APIRouter, Query

from app.api.entities import _build_price_index, _price_on_date

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

# Ticker alias map — bidirectional.  Extend as needed.
_TICKER_ALIASES: dict[str, list[str]] = {
    "GOOGL": ["GOOG"],
    "GOOG": ["GOOGL"],
}


def _ticker_variants(ticker: str) -> set[str]:
    """Return the ticker plus any known aliases."""
    variants = {ticker}
    for alias in _TICKER_ALIASES.get(ticker, []):
        variants.add(alias)
    return variants


def _load_trades_for_ticker(
    ticker: str, portfolio: str | None = None
) -> list[dict[str, str]]:
    """Load all trades matching *ticker* (including aliases), sorted by date."""
    from app.data_access.db import get_sync_conn
    variants = list(_ticker_variants(ticker))
    conn = get_sync_conn()
    cur = conn.cursor()
    if portfolio:
        cur.execute(
            "SELECT date, ticker, action, shares, price, portfolio, side "
            "FROM portfolio_trades "
            "WHERE ticker = ANY(%s) AND portfolio = %s ORDER BY date",
            (variants, portfolio),
        )
    else:
        cur.execute(
            "SELECT date, ticker, action, shares, price, portfolio, side "
            "FROM portfolio_trades WHERE ticker = ANY(%s) ORDER BY date",
            (variants,),
        )
    columns = [desc[0] for desc in cur.description]
    rows = [{col: str(val) if val is not None else "" for col, val in zip(columns, row)}
            for row in cur.fetchall()]
    cur.close()
    return rows


def _load_all_portfolio_trades(portfolio_name: str) -> list[dict[str, str]]:
    """Load *all* trades in a portfolio (every ticker), sorted by date."""
    from app.data_access.db import get_sync_conn
    conn = get_sync_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, ticker, action, shares, price, portfolio, side "
        "FROM portfolio_trades WHERE portfolio = %s ORDER BY date",
        (portfolio_name,),
    )
    columns = [desc[0] for desc in cur.description]
    rows = [{col: str(val) if val is not None else "" for col, val in zip(columns, row)}
            for row in cur.fetchall()]
    cur.close()
    return rows


def _get_current_price(ticker: str) -> float | None:
    """Get the most recent price, trying ticker + aliases."""
    for variant in _ticker_variants(ticker):
        price = _price_on_date(variant, "9999-12-31")
        if price is not None:
            return price
    return None


def _get_price_for_ticker(ticker: str, date: str) -> float | None:
    """Get price on a date, trying ticker + aliases."""
    for variant in _ticker_variants(ticker):
        price = _price_on_date(variant, date)
        if price is not None:
            return price
    return None


def _distinct_portfolios_for_ticker(ticker: str) -> list[str]:
    """Return sorted list of distinct portfolio names that traded this ticker."""
    from app.data_access.db import get_sync_conn
    variants = list(_ticker_variants(ticker))
    conn = get_sync_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT portfolio FROM portfolio_trades "
        "WHERE ticker = ANY(%s) ORDER BY portfolio",
        (variants,),
    )
    names = [row[0] for row in cur.fetchall()]
    cur.close()
    return names


def _is_opening(action: str, side: str) -> bool:
    return (action == "buy" and side == "long") or (
        action == "sell" and side == "short"
    )


_PRICE_SERIES_START = "2021-01-01"


def _get_daily_prices(ticker: str) -> tuple[list[str], list[float]]:
    """Return (dates, prices) for *ticker* from 2021-01-01, trying aliases."""
    index = _build_price_index()
    for variant in _ticker_variants(ticker):
        entry = index.get(variant)
        if entry:
            dates, prices = entry
            start = bisect.bisect_left(dates, _PRICE_SERIES_START)
            return dates[start:], prices[start:]
    return [], []


def _compute_price_weight_series(
    ticker_upper: str,
    portfolio_name: str,
    ticker_trades: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Build a daily stock-price series from 2021 with portfolio weight & dollar value.

    Both portfolio_pct and portfolio_dollars are computed **daily** using each
    day's stock prices so the chart reflects real market-value movements, not
    flat forward-filled snapshots from trade dates.
    """
    daily_dates, daily_prices = _get_daily_prices(ticker_upper)
    if not daily_dates:
        return []

    # If we have trades + portfolio context, compute daily weight & dollars.
    # We walk through daily dates, advancing the portfolio trade log as we go,
    # then price every open position on each date.
    all_trades: list[dict[str, str]] = []
    ticker_variants: set[str] = set()
    positions: dict[str, dict[str, Any]] = {}
    trade_idx = 0
    has_position = False  # True once the ticker has been traded

    if ticker_trades and portfolio_name:
        all_trades = _load_all_portfolio_trades(portfolio_name)
        ticker_variants = _ticker_variants(ticker_upper)

    series: list[dict[str, Any]] = []
    for date, price in zip(daily_dates, daily_prices):
        # Advance portfolio trades up to this date
        while trade_idx < len(all_trades) and all_trades[trade_idx]["date"] <= date:
            t = all_trades[trade_idx]
            tk = t["ticker"]
            action = t["action"]
            side = t["side"]
            shares = float(t["shares"])
            tprice = float(t["price"])

            if tk not in positions:
                positions[tk] = {"side": side, "shares": 0.0, "total_cost": 0.0}

            pos = positions[tk]
            if _is_opening(action, side):
                pos["total_cost"] += shares * tprice
                pos["shares"] += shares
            else:
                if pos["shares"] > 0:
                    ratio = min(shares / pos["shares"], 1.0)
                    pos["total_cost"] *= 1 - ratio
                    pos["shares"] -= shares
                    if pos["shares"] <= 0.5:
                        del positions[tk]

            if tk in ticker_variants:
                has_position = True

            trade_idx += 1

        # Compute portfolio weight and dollar value for this day
        portfolio_pct: float | None = None
        portfolio_dollars: float | None = None

        if has_position and positions:
            ticker_mv = 0.0
            total_mv = 0.0
            for tk, pos in positions.items():
                if pos["shares"] < 0.5:
                    continue
                pk = _price_on_date(tk, date)
                if pk is None:
                    pk = pos["total_cost"] / pos["shares"] if pos["shares"] > 0 else 0
                mv = pos["shares"] * pk
                total_mv += abs(mv)
                if tk in ticker_variants:
                    ticker_mv += abs(mv)

            if ticker_mv > 0:
                portfolio_pct = round(
                    (ticker_mv / total_mv * 100) if total_mv > 0 else 0, 2
                )
                portfolio_dollars = round(ticker_mv)

        series.append({
            "date": date,
            "stock_price": round(price, 2),
            "portfolio_pct": portfolio_pct,
            "portfolio_dollars": portfolio_dollars,
        })

    return series


@router.get("/{ticker}")
async def get_ticker_portfolio(
    ticker: str,
    portfolio: str | None = Query(default=None),
) -> dict[str, Any]:
    """Return full portfolio data for a single ticker (positions, PnL, trades)."""
    ticker_upper = ticker.upper()

    # Always return distinct portfolios (before filtering)
    portfolios = _distinct_portfolios_for_ticker(ticker_upper)

    trades = _load_trades_for_ticker(ticker_upper, portfolio=portfolio)

    current_price = _get_current_price(ticker_upper)
    if current_price is None:
        current_price = 0.0

    # ------------------------------------------------------------------
    # Replay trades per (portfolio, side) group
    # ------------------------------------------------------------------
    groups: dict[tuple[str, str], dict[str, Any]] = {}

    for trade in trades:
        port = trade["portfolio"]
        side = trade["side"]
        key = (port, side)
        action = trade["action"]
        shares = float(trade["shares"])
        price = float(trade["price"])
        date = trade["date"]

        if key not in groups:
            groups[key] = {
                "portfolio": port,
                "side": side,
                "shares": 0.0,
                "total_cost": 0.0,
                "realized_pnl": 0.0,
                "total_shares_traded": 0.0,
                "total_cost_invested": 0.0,
                "first_trade_date": date,
                "last_trade_date": date,
            }

        g = groups[key]
        g["last_trade_date"] = date
        g["total_shares_traded"] += shares

        if _is_opening(action, side):
            g["total_cost"] += shares * price
            g["total_cost_invested"] += shares * price
            g["shares"] += shares
        else:
            if g["shares"] > 0:
                avg_cost = g["total_cost"] / g["shares"]
                close_shares = min(shares, g["shares"])
                if side == "long":
                    g["realized_pnl"] += (price - avg_cost) * close_shares
                else:
                    g["realized_pnl"] += (avg_cost - price) * close_shares
                ratio = close_shares / g["shares"]
                g["total_cost"] *= 1 - ratio
                g["shares"] -= close_shares

    # ------------------------------------------------------------------
    # Build open / closed position lists
    # ------------------------------------------------------------------
    open_positions: list[dict[str, Any]] = []
    closed_positions: list[dict[str, Any]] = []

    total_realized = 0.0
    total_unrealized = 0.0

    for key, g in groups.items():
        total_realized += g["realized_pnl"]

        if g["shares"] > 0.5:
            avg_cost = g["total_cost"] / g["shares"] if g["shares"] > 0 else 0
            market_value = g["shares"] * current_price
            cost_basis = g["total_cost"]
            if g["side"] == "long":
                unrealized = market_value - cost_basis
            else:
                unrealized = cost_basis - market_value
            unrealized_pct = (unrealized / cost_basis * 100) if cost_basis else 0

            total_unrealized += unrealized

            open_positions.append(
                {
                    "portfolio": g["portfolio"],
                    "side": g["side"],
                    "shares": round(g["shares"]),
                    "avg_cost": round(avg_cost, 2),
                    "current_price": round(current_price, 2),
                    "market_value": round(market_value, 2),
                    "cost_basis": round(cost_basis, 2),
                    "unrealized_pnl": round(unrealized, 2),
                    "unrealized_pnl_pct": round(unrealized_pct, 2),
                    "realized_pnl": round(g["realized_pnl"], 2),
                    "first_trade_date": g["first_trade_date"],
                    "last_trade_date": g["last_trade_date"],
                }
            )
        else:
            closed_positions.append(
                {
                    "portfolio": g["portfolio"],
                    "side": g["side"],
                    "total_shares_traded": round(g["total_shares_traded"]),
                    "realized_pnl": round(g["realized_pnl"], 2),
                    "first_trade_date": g["first_trade_date"],
                    "last_trade_date": g["last_trade_date"],
                }
            )

    # Compute portfolio weight percentage for each open position
    # We need each position's weight relative to the ENTIRE portfolio, not just
    # this ticker.  Replay all trades per portfolio to get total market value.
    portfolio_total_mv: dict[str, float] = {}
    distinct_portfolios = {p["portfolio"] for p in open_positions}
    for pname in distinct_portfolios:
        all_trades = _load_all_portfolio_trades(pname)
        holdings: dict[str, dict[str, Any]] = {}
        for t in all_trades:
            tk = t["ticker"]
            action = t["action"]
            side = t["side"]
            shares = float(t["shares"])
            price = float(t["price"])

            if tk not in holdings:
                holdings[tk] = {"side": side, "shares": 0.0, "total_cost": 0.0}

            h = holdings[tk]
            if _is_opening(action, side):
                h["total_cost"] += shares * price
                h["shares"] += shares
            else:
                if h["shares"] > 0:
                    ratio = min(shares / h["shares"], 1.0)
                    h["total_cost"] *= 1 - ratio
                    h["shares"] -= shares
                    if h["shares"] <= 0.5:
                        del holdings[tk]

        total_mv = 0.0
        for tk, h in holdings.items():
            if h["shares"] < 0.5:
                continue
            pk = _get_current_price(tk)
            if pk is None:
                pk = h["total_cost"] / h["shares"] if h["shares"] > 0 else 0
            total_mv += abs(h["shares"] * pk)
        portfolio_total_mv[pname] = total_mv

    for p in open_positions:
        total_mv = portfolio_total_mv.get(p["portfolio"], 0)
        p["portfolio_pct"] = round(
            abs(p["market_value"]) / total_mv * 100, 2
        ) if total_mv > 0 else 0.0

    lifetime_pnl = total_realized + total_unrealized
    total_cost_invested = sum(g["total_cost_invested"] for g in groups.values())

    # ------------------------------------------------------------------
    # PnL time series (daily, from first trade to last available price)
    # ------------------------------------------------------------------
    pnl_series: list[dict[str, Any]] = []
    ts_groups: dict[tuple[str, str], dict[str, Any]] = {}

    if trades:
        # Build trade lookup by date
        trades_by_date: dict[str, list[dict[str, str]]] = {}
        for trade in trades:
            trades_by_date.setdefault(trade["date"], []).append(trade)

        # Get daily trading dates from price data
        daily_dates, _ = _get_daily_prices(ticker_upper)
        first_trade_date = trades[0]["date"]
        last_trade_date = trades[-1]["date"]

        # Find the range: first trade date to the later of last trade date
        # or last available price date
        start_idx = bisect.bisect_left(daily_dates, first_trade_date)
        end_date = max(last_trade_date, daily_dates[-1] if daily_dates else last_trade_date)
        end_idx = bisect.bisect_right(daily_dates, end_date)
        relevant_dates = daily_dates[start_idx:end_idx]

        # Track whether position is fully closed to stop emitting points
        position_closed = False

        for date in relevant_dates:
            # Apply any trades on this date
            for trade in trades_by_date.get(date, []):
                port = trade["portfolio"]
                side = trade["side"]
                key = (port, side)
                action = trade["action"]
                t_shares = float(trade["shares"])
                t_price = float(trade["price"])

                if key not in ts_groups:
                    ts_groups[key] = {
                        "side": side,
                        "shares": 0.0,
                        "total_cost": 0.0,
                        "realized_pnl": 0.0,
                        "total_cost_invested": 0.0,
                    }

                tg = ts_groups[key]

                if _is_opening(action, side):
                    tg["total_cost"] += t_shares * t_price
                    tg["total_cost_invested"] += t_shares * t_price
                    tg["shares"] += t_shares
                    position_closed = False
                else:
                    if tg["shares"] > 0:
                        avg_cost = tg["total_cost"] / tg["shares"]
                        close_shares = min(t_shares, tg["shares"])
                        if side == "long":
                            tg["realized_pnl"] += (t_price - avg_cost) * close_shares
                        else:
                            tg["realized_pnl"] += (avg_cost - t_price) * close_shares
                        ratio = close_shares / tg["shares"]
                        tg["total_cost"] *= 1 - ratio
                        tg["shares"] -= close_shares

            if not ts_groups:
                continue

            # Check if all positions are closed
            all_closed = all(v["shares"] < 0.5 for v in ts_groups.values())

            # Skip dates after position was fully closed (no change)
            if position_closed and all_closed:
                continue

            # Snapshot PnL
            cum_realized = sum(v["realized_pnl"] for v in ts_groups.values())
            cum_unrealized = 0.0
            for v in ts_groups.values():
                if v["shares"] > 0.5:
                    mark = _get_price_for_ticker(ticker_upper, date)
                    if mark is None:
                        mark = v["total_cost"] / v["shares"] if v["shares"] > 0 else 0
                    mv = v["shares"] * mark
                    if v["side"] == "long":
                        cum_unrealized += mv - v["total_cost"]
                    else:
                        cum_unrealized += v["total_cost"] - mv

            ts_total_invested = sum(v["total_cost_invested"] for v in ts_groups.values())
            cum_total = cum_realized + cum_unrealized
            pnl_series.append(
                {
                    "date": date,
                    "cumulative_pnl": round(cum_total, 2),
                    "realized_pnl": round(cum_realized, 2),
                    "unrealized_pnl": round(cum_unrealized, 2),
                    "cumulative_pnl_pct": round(cum_total / ts_total_invested * 100, 2) if ts_total_invested > 0 else 0.0,
                    "realized_pnl_pct": round(cum_realized / ts_total_invested * 100, 2) if ts_total_invested > 0 else 0.0,
                    "unrealized_pnl_pct": round(cum_unrealized / ts_total_invested * 100, 2) if ts_total_invested > 0 else 0.0,
                }
            )

            if all_closed:
                position_closed = True

        # Carry forward the final PnL values to today's date so the chart
        # always extends to the current date (even for closed positions
        # where realized PnL is locked in).
        if pnl_series:
            last_data_date = pnl_series[-1]["date"]
            today_str = _date_type.today().isoformat()
            if last_data_date < today_str:
                pnl_series.append({**pnl_series[-1], "date": today_str})

    # ------------------------------------------------------------------
    # YTD PnL
    # ------------------------------------------------------------------
    eoy_date = "2025-12-31"

    eoy_groups: dict[tuple[str, str], dict[str, Any]] = {}
    for trade in trades:
        if trade["date"] > eoy_date:
            break
        port = trade["portfolio"]
        side = trade["side"]
        key = (port, side)
        action = trade["action"]
        shares_t = float(trade["shares"])
        price_t = float(trade["price"])

        if key not in eoy_groups:
            eoy_groups[key] = {"side": side, "shares": 0.0, "total_cost": 0.0, "realized_pnl": 0.0}

        eg = eoy_groups[key]
        if _is_opening(action, side):
            eg["total_cost"] += shares_t * price_t
            eg["shares"] += shares_t
        else:
            if eg["shares"] > 0:
                ratio = min(shares_t / eg["shares"], 1.0)
                eg["total_cost"] *= 1 - ratio
                eg["shares"] -= shares_t

    eoy_unrealized = 0.0
    for v in eoy_groups.values():
        if v["shares"] > 0.5:
            eoy_price = _get_price_for_ticker(ticker_upper, eoy_date)
            if eoy_price is None:
                eoy_price = v["total_cost"] / v["shares"] if v["shares"] > 0 else 0
            mv = v["shares"] * eoy_price
            if v["side"] == "long":
                eoy_unrealized += mv - v["total_cost"]
            else:
                eoy_unrealized += v["total_cost"] - mv

    eoy_realized = 0.0
    full_replay: dict[tuple[str, str], dict[str, Any]] = {}
    for trade in trades:
        port = trade["portfolio"]
        side = trade["side"]
        key = (port, side)
        action = trade["action"]
        shares_t = float(trade["shares"])
        price_t = float(trade["price"])

        if key not in full_replay:
            full_replay[key] = {"side": side, "shares": 0.0, "total_cost": 0.0, "realized_pnl": 0.0}

        fr = full_replay[key]
        if _is_opening(action, side):
            fr["total_cost"] += shares_t * price_t
            fr["shares"] += shares_t
        else:
            if fr["shares"] > 0:
                avg_c = fr["total_cost"] / fr["shares"]
                cs = min(shares_t, fr["shares"])
                if side == "long":
                    fr["realized_pnl"] += (price_t - avg_c) * cs
                else:
                    fr["realized_pnl"] += (avg_c - price_t) * cs
                ratio = cs / fr["shares"]
                fr["total_cost"] *= 1 - ratio
                fr["shares"] -= cs

        if trade["date"] <= eoy_date:
            eoy_realized = sum(v["realized_pnl"] for v in full_replay.values())

    ytd_realized = total_realized - eoy_realized
    ytd_unrealized = total_unrealized - eoy_unrealized
    ytd_pnl = ytd_realized + ytd_unrealized

    # ------------------------------------------------------------------
    # Price + weight series
    # ------------------------------------------------------------------
    price_weight_series: list[dict[str, Any]] = []
    if portfolio and trades:
        price_weight_series = _compute_price_weight_series(
            ticker_upper, portfolio, trades
        )
    else:
        # Always provide a price-only series so the chart renders
        daily_dates, daily_prices = _get_daily_prices(ticker_upper)
        price_weight_series = [
            {"date": d, "stock_price": round(p, 2), "portfolio_pct": None, "portfolio_dollars": None}
            for d, p in zip(daily_dates, daily_prices)
        ]

    # ------------------------------------------------------------------
    # Trade list for the grid
    # ------------------------------------------------------------------
    trade_list = [
        {
            "date": t["date"],
            "action": t["action"],
            "shares": int(float(t["shares"])),
            "price": round(float(t["price"]), 2),
            "portfolio": t["portfolio"],
            "side": t["side"],
            "notional": round(float(t["shares"]) * float(t["price"]), 2),
        }
        for t in trades
    ]

    first_trade = trades[0]["date"] if trades else None
    last_trade = trades[-1]["date"] if trades else None

    return {
        "ticker": ticker_upper,
        "current_price": round(current_price, 2),
        "portfolios": portfolios,
        "summary": {
            "lifetime_pnl": round(lifetime_pnl, 2),
            "lifetime_realized_pnl": round(total_realized, 2),
            "lifetime_unrealized_pnl": round(total_unrealized, 2),
            "lifetime_pnl_pct": round(lifetime_pnl / total_cost_invested * 100, 2) if total_cost_invested > 0 else 0.0,
            "lifetime_realized_pnl_pct": round(total_realized / total_cost_invested * 100, 2) if total_cost_invested > 0 else 0.0,
            "lifetime_unrealized_pnl_pct": round(total_unrealized / total_cost_invested * 100, 2) if total_cost_invested > 0 else 0.0,
            "ytd_pnl": round(ytd_pnl, 2),
            "ytd_realized_pnl": round(ytd_realized, 2),
            "ytd_unrealized_pnl": round(ytd_unrealized, 2),
            "ytd_pnl_pct": round(ytd_pnl / total_cost_invested * 100, 2) if total_cost_invested > 0 else 0.0,
            "ytd_realized_pnl_pct": round(ytd_realized / total_cost_invested * 100, 2) if total_cost_invested > 0 else 0.0,
            "ytd_unrealized_pnl_pct": round(ytd_unrealized / total_cost_invested * 100, 2) if total_cost_invested > 0 else 0.0,
            "active_position_count": len(open_positions),
            "total_trade_count": len(trades),
            "first_trade_date": first_trade,
            "last_trade_date": last_trade,
        },
        "open_positions": open_positions,
        "closed_positions": closed_positions,
        "trades": trade_list,
        "pnl_series": pnl_series,
        "price_weight_series": price_weight_series,
    }
