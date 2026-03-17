from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.mode2.db import get_conn

router = APIRouter(prefix="/api/financials", tags=["financials"])


async def _read_financial_db(
    ticker: str, period_type: str,
) -> dict[str, dict[str, float | None]]:
    """Read financial data from Supabase, returning {metric: {date: value}}."""
    result: dict[str, dict[str, float | None]] = {}
    async with get_conn() as conn:
        rows = await conn.fetch(
            """SELECT metric_name, period_end, value
               FROM financial_metrics
               WHERE ticker = $1 AND period_type = $2
               ORDER BY period_end""",
            ticker, period_type,
        )
    for row in rows:
        metric = row["metric_name"]
        date_str = str(row["period_end"])  # date → "YYYY-MM-DD"
        result.setdefault(metric, {})[date_str] = (
            float(row["value"]) if row["value"] is not None else None
        )
    return result


async def _get_fy_end_month(ticker: str) -> int:
    """Determine fiscal year end month from annual income statement dates."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            """SELECT period_end FROM financial_metrics
               WHERE ticker = $1 AND period_type = 'annual'
               ORDER BY period_end DESC LIMIT 1""",
            ticker,
        )
    return row["period_end"].month if row and row["period_end"] else 12


def _get_sorted_dates(data: dict[str, dict[str, float | None]]) -> list[str]:
    """Get sorted unique dates across all metrics."""
    all_dates: set[str] = set()
    for metric_dates in data.values():
        all_dates.update(metric_dates.keys())
    return sorted(all_dates)


def _compute_growth(
    values: dict[str, float | None], dates: list[str], lookback: int = 1,
) -> dict[str, float | None]:
    """Compute growth percentages vs N periods back."""
    growth: dict[str, float | None] = {}
    for i, date in enumerate(dates):
        if i < lookback:
            growth[date] = None
            continue
        prev_date = dates[i - lookback]
        curr = values.get(date)
        prev = values.get(prev_date)
        if curr is not None and prev is not None and prev != 0:
            growth[date] = round(((curr - prev) / abs(prev)) * 100, 1)
        else:
            growth[date] = None
    return growth


def _compute_yoy(values: dict[str, float | None], dates: list[str]) -> dict[str, float | None]:
    """Compute period-over-period growth (consecutive dates)."""
    return _compute_growth(values, dates, lookback=1)


def _compute_margin(
    numerator_key: str,
    denominator_key: str,
    data: dict[str, dict[str, float | None]],
    dates: list[str],
) -> dict[str, float | None]:
    """Compute margin as percentage (numerator / denominator * 100)."""
    result: dict[str, float | None] = {}
    for d in dates:
        num = data.get(numerator_key, {}).get(d)
        den = data.get(denominator_key, {}).get(d)
        if num is not None and den is not None and den != 0:
            result[d] = round((num / den) * 100, 1)
        else:
            result[d] = None
    return result


def _build_line_item(
    metric_key: str,
    label: str,
    data: dict[str, dict[str, float | None]],
    dates: list[str],
    indent: int = 0,
    is_header: bool = False,
    format_type: str = "currency",
    computed_values: dict[str, float | None] | None = None,
) -> dict[str, Any] | None:
    """Build a line item dict, returning None if no data exists."""
    if computed_values is not None:
        values = {d: computed_values.get(d) for d in dates}
    elif metric_key in data:
        values = {d: data[metric_key].get(d) for d in dates}
    else:
        return None

    if all(v is None for v in values.values()):
        return None

    yoy = _compute_yoy(values, dates)

    return {
        "metric": metric_key,
        "label": label,
        "values": values,
        "yoy": yoy,
        "indent": indent,
        "is_header": is_header,
        "format_type": format_type,
    }


# ---- Line item definitions ----


def _build_income_statement_items(
    data: dict[str, dict[str, float | None]], dates: list[str],
) -> list[dict[str, Any]]:
    definitions: list[tuple[str, str, int, bool, str]] = [
        ("total_revenue", "Revenue", 0, True, "currency"),
        ("cost_of_revenue", "Cost of Revenue", 1, False, "currency"),
        ("gross_profit", "Gross Profit", 0, True, "currency"),
        ("_gross_margin", "Gross Margin", 1, False, "percent"),
        ("research_and_development", "Research & Development", 1, False, "currency"),
        ("selling_gen_admin", "Selling, General & Admin", 1, False, "currency"),
        ("operating_expense", "Total Operating Expenses", 1, False, "currency"),
        ("operating_income", "Operating Income", 0, True, "currency"),
        ("_operating_margin", "Operating Margin", 1, False, "percent"),
        ("ebitda", "EBITDA", 0, True, "currency"),
        ("_ebitda_margin", "EBITDA Margin", 1, False, "percent"),
        ("interest_expense", "Interest Expense", 1, False, "currency"),
        ("interest_income", "Interest Income", 1, False, "currency"),
        ("other_income_expense", "Other Income/Expense", 1, False, "currency"),
        ("pretax_income", "Pre-tax Income", 0, True, "currency"),
        ("tax_provision", "Tax Provision", 1, False, "currency"),
        ("_effective_tax_rate", "Effective Tax Rate", 1, False, "percent"),
        ("net_income", "Net Income", 0, True, "currency"),
        ("_net_margin", "Net Margin", 1, False, "percent"),
        ("diluted_eps", "Diluted EPS", 0, False, "per_share"),
        ("basic_eps", "Basic EPS", 1, False, "per_share"),
        ("diluted_average_shares", "Diluted Shares Outstanding", 0, False, "count"),
        ("reconciled_depreciation", "Depreciation & Amortization", 1, False, "currency"),
    ]

    computed: dict[str, dict[str, float | None]] = {
        "_gross_margin": _compute_margin("gross_profit", "total_revenue", data, dates),
        "_operating_margin": _compute_margin("operating_income", "total_revenue", data, dates),
        "_ebitda_margin": _compute_margin("ebitda", "total_revenue", data, dates),
        "_effective_tax_rate": _compute_margin("tax_provision", "pretax_income", data, dates),
        "_net_margin": _compute_margin("net_income", "total_revenue", data, dates),
    }

    items: list[dict[str, Any]] = []
    for metric, label, indent, is_header, fmt in definitions:
        cv = computed.get(metric)
        item = _build_line_item(metric, label, data, dates, indent, is_header, fmt, cv)
        if item is not None:
            items.append(item)
    return items


def _build_balance_sheet_items(
    data: dict[str, dict[str, float | None]], dates: list[str],
) -> list[dict[str, Any]]:
    definitions: list[tuple[str, str, int, bool, str]] = [
        ("current_assets", "Current Assets", 0, True, "currency"),
        ("cash_and_cash_equivalents", "Cash & Cash Equivalents", 1, False, "currency"),
        ("other_short_term_investments", "Short-term Investments", 1, False, "currency"),
        ("accounts_receivable", "Accounts Receivable", 1, False, "currency"),
        ("inventory", "Inventory", 1, False, "currency"),
        ("other_current_assets", "Other Current Assets", 1, False, "currency"),
        ("total_non_current_assets", "Non-Current Assets", 0, True, "currency"),
        ("net_ppe", "Net PP&E", 1, False, "currency"),
        ("investments_and_advances", "Investments & Advances", 1, False, "currency"),
        ("other_non_current_assets", "Other Non-Current Assets", 1, False, "currency"),
        ("total_assets", "Total Assets", 0, True, "currency"),
        ("current_liabilities", "Current Liabilities", 0, True, "currency"),
        ("accounts_payable", "Accounts Payable", 1, False, "currency"),
        ("current_debt", "Current Debt", 1, False, "currency"),
        ("current_deferred_revenue", "Deferred Revenue", 1, False, "currency"),
        ("other_current_liabilities", "Other Current Liabilities", 1, False, "currency"),
        ("total_non_current_liabilities_net_minority_interest", "Non-Current Liabilities", 0, True, "currency"),
        ("long_term_debt", "Long-term Debt", 1, False, "currency"),
        ("other_non_current_liabilities", "Other Non-Current Liabilities", 1, False, "currency"),
        ("total_liabilities_net_minority_interest", "Total Liabilities", 0, True, "currency"),
        ("stockholders_equity", "Stockholders' Equity", 0, True, "currency"),
        ("common_stock", "Common Stock", 1, False, "currency"),
        ("retained_earnings", "Retained Earnings", 1, False, "currency"),
        ("gains_losses_not_affecting_retained_earnings", "AOCI", 1, False, "currency"),
        ("total_debt", "Total Debt", 0, True, "currency"),
        ("net_debt", "Net Debt", 0, False, "currency"),
        ("working_capital", "Working Capital", 0, False, "currency"),
        ("tangible_book_value", "Tangible Book Value", 0, False, "currency"),
    ]

    items: list[dict[str, Any]] = []
    for metric, label, indent, is_header, fmt in definitions:
        item = _build_line_item(metric, label, data, dates, indent, is_header, fmt)
        if item is not None:
            items.append(item)
    return items


def _build_cash_flow_items(
    data: dict[str, dict[str, float | None]],
    dates: list[str],
    income_data: dict[str, dict[str, float | None]] | None = None,
) -> list[dict[str, Any]]:
    definitions: list[tuple[str, str, int, bool, str]] = [
        ("operating_cash_flow", "Cash from Operations", 0, True, "currency"),
        ("net_income_from_continuing_operations", "Net Income", 1, False, "currency"),
        ("depreciation_and_amortization", "Depreciation & Amortization", 1, False, "currency"),
        ("stock_based_compensation", "Stock-Based Compensation", 1, False, "currency"),
        ("deferred_income_tax", "Deferred Income Tax", 1, False, "currency"),
        ("change_in_working_capital", "Changes in Working Capital", 1, False, "currency"),
        ("changes_in_account_receivables", "Accounts Receivable", 2, False, "currency"),
        ("change_in_inventory", "Inventory", 2, False, "currency"),
        ("change_in_account_payable", "Accounts Payable", 2, False, "currency"),
        ("investing_cash_flow", "Cash from Investing", 0, True, "currency"),
        ("capital_expenditure", "Capital Expenditure", 1, False, "currency"),
        ("net_business_purchase_and_sale", "Acquisitions", 1, False, "currency"),
        ("net_investment_purchase_and_sale", "Purchases/Sales of Investments", 1, False, "currency"),
        ("net_other_investing_changes", "Other Investing", 1, False, "currency"),
        ("financing_cash_flow", "Cash from Financing", 0, True, "currency"),
        ("repurchase_of_capital_stock", "Share Buybacks", 1, False, "currency"),
        ("common_stock_dividend_paid", "Dividends Paid", 1, False, "currency"),
        ("net_issuance_payments_of_debt", "Net Debt Issuance", 1, False, "currency"),
        ("net_other_financing_charges", "Other Financing", 1, False, "currency"),
        ("free_cash_flow", "Free Cash Flow", 0, True, "currency"),
        ("_fcf_margin", "FCF Margin", 1, False, "percent"),
        ("changes_in_cash", "Net Change in Cash", 0, False, "currency"),
        ("end_cash_position", "Ending Cash Position", 0, False, "currency"),
    ]

    computed: dict[str, dict[str, float | None]] = {}
    if income_data:
        merged = {**data, **income_data}
        computed["_fcf_margin"] = _compute_margin("free_cash_flow", "total_revenue", merged, dates)
    else:
        computed["_fcf_margin"] = {d: None for d in dates}

    items: list[dict[str, Any]] = []
    for metric, label, indent, is_header, fmt in definitions:
        cv = computed.get(metric)
        item = _build_line_item(metric, label, data, dates, indent, is_header, fmt, cv)
        if item is not None:
            items.append(item)
    return items


# ---- Summary metric definitions ----

_SUMMARY_METRICS: dict[str, list[tuple[str, str, str]]] = {
    "income_statement": [
        ("total_revenue", "Revenue", "currency"),
        ("gross_profit", "Gross Profit", "currency"),
        ("operating_income", "Operating Income", "currency"),
        ("ebitda", "EBITDA", "currency"),
        ("net_income", "Net Income", "currency"),
        ("diluted_eps", "Diluted EPS", "per_share"),
    ],
    "balance_sheet": [
        ("total_assets", "Total Assets", "currency"),
        ("total_debt", "Total Debt", "currency"),
        ("stockholders_equity", "Stockholders' Equity", "currency"),
        ("cash_and_cash_equivalents", "Cash & Equivalents", "currency"),
    ],
    "cash_flow": [
        ("operating_cash_flow", "Operating Cash Flow", "currency"),
        ("free_cash_flow", "Free Cash Flow", "currency"),
        ("capital_expenditure", "Capital Expenditure", "currency"),
        ("repurchase_of_capital_stock", "Share Buybacks", "currency"),
        ("common_stock_dividend_paid", "Dividends Paid", "currency"),
    ],
}


# ---- Endpoints ----


@router.get("/{ticker}/income-statement")
async def get_income_statement(
    ticker: str,
    period: str = Query(default="annual", pattern="^(annual|quarterly)$"),
) -> dict[str, Any]:
    ticker_upper = ticker.upper()
    data = await _read_financial_db(ticker_upper, period)
    dates = _get_sorted_dates(data)
    line_items = _build_income_statement_items(data, dates)
    return {
        "ticker": ticker_upper,
        "statement_type": "income_statement",
        "period": period,
        "dates": dates,
        "line_items": line_items,
        "fy_end_month": await _get_fy_end_month(ticker_upper),
    }


@router.get("/{ticker}/balance-sheet")
async def get_balance_sheet(
    ticker: str,
    period: str = Query(default="annual", pattern="^(annual|quarterly)$"),
) -> dict[str, Any]:
    ticker_upper = ticker.upper()
    data = await _read_financial_db(ticker_upper, period)
    dates = _get_sorted_dates(data)
    line_items = _build_balance_sheet_items(data, dates)
    return {
        "ticker": ticker_upper,
        "statement_type": "balance_sheet",
        "period": period,
        "dates": dates,
        "line_items": line_items,
        "fy_end_month": await _get_fy_end_month(ticker_upper),
    }


@router.get("/{ticker}/cash-flow")
async def get_cash_flow(
    ticker: str,
    period: str = Query(default="annual", pattern="^(annual|quarterly)$"),
) -> dict[str, Any]:
    ticker_upper = ticker.upper()
    # Single read returns all metrics — includes both cash flow and income data
    data = await _read_financial_db(ticker_upper, period)
    dates = _get_sorted_dates(data)
    # Pass data as both cash flow and income data since it contains all metrics
    line_items = _build_cash_flow_items(data, dates, income_data=data)
    return {
        "ticker": ticker_upper,
        "statement_type": "cash_flow",
        "period": period,
        "dates": dates,
        "line_items": line_items,
        "fy_end_month": await _get_fy_end_month(ticker_upper),
    }


@router.get("/{ticker}/summary")
async def get_summary(
    ticker: str,
    period: str = Query(default="annual", pattern="^(annual|quarterly)$"),
) -> dict[str, Any]:
    ticker_upper = ticker.upper()

    # Single DB read gets all metrics for this ticker+period
    all_metrics = await _read_financial_db(ticker_upper, period)

    # Partition metrics into sections based on _SUMMARY_METRICS keys
    all_data: dict[str, dict[str, dict[str, float | None]]] = {}
    for section in ("income_statement", "balance_sheet", "cash_flow"):
        section_keys = {m[0] for m in _SUMMARY_METRICS[section]}
        all_data[section] = {k: v for k, v in all_metrics.items() if k in section_keys}

    all_dates_set: set[str] = set()
    for section_data in all_data.values():
        for metric_dates in section_data.values():
            all_dates_set.update(metric_dates.keys())
    dates = sorted(all_dates_set)

    metrics: list[dict[str, Any]] = []
    for section, metric_defs in _SUMMARY_METRICS.items():
        data = all_data[section]
        for metric_key, label, fmt in metric_defs:
            if metric_key not in data:
                continue
            values = {d: data[metric_key].get(d) for d in dates}
            if all(v is None for v in values.values()):
                continue
            if period == "quarterly":
                yoy = _compute_growth(values, dates, lookback=4)
                qoq = _compute_growth(values, dates, lookback=1)
            else:
                yoy = _compute_growth(values, dates, lookback=1)
                qoq = {d: None for d in dates}
            metrics.append({
                "metric": metric_key,
                "label": label,
                "section": section,
                "values": values,
                "yoy": yoy,
                "qoq": qoq,
                "format_type": fmt,
            })

    return {
        "ticker": ticker_upper,
        "period": period,
        "dates": dates,
        "metrics": metrics,
        "fy_end_month": await _get_fy_end_month(ticker_upper),
    }
