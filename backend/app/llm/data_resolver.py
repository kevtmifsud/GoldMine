from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from app.config.settings import settings
from app.data_access.factory import get_data_provider
from app.data_access.models import FilterParams
from app.logging_config import get_logger
from app.studios.models import DataSource

logger = get_logger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "structured"

_FINANCIALS_DIR = _DATA_DIR / "financials"

_CSV_FILES = {
    ("income_statement", "annual"): _FINANCIALS_DIR / "annual_income_statements.csv",
    ("income_statement", "quarterly"): _FINANCIALS_DIR / "quarterly_income_statements.csv",
    ("balance_sheet", "annual"): _FINANCIALS_DIR / "annual_balance_sheets.csv",
    ("balance_sheet", "quarterly"): _FINANCIALS_DIR / "quarterly_balance_sheets.csv",
    ("cash_flow", "annual"): _FINANCIALS_DIR / "annual_cash_flows.csv",
    ("cash_flow", "quarterly"): _FINANCIALS_DIR / "quarterly_cash_flows.csv",
}


def resolve_data_source(data_source: DataSource) -> list[dict[str, Any]]:
    """Resolve a DataSource descriptor into actual data rows."""
    resolver = _RESOLVERS.get(data_source.type)
    if not resolver:
        logger.warning("unknown_data_source_type", type=data_source.type)
        return []
    try:
        return resolver(data_source)
    except Exception as e:
        logger.error("data_resolve_error", type=data_source.type, error=str(e))
        return []


def _resolve_financials(ds: DataSource) -> list[dict[str, Any]]:
    """Resolve financial statement data for a ticker."""
    ticker = (ds.ticker or "").upper()
    statement_type = ds.statement_type or "income_statement"
    period = ds.period or "annual"
    metrics = ds.metrics or []

    key = (statement_type, period)
    csv_path = _CSV_FILES.get(key)
    if not csv_path or not csv_path.exists():
        return []

    # Read relevant rows from the CSV
    raw: dict[str, dict[str, float | None]] = {}
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["ticker"] != ticker:
                continue
            metric = row["metric"]
            if metrics and metric not in metrics:
                continue
            date = row["date"]
            try:
                value = float(row["value"])
            except (ValueError, TypeError):
                value = None
            if metric not in raw:
                raw[metric] = {}
            raw[metric][date] = value

    # Get sorted dates
    all_dates: set[str] = set()
    for metric_dates in raw.values():
        all_dates.update(metric_dates.keys())
    dates = sorted(all_dates)

    if not dates:
        return []

    # If exactly one metric, return simple [{date, value}, ...]
    if len(raw) == 1:
        metric_name = list(raw.keys())[0]
        values = raw[metric_name]
        return [{"date": d, "value": values.get(d)} for d in dates if values.get(d) is not None]

    # Multiple metrics: return [{date, metric1, metric2, ...}, ...]
    result: list[dict[str, Any]] = []
    for d in dates:
        row: dict[str, Any] = {"date": d}
        has_any = False
        for metric_name, values in raw.items():
            v = values.get(d)
            row[metric_name] = v
            if v is not None:
                has_any = True
        if has_any:
            result.append(row)
    return result


def _resolve_dataset(ds: DataSource) -> list[dict[str, Any]]:
    """Resolve data from a CSV dataset via the data provider."""
    dataset = ds.dataset or ""
    if not dataset:
        return []

    provider = get_data_provider()
    filters = ds.filters or {}
    params = FilterParams(
        page=1,
        page_size=min(ds.limit or 100, 500),
        sort_by=ds.sort_by,
        sort_order=ds.sort_order or "asc",
        filters=filters,
    )
    response = provider.query(dataset, params)
    return response.data


def _resolve_price_history(ds: DataSource) -> list[dict[str, Any]]:
    """Resolve stock price history for a ticker."""
    ticker = (ds.ticker or "").upper()
    if not ticker:
        return []

    csv_path = _DATA_DIR / "stock_history.csv"
    if not csv_path.exists():
        return []

    rows: list[dict[str, Any]] = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["ticker"] != ticker:
                continue
            try:
                close = float(row["close"])
            except (ValueError, TypeError):
                continue
            rows.append({"date": row["date"], "close": close})

    return rows


