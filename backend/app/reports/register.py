from functools import partial

from app.reports.catalog import ReportDefinition, register_report
from app.reports.daily_pnl_report import render_daily_pnl_report

register_report(ReportDefinition(
    report_id="daily-pnl-flagship",
    name="Daily PnL Report — Flagship",
    description="Daily performance report for the Flagship portfolio: top-line PnL (daily, YTD, L30D), sector attribution, top contributors/detractors, recent trade activity, and earnings watchlist.",
    category="Portfolio",
    data_sources=["portfolios", "portfolio_trades", "stock_history", "earnings_calendar"],
    render=partial(render_daily_pnl_report, portfolio_name="Flagship"),
))

register_report(ReportDefinition(
    report_id="daily-pnl-long-only",
    name="Daily PnL Report — Long Only",
    description="Daily performance report for the Long Only portfolio: top-line PnL (daily, YTD, L30D), sector attribution, top contributors/detractors, recent trade activity, and earnings watchlist.",
    category="Portfolio",
    data_sources=["portfolios", "portfolio_trades", "stock_history", "earnings_calendar"],
    render=partial(render_daily_pnl_report, portfolio_name="Long Only"),
))
