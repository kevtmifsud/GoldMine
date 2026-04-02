"""Tests for deterministic MCP formatters."""
from __future__ import annotations

from app.mcp.formatters import (
    fmt_currency,
    fmt_pct,
    fmt_date,
    fmt_shares,
    fmt_weight,
    fmt_str,
    fmt_analyst,
    md_table,
    format_get_estimates,
    format_get_daily_pnl,
    format_get_financial_metrics,
    format_get_portfolio_risk,
    format_get_guidance,
    format_search_universe,
    format_tool_result,
)


class TestValueFormatters:
    def test_fmt_currency_billions(self):
        assert fmt_currency(1_500_000_000) == "$1.5B"
        assert fmt_currency(12_096_358_049) == "$12.1B"

    def test_fmt_currency_millions(self):
        assert fmt_currency(607_621_000) == "$608M"

    def test_fmt_currency_thousands(self):
        assert fmt_currency(25_000) == "$25K"

    def test_fmt_currency_eps(self):
        assert fmt_currency(4.06) == "$4.06"
        assert fmt_currency(1.98) == "$1.98"

    def test_fmt_currency_none(self):
        assert fmt_currency(None) == "—"

    def test_fmt_pct_positive(self):
        assert fmt_pct(5.2) == "+5.2%"

    def test_fmt_pct_negative(self):
        assert fmt_pct(-3.1) == "-3.1%"

    def test_fmt_pct_none(self):
        assert fmt_pct(None) == "—"

    def test_fmt_pct_no_sign(self):
        assert fmt_pct(5.2, sign=False) == "5.2%"

    def test_fmt_date_iso(self):
        assert fmt_date("2026-04-01T12:00:00") == "2026-04-01"

    def test_fmt_date_none(self):
        assert fmt_date(None) == "—"

    def test_fmt_shares_millions(self):
        assert fmt_shares(1_500_000) == "1.5M"

    def test_fmt_shares_thousands(self):
        assert fmt_shares(2_500) == "2K"

    def test_fmt_weight(self):
        assert fmt_weight(0.05) == "5.00%"

    def test_fmt_str_none(self):
        assert fmt_str(None) == "—"
        assert fmt_str("") == "—"
        assert fmt_str("hello") == "hello"

    def test_fmt_analyst(self):
        assert fmt_analyst("Goldman Sachs", "Alex Rivera") == "Goldman Sachs / Alex Rivera"
        assert fmt_analyst(None, None) == "—"
        assert fmt_analyst("Tiger Global", None) == "Tiger Global"


class TestMdTable:
    def test_basic_table(self):
        result = md_table(["A", "B"], [["1", "2"], ["3", "4"]])
        assert "| A | B |" in result
        assert "| 1 | 2 |" in result

    def test_empty_rows(self):
        result = md_table(["A"], [])
        assert "No data" in result


class TestFormatEstimates:
    def test_single_ticker(self):
        rows = [
            {
                "ticker": "CMG", "metric": "total_revenue", "period": "2026A",
                "source": "consensus", "firm": None, "analyst_name": None,
                "value": 11826438993.0, "yoy_vs_actual": -0.8,
                "estimate_date": "2026-03-15", "as_of_date": "2026-04-01", "staleness_days": 1,
            },
            {
                "ticker": "CMG", "metric": "total_revenue", "period": "2026A",
                "source": "internal", "firm": None, "analyst_name": None,
                "value": 12191384895.0, "yoy_vs_actual": 2.2,
                "estimate_date": "2026-03-15", "as_of_date": "2026-04-01", "staleness_days": 1,
            },
        ]
        result = format_get_estimates(rows, {"tickers": ["CMG"]})
        assert "$11.8B" in result
        assert "$12.2B" in result
        assert "-0.8%" in result
        assert "+2.2%" in result
        assert "Consensus" in result
        assert "Internal" in result
        assert "2026-03-15" in result

    def test_eps_formatting(self):
        rows = [{
            "ticker": "AAPL", "metric": "diluted_eps", "period": "2026Q1",
            "source": "consensus", "firm": None, "analyst_name": None,
            "value": 1.98, "yoy_vs_actual": 5.3,
            "estimate_date": "2026-03-15", "as_of_date": "2026-04-01", "staleness_days": 1,
        }]
        result = format_get_estimates(rows, {})
        assert "$1.98" in result
        assert "$1.98B" not in result  # must not be treated as billions

    def test_staleness_warning(self):
        rows = [{
            "ticker": "AAPL", "metric": "total_revenue", "period": "2026A",
            "source": "consensus", "value": 400_000_000_000,
            "yoy_vs_actual": None, "as_of_date": "2025-12-01", "staleness_days": 120,
        }]
        result = format_get_estimates(rows, {})
        assert "120 days old" in result

    def test_multi_ticker(self):
        rows = [
            {"ticker": "CMG", "metric": "total_revenue", "period": "2026A",
             "source": "consensus", "value": 11e9, "yoy_vs_actual": None,
             "estimate_date": "2026-03-15", "as_of_date": "2026-04-01", "staleness_days": 1},
            {"ticker": "DPZ", "metric": "total_revenue", "period": "2026A",
             "source": "consensus", "value": 5e9, "yoy_vs_actual": None,
             "estimate_date": "2026-03-15", "as_of_date": "2026-04-01", "staleness_days": 1},
        ]
        result = format_get_estimates(rows, {"tickers": ["CMG", "DPZ"]})
        assert "Ticker" in result  # multi-ticker adds Ticker column
        assert "CMG" in result
        assert "DPZ" in result


class TestFormatDailyPnl:
    def test_basic(self):
        rows = [{
            "ticker": "AAPL", "portfolio": "Flagship", "side": "long",
            "date": "2026-04-01", "shares_held": 1000, "market_value": 170000,
            "unrealized_pnl": 25000, "ytd_pnl": 12000, "daily_return": 0.5,
        }]
        result = format_get_daily_pnl(rows, {})
        assert "Flagship" in result
        assert "AAPL" in result
        assert "LONG" in result


class TestFormatFinancialMetrics:
    def test_pivot(self):
        rows = [
            {"ticker": "AAPL", "metric_name": "total_revenue",
             "period_end": "2025-09-30", "period_type": "quarterly", "value": 94_930_000_000},
            {"ticker": "AAPL", "metric_name": "total_revenue",
             "period_end": "2025-12-31", "period_type": "quarterly", "value": 124_300_000_000},
        ]
        result = format_get_financial_metrics(rows, {})
        assert "Total Revenue" in result
        assert "$94.9B" in result
        assert "$124.3B" in result
        assert "AAPL" in result


class TestFormatToolResult:
    def test_known_tool(self):
        rows = [{"ticker": "AAPL", "metric": "diluted_eps", "period": "2026Q1",
                 "source": "consensus", "value": 1.98, "yoy_vs_actual": None,
                 "estimate_date": "2026-03-15", "as_of_date": "2026-04-01", "staleness_days": 1}]
        result = format_tool_result("get_estimates", rows, {})
        assert result is not None
        assert "$1.98" in result

    def test_unknown_tool_returns_none(self):
        assert format_tool_result("get_alt_data", [{"x": 1}], {}) is None

    def test_empty_rows(self):
        result = format_tool_result("get_estimates", [], {})
        assert result is not None
        assert "No estimates" in result