def _resolve_portfolio_pnl(ds: DataSource) -> list[dict[str, Any]]:
    """Resolve portfolio daily PnL series."""
    portfolio_name = ds.portfolio_name or "Flagship"

    # Import the compute function from entities
    try:
        from app.api.entities import _compute_daily_pnl_series
        series = _compute_daily_pnl_series(portfolio_name)
        # Convert to simpler format
        result: list[dict[str, Any]] = []
        for point in series:
            result.append({
                "date": point["date"],
                "daily_pnl": float(point.get("daily_pnl", 0)),
                "cumulative_pnl": float(point.get("cumulative_pnl", 0)),
            })
        return result
    except Exception as e:
        logger.error("portfolio_pnl_resolve_error", error=str(e))
        return []


def _resolve_multi_price_indexed(ds: DataSource) -> list[dict[str, Any]]:
    """Resolve indexed price history for multiple tickers.

    Merges closing prices by date and optionally indexes all series
    to 100 from the first common date.
    """
    tickers = [t.upper() for t in (ds.tickers or [])]
    if not tickers:
        return []

    csv_path = _DATA_DIR / "stock_history.csv"
    if not csv_path.exists():
        return []

    # Load prices per ticker
    prices: dict[str, dict[str, float]] = {t: {} for t in tickers}
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            t = row["ticker"]
            if t not in prices:
                continue
            try:
                close = float(row["close"])
            except (ValueError, TypeError):
                continue
            prices[t][row["date"]] = close

    # Find common dates (dates where ALL tickers have data)
    date_sets = [set(p.keys()) for p in prices.values() if p]
    if not date_sets:
        return []
    common_dates = sorted(set.intersection(*date_sets))
    if not common_dates:
        return []

    # Build merged rows
    if ds.indexed and common_dates:
        # Index each series to 100 from first common date
        base_date = common_dates[0]
        bases = {t: prices[t].get(base_date, 1.0) for t in tickers}
        result: list[dict[str, Any]] = []
        for d in common_dates:
            row: dict[str, Any] = {"date": d}
            for t in tickers:
                base = bases[t] if bases[t] != 0 else 1.0
                row[t] = round((prices[t][d] / base) * 100, 2)
            result.append(row)
        return result
    else:
        result = []
        for d in common_dates:
            row: dict[str, Any] = {"date": d}
            for t in tickers:
                row[t] = prices[t][d]
            result.append(row)
        return result


def _resolve_multi_financials(ds: DataSource) -> list[dict[str, Any]]:
    """Resolve a single financial metric across multiple tickers.

    Returns rows like {date: "2024-12-31", AAPL: 6.42, MSFT: 11.53, GOOGL: 5.80}.
    """
    tickers = [t.upper() for t in (ds.tickers or [])]
    metric = ds.metric or ""
    if not tickers or not metric:
        return []

    statement_type = ds.statement_type or "income_statement"
    period = ds.period or "annual"

    key = (statement_type, period)
    csv_path = _CSV_FILES.get(key)
    if not csv_path or not csv_path.exists():
        return []

    # Collect {ticker: {date: value}} for the specified metric
    ticker_data: dict[str, dict[str, float]] = {t: {} for t in tickers}
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            t = row["ticker"]
            if t not in ticker_data:
                continue
            if row["metric"] != metric:
                continue
            try:
                value = float(row["value"])
            except (ValueError, TypeError):
                continue
            ticker_data[t][row["date"]] = value

    # Find all dates where at least one ticker has data
    all_dates: set[str] = set()
    for dates in ticker_data.values():
        all_dates.update(dates.keys())
    if not all_dates:
        return []

    dates = sorted(all_dates)
    result: list[dict[str, Any]] = []
    for d in dates:
        row_out: dict[str, Any] = {"date": d}
        has_any = False
        for t in tickers:
            v = ticker_data[t].get(d)
            row_out[t] = v
            if v is not None:
                has_any = True
        if has_any:
            result.append(row_out)
    return result


_RESOLVERS = {
    "financials": _resolve_financials,
    "dataset": _resolve_dataset,
    "price_history": _resolve_price_history,
    "portfolio_pnl": _resolve_portfolio_pnl,
    "multi_price_indexed": _resolve_multi_price_indexed,
    "multi_financials": _resolve_multi_financials,
}
