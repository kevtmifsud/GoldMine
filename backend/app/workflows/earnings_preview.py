"""Earnings Preview Workflow.

Full pre-earnings briefing for a single ticker covering:
  1. Estimates table (all four sources)
  2. Most recent quarter actuals
  3. Stock price behavior (last 90 days)
  4. Portfolio position
  5. Alt data signals
  6. KPI determination
  7. Prior preview reference

See instructions/domain/workflows.md for the full spec.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import date, timedelta
from typing import Any

import structlog

from app.mode2.db import get_conn
from app.mode2.models import ClassifiedQuery
from app.mode2.steps import StepCollector
from app.workflows.base import WorkflowBase

logger = structlog.get_logger(__name__)

# Key metrics always included in estimates table per spec
_DEFAULT_METRICS = ["diluted_eps", "total_revenue"]

# Actuals metrics per spec (Section 2)
_ACTUALS_METRICS = [
    "total_revenue", "gross_profit", "operating_income",
    "ebitda", "net_income", "diluted_eps",
]


class EarningsPreviewWorkflow(WorkflowBase):
    workflow_name = "earnings_preview"

    async def execute(
        self,
        inputs: dict[str, Any],
        triggered_by: str,
        user_id: str,
        steps: StepCollector,
    ) -> dict[str, Any]:
        ticker = inputs["ticker"].upper()
        reporting_period = inputs["reporting_period"]
        forward_period = inputs["forward_period"]

        logger.info("earnings_preview_start", ticker=ticker,
                     reporting_period=reporting_period,
                     forward_period=forward_period)

        t0 = time.monotonic()
        citations: list[dict[str, str]] = []

        # ------------------------------------------------------------------
        # Parallel data pulls (Sections 1-5 + 6 + 7)
        # ------------------------------------------------------------------
        (
            estimates_raw,
            actuals_raw,
            price_history,
            spx_history,
            pnl_data,
            concentration_data,
            alt_data_raw,
            prior_preview,
            kpi_from_notes,
        ) = await asyncio.gather(
            self._fetch_estimates(ticker, reporting_period, forward_period, steps),
            self._fetch_actuals(ticker, steps),
            self._fetch_stock_history(ticker, steps),
            self._fetch_stock_history("SPY", steps),
            self._fetch_daily_pnl(ticker, steps),
            self._fetch_concentration(ticker, steps),
            self._fetch_alt_data(ticker, steps),
            self._fetch_prior_preview(ticker),
            self._infer_kpis_from_notes(ticker),
        )

        steps.add(
            label="All data sections retrieved",
            detail=f"Parallel fetch for {ticker}",
            source="supabase",
            result_summary="assembling output",
        )

        # ------------------------------------------------------------------
        # Section 6 — KPI determination
        # ------------------------------------------------------------------
        key_kpis: list[str] = []
        kpis_need_user_input = False

        # Priority: user-provided > prior preview > inferred from notes
        if inputs.get("key_kpis"):
            key_kpis = inputs["key_kpis"]
        elif prior_preview and prior_preview.get("key_kpis"):
            key_kpis = prior_preview["key_kpis"]
        elif kpi_from_notes:
            key_kpis = kpi_from_notes
        else:
            kpis_need_user_input = True

        # ------------------------------------------------------------------
        # Section 1 — Estimates table
        # ------------------------------------------------------------------
        estimates_table = self._build_estimates_table(
            estimates_raw, actuals_raw, reporting_period, forward_period,
            key_kpis, citations, ticker,
        )

        # ------------------------------------------------------------------
        # Section 2 — Most recent quarter actuals
        # ------------------------------------------------------------------
        actuals_section = self._build_actuals_section(
            actuals_raw, citations, ticker,
        )

        # ------------------------------------------------------------------
        # Section 3 — Stock price behavior (last 90 days)
        # ------------------------------------------------------------------
        price_section = self._build_price_section(
            price_history, spx_history, ticker,
        )

        # ------------------------------------------------------------------
        # Section 4 — Portfolio position
        # ------------------------------------------------------------------
        portfolio_section = self._build_portfolio_section(
            pnl_data, concentration_data, ticker,
        )

        # ------------------------------------------------------------------
        # Section 5 — Alt data signals
        # ------------------------------------------------------------------
        alt_data_section = self._build_alt_data_section(
            alt_data_raw, citations, ticker,
        )

        # ------------------------------------------------------------------
        # Section 7 — Prior preview reference
        # ------------------------------------------------------------------
        prior_preview_reference = None
        if prior_preview:
            prior_preview_reference = {
                "prior_reporting_period": prior_preview.get("reporting_period"),
                "prior_key_kpis": prior_preview.get("key_kpis", []),
                "prior_generated_at": str(prior_preview.get("generated_at", "")),
            }

        # ------------------------------------------------------------------
        # Write output row
        # ------------------------------------------------------------------
        output_id = str(uuid.uuid4())

        async with get_conn() as conn:
            # Get workflow_run_id from the most recent running run for this workflow
            run_row = await conn.fetchrow(
                """SELECT wr.id FROM workflow_runs wr
                   JOIN workflow_registry wreg ON wr.workflow_id = wreg.id
                   WHERE wreg.workflow_name = 'earnings_preview'
                     AND wr.ticker = $1
                     AND wr.status = 'running'
                   ORDER BY wr.started_at DESC LIMIT 1""",
                ticker,
            )
            workflow_run_id = run_row["id"] if run_row else None

            await conn.execute(
                """INSERT INTO workflow_outputs_earnings_preview
                   (id, workflow_run_id, ticker, reporting_period, forward_period,
                    key_kpis, estimates_table, actuals_section, price_section,
                    portfolio_section, alt_data_section, prior_preview_reference,
                    generated_at, generated_by, citations)
                   VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb,
                           $9::jsonb, $10::jsonb, $11::jsonb, $12::jsonb,
                           NOW(), $13, $14::jsonb)""",
                uuid.UUID(output_id),
                workflow_run_id,
                ticker,
                reporting_period,
                forward_period,
                key_kpis,
                json.dumps(estimates_table),
                json.dumps(actuals_section),
                json.dumps(price_section),
                json.dumps(portfolio_section),
                json.dumps(alt_data_section),
                json.dumps(prior_preview_reference) if prior_preview_reference else None,
                triggered_by,
                json.dumps(citations),
            )

        elapsed = round(time.monotonic() - t0, 2)
        logger.info("earnings_preview_complete", ticker=ticker,
                     output_id=output_id, elapsed_seconds=elapsed,
                     kpis_need_user_input=kpis_need_user_input)

        return {
            "output_id": output_id,
            "ticker": ticker,
            "reporting_period": reporting_period,
            "forward_period": forward_period,
            "key_kpis": key_kpis,
            "kpis_need_user_input": kpis_need_user_input,
            "estimates_table": estimates_table,
            "actuals_section": actuals_section,
            "price_section": price_section,
            "portfolio_section": portfolio_section,
            "alt_data_section": alt_data_section,
            "prior_preview_reference": prior_preview_reference,
            "citations": citations,
            "cost_usd": 0.0,
        }

    # ==================================================================
    # Data fetchers (called in parallel via asyncio.gather)
    # ==================================================================

    async def _fetch_estimates(
        self, ticker: str, reporting_period: str,
        forward_period: str, steps: StepCollector,
    ) -> list[dict]:
        """Fetch all four estimate sources for both periods."""
        t0 = time.time()
        periods = [reporting_period, forward_period]
        queries = {
            "internal_estimates": """
                SELECT DISTINCT ON (ticker, metric, period)
                    ticker, metric, period, value, unit, model_version,
                    created_at, 'internal_estimates' AS _table
                FROM internal_estimates
                WHERE ticker = $1 AND period = ANY($2)
                ORDER BY ticker, metric, period, created_at DESC""",
            "buyside_estimates": """
                SELECT DISTINCT ON (ticker, metric, period)
                    ticker, firm, metric, period, value, unit, estimate_date,
                    'buyside_estimates' AS _table
                FROM buyside_estimates
                WHERE ticker = $1 AND period = ANY($2)
                ORDER BY ticker, metric, period, estimate_date DESC""",
            "consensus_estimates": """
                SELECT DISTINCT ON (ticker, metric, period)
                    ticker, metric, period, value, unit, estimate_date,
                    'consensus_estimates' AS _table
                FROM consensus_estimates
                WHERE ticker = $1 AND period = ANY($2)
                ORDER BY ticker, metric, period, estimate_date DESC""",
            "sellside_estimates": """
                SELECT DISTINCT ON (ticker, metric, period)
                    ticker, firm, metric, period, value, unit, estimate_date,
                    'sellside_estimates' AS _table
                FROM sellside_estimates
                WHERE ticker = $1 AND period = ANY($2)
                ORDER BY ticker, metric, period, estimate_date DESC""",
        }

        results: list[dict] = []

        async def _fetch_one(sql: str) -> list:
            async with get_conn() as conn:
                return await conn.fetch(sql, ticker, periods)

        coros = [_fetch_one(sql) for sql in queries.values()]
        fetched = await asyncio.gather(*coros, return_exceptions=True)

        for table_name, rows_or_err in zip(queries.keys(), fetched):
            if isinstance(rows_or_err, Exception):
                logger.warning("estimate_fetch_failed", table=table_name,
                                error=str(rows_or_err))
                continue
            for r in rows_or_err:
                results.append(dict(r))

        duration_ms = int((time.time() - t0) * 1000)
        steps.add(
            label=f"Fetching estimates for {ticker}",
            detail=f"4 tables, {len(results)} rows",
            source="supabase",
            duration_ms=duration_ms,
            result_summary=f"{len(results)} estimate rows",
        )
        return results

    async def _fetch_actuals(self, ticker: str, steps: StepCollector) -> list[dict]:
        """Fetch 8 quarters of financial metrics for YoY comparisons."""
        t0 = time.time()
        async with get_conn() as conn:
            rows = await conn.fetch(
                """SELECT metric_name, period_end, period_type, value
                   FROM financial_metrics
                   WHERE ticker = $1
                     AND metric_name = ANY($2)
                     AND period_type = 'quarterly'
                   ORDER BY period_end DESC
                   LIMIT 80""",
                ticker, _ACTUALS_METRICS,
            )
        results = [dict(r) for r in rows]
        duration_ms = int((time.time() - t0) * 1000)
        steps.add(
            label=f"Fetching actuals for {ticker}",
            detail=f"financial_metrics ({len(results)} rows)",
            source="supabase",
            duration_ms=duration_ms,
            result_summary=f"{len(results)} rows",
        )
        return results

    async def _fetch_stock_history(
        self, ticker: str, steps: StepCollector,
    ) -> list[dict]:
        """Fetch last 90 days of price data."""
        t0 = time.time()
        async with get_conn() as conn:
            rows = await conn.fetch(
                """SELECT
                     ticker,
                     date::date AS date,
                     close::numeric AS close,
                     NULLIF(eps_estimate, '')::numeric AS eps_estimate,
                     NULLIF(eps_actual, '')::numeric AS eps_actual
                   FROM stock_history
                   WHERE ticker = $1
                     AND date::date >= CURRENT_DATE - INTERVAL '90 days'
                   ORDER BY date::date""",
                ticker,
            )
        results = [dict(r) for r in rows]
        duration_ms = int((time.time() - t0) * 1000)
        steps.add(
            label=f"Fetching price history for {ticker}",
            detail=f"stock_history ({len(results)} rows)",
            source="supabase",
            duration_ms=duration_ms,
            result_summary=f"{len(results)} rows",
        )
        return results

    async def _fetch_daily_pnl(
        self, ticker: str, steps: StepCollector,
    ) -> list[dict]:
        """Fetch most recent daily_pnl for ticker across portfolios."""
        t0 = time.time()
        async with get_conn() as conn:
            rows = await conn.fetch(
                """SELECT date, ticker, portfolio, side, sector,
                          unrealized_pnl, realized_pnl, daily_return,
                          cumulative_return, contribution_to_portfolio,
                          shares_held, market_value, cost_basis,
                          ytd_pnl
                   FROM daily_pnl
                   WHERE ticker = $1
                     AND date = (SELECT MAX(date) FROM daily_pnl WHERE ticker = $1)""",
                ticker,
            )
        results = [dict(r) for r in rows]
        duration_ms = int((time.time() - t0) * 1000)
        steps.add(
            label=f"Fetching P&L for {ticker}",
            detail=f"daily_pnl ({len(results)} rows)",
            source="supabase",
            duration_ms=duration_ms,
            result_summary=f"{len(results)} rows",
        )
        return results

    async def _fetch_concentration(
        self, ticker: str, steps: StepCollector,
    ) -> list[dict]:
        """Fetch most recent portfolio_concentration for ticker."""
        t0 = time.time()
        async with get_conn() as conn:
            rows = await conn.fetch(
                """SELECT date, ticker, portfolio, side, position_weight,
                          sector_weight, is_market_neutral_compliant
                   FROM portfolio_concentration
                   WHERE ticker = $1
                     AND date = (SELECT MAX(date) FROM portfolio_concentration
                                 WHERE ticker = $1)""",
                ticker,
            )
        results = [dict(r) for r in rows]
        duration_ms = int((time.time() - t0) * 1000)
        steps.add(
            label=f"Fetching concentration for {ticker}",
            detail=f"portfolio_concentration ({len(results)} rows)",
            source="supabase",
            duration_ms=duration_ms,
            result_summary=f"{len(results)} rows",
        )
        return results

    async def _fetch_alt_data(
        self, ticker: str, steps: StepCollector,
    ) -> list[dict]:
        """Fetch all available alt data types for ticker."""
        t0 = time.time()
        async with get_conn() as conn:
            rows = await conn.fetch(
                """SELECT ticker, data_type, date, value, growth, unit,
                          source_vendor, date_frequency
                   FROM alt_data
                   WHERE ticker = $1
                   ORDER BY data_type, date DESC
                   LIMIT 100""",
                ticker,
            )
        results = [dict(r) for r in rows]
        duration_ms = int((time.time() - t0) * 1000)
        steps.add(
            label=f"Fetching alt data for {ticker}",
            detail=f"alt_data ({len(results)} rows)",
            source="supabase",
            duration_ms=duration_ms,
            result_summary=f"{len(results)} rows",
        )
        return results

    async def _fetch_prior_preview(self, ticker: str) -> dict | None:
        """Fetch most recent prior earnings preview for this ticker."""
        async with get_conn() as conn:
            row = await conn.fetchrow(
                """SELECT ticker, reporting_period, forward_period,
                          key_kpis, selected_alt_signals,
                          estimates_table, actuals_section,
                          generated_at
                   FROM workflow_outputs_earnings_preview
                   WHERE ticker = $1
                   ORDER BY generated_at DESC
                   LIMIT 1""",
                ticker,
            )
        return dict(row) if row else None

    async def _infer_kpis_from_notes(self, ticker: str) -> list[str]:
        """Infer KPIs from analyst_notes and sellside_notes chunks.

        Looks for the most frequently mentioned metric-like terms
        in chunks for this ticker.
        """
        async with get_conn() as conn:
            rows = await conn.fetch(
                """SELECT chunk_text
                   FROM chunks
                   WHERE ticker = $1
                     AND document_type IN ('analyst_note', 'sellside_note')
                   ORDER BY created_at DESC
                   LIMIT 20""",
                ticker,
            )

        if not rows:
            return []

        # Simple frequency-based extraction of common financial metric terms
        metric_keywords = {
            "revenue": "revenue",
            "eps": "eps",
            "ebitda": "ebitda",
            "margins": "gross_margin",
            "gross margin": "gross_margin",
            "operating margin": "operating_margin",
            "free cash flow": "free_cash_flow",
            "fcf": "free_cash_flow",
            "arpu": "arpu",
            "subscribers": "subscribers",
            "dau": "dau",
            "mau": "mau",
            "gmv": "gmv",
            "arr": "arr",
            "net adds": "net_adds",
            "same store sales": "same_store_sales",
            "comp sales": "same_store_sales",
            "backlog": "backlog",
            "bookings": "bookings",
            "asp": "asp",
            "units": "units",
        }

        counts: dict[str, int] = {}
        for row in rows:
            text = (row["chunk_text"] or "").lower()
            for keyword, metric in metric_keywords.items():
                if keyword in text:
                    counts[metric] = counts.get(metric, 0) + 1

        # Return top 5 by frequency, excluding revenue/eps (always included)
        sorted_metrics = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        kpis = [m for m, _ in sorted_metrics if m not in ("revenue", "eps")][:5]
        return kpis

    # ==================================================================
    # Section builders
    # ==================================================================

    def _build_estimates_table(
        self,
        estimates_raw: list[dict],
        actuals_raw: list[dict],
        reporting_period: str,
        forward_period: str,
        key_kpis: list[str],
        citations: list[dict[str, str]],
        ticker: str,
    ) -> dict[str, Any]:
        """Build the estimates comparison table (Section 1).

        Enriches each estimate with:
        - yoy_vs_actual: % growth vs prior year actual
        - prior_year_actual: the actual value used for YoY
        - vs_consensus: value minus consensus (in dollar/unit terms)
        """
        all_metrics = list(dict.fromkeys(key_kpis + _DEFAULT_METRICS))

        source_map = {
            "internal_estimates": "Internal",
            "buyside_estimates": "Buyside",
            "consensus_estimates": "Consensus",
            "sellside_estimates": "Sellside",
        }

        # Build actuals lookup by (metric, period_end) for YoY calculation
        from collections import defaultdict
        from datetime import date as date_type

        actuals_by_period: dict[str, dict[str, float]] = defaultdict(dict)
        for r in actuals_raw:
            p = str(r["period_end"])
            if r.get("value") is not None:
                actuals_by_period[p][r["metric_name"]] = float(r["value"])

        sorted_actual_periods = sorted(actuals_by_period.keys(), reverse=True)

        def find_prior_year_actual(metric: str) -> float | None:
            """Find most recent annual-equivalent actual for YoY comp."""
            if not sorted_actual_periods:
                return None
            # Use most recent quarter's actual for the metric
            for p in sorted_actual_periods:
                val = actuals_by_period[p].get(metric)
                if val is not None:
                    return val
            return None

        table: dict[str, Any] = {
            "reporting_period": reporting_period,
            "forward_period": forward_period,
            "metrics": {},
        }

        for metric in all_metrics:
            prior_actual = find_prior_year_actual(metric)

            metric_data: dict[str, Any] = {}
            for period in [reporting_period, forward_period]:
                period_data: dict[str, Any] = {}

                # First pass: collect all source values to find consensus
                source_values: dict[str, float | None] = {}
                for table_name, display_name in source_map.items():
                    match = next(
                        (r for r in estimates_raw
                         if r.get("_table") == table_name
                         and r.get("metric", "").lower() == metric.lower()
                         and r.get("period") == period),
                        None,
                    )
                    if match and match.get("value") is not None:
                        source_values[display_name] = float(match["value"])
                    else:
                        source_values[display_name] = None

                consensus_val = source_values.get("Consensus")

                # Second pass: build enriched entries
                for table_name, display_name in source_map.items():
                    match = next(
                        (r for r in estimates_raw
                         if r.get("_table") == table_name
                         and r.get("metric", "").lower() == metric.lower()
                         and r.get("period") == period),
                        None,
                    )
                    val = source_values[display_name]

                    entry: dict[str, Any] = {"value": val, "unit": match.get("unit") if match else None}

                    # YoY vs actual
                    if val is not None and prior_actual is not None and prior_actual != 0:
                        entry["yoy_vs_actual"] = round((val / prior_actual - 1) * 100, 2)
                        entry["prior_year_actual"] = prior_actual
                    else:
                        entry["yoy_vs_actual"] = None
                        entry["prior_year_actual"] = prior_actual

                    # vs Consensus (value difference, not percentage)
                    if display_name == "Consensus":
                        entry["vs_consensus"] = None
                    elif val is not None and consensus_val is not None:
                        entry["vs_consensus"] = round(val - consensus_val, 2)
                    else:
                        entry["vs_consensus"] = None

                    period_data[display_name] = entry

                    # Citation
                    if match:
                        cite_label = {
                            "internal_estimates": f"[{ticker} | Internal Estimate | {match.get('model_version', '')} | {match.get('created_at', '')}]",
                            "buyside_estimates": f"[{ticker} | Buyside Estimate | {match.get('firm', '')} | {match.get('estimate_date', '')}]",
                            "consensus_estimates": f"[{ticker} | Consensus | {period} | {match.get('estimate_date', '')}]",
                            "sellside_estimates": f"[{ticker} | Sellside Estimate | {match.get('firm', '')} | {match.get('estimate_date', '')}]",
                        }
                        citations.append({
                            "ticker": ticker,
                            "source": table_name,
                            "metric": metric,
                            "period": period,
                            "citation": cite_label.get(table_name, ""),
                        })

                metric_data[period] = period_data
            table["metrics"][metric] = metric_data

        return table

    def _build_actuals_section(
        self,
        actuals_raw: list[dict],
        citations: list[dict[str, str]],
        ticker: str,
    ) -> dict[str, Any]:
        """Build actuals section with all quarters and YoY growth."""
        if not actuals_raw:
            return {
                "note": "No recent quarterly actuals available.",
                "metrics": {},
                "quarters": {},
                "yoy_growth": {},
            }

        from collections import defaultdict
        from datetime import date as date_type

        # Group all rows by period_end
        by_period: dict[str, dict[str, Any]] = defaultdict(dict)
        for r in actuals_raw:
            period = str(r["period_end"])
            metric = r["metric_name"]
            by_period[period][metric] = {
                "value": float(r["value"]) if r.get("value") is not None else None,
                "period_end": period,
                "period_type": r["period_type"],
            }

        sorted_periods = sorted(by_period.keys(), reverse=True)
        most_recent_period = sorted_periods[0]

        # Find prior year period: within 45 days of exactly 1 year ago
        def find_prior_year(period: str) -> str | None:
            pd = date_type.fromisoformat(period)
            try:
                target = date_type(pd.year - 1, pd.month, pd.day)
            except ValueError:
                # Handle Feb 29 → Feb 28
                target = date_type(pd.year - 1, pd.month, pd.day - 1)
            for p in sorted_periods:
                candidate = date_type.fromisoformat(p)
                if abs((candidate - target).days) <= 45:
                    return p
            return None

        # Build YoY growth for each period that has a prior year comp
        yoy_growth: dict[str, dict[str, Any]] = {}
        for period in sorted_periods:
            prior = find_prior_year(period)
            if not prior:
                continue
            period_yoy: dict[str, Any] = {}
            for metric, current_data in by_period[period].items():
                prior_data = by_period[prior].get(metric)
                if not prior_data:
                    continue
                cur_val = current_data["value"]
                pri_val = prior_data["value"]
                growth = None
                if cur_val is not None and pri_val is not None and pri_val != 0:
                    growth = round((cur_val / pri_val - 1) * 100, 2)
                period_yoy[metric] = {
                    "current": cur_val,
                    "prior": pri_val,
                    "prior_period": prior,
                    "growth_pct": growth,
                }
            if period_yoy:
                yoy_growth[period] = period_yoy

        # Citations for most recent period
        for metric in by_period[most_recent_period]:
            citations.append({
                "ticker": ticker,
                "source": "financial_metrics",
                "metric": metric,
                "period": most_recent_period,
                "citation": f"[{ticker} | Financials | {most_recent_period}]",
            })

        return {
            "period_end": most_recent_period,
            "metrics": by_period[most_recent_period],
            "quarters": dict(by_period),
            "yoy_growth": yoy_growth,
        }

    def _build_price_section(
        self,
        price_history: list[dict],
        spx_history: list[dict],
        ticker: str,
    ) -> dict[str, Any]:
        """Build stock price behavior section (Section 3). Exempt from citation.

        Uses close price only (stock_history schema: date, ticker, close,
        eps_estimate, eps_actual). Includes EPS estimate vs actual comparison.
        """
        if not price_history:
            return {"note": f"No recent price data for {ticker}."}

        prices = sorted(price_history, key=lambda r: r["date"])
        first_close = float(prices[0]["close"])
        last_close = float(prices[-1]["close"])
        price_change_pct = ((last_close - first_close) / first_close * 100) if first_close else 0.0

        # SPX comparison
        vs_spx_return = None
        if spx_history:
            spx_sorted = sorted(spx_history, key=lambda r: r["date"])
            spx_first = float(spx_sorted[0]["close"])
            spx_last = float(spx_sorted[-1]["close"])
            spx_return = ((spx_last - spx_first) / spx_first * 100) if spx_first else 0.0
            vs_spx_return = round(price_change_pct - spx_return, 2)

        # EPS estimate vs actual (from most recent row that has both)
        eps_comparison = None
        for row in reversed(prices):
            est = row.get("eps_estimate")
            act = row.get("eps_actual")
            if est is not None and act is not None:
                eps_comparison = {
                    "date": str(row["date"]),
                    "eps_estimate": float(est),
                    "eps_actual": float(act),
                    "surprise_pct": round(
                        ((float(act) - float(est)) / abs(float(est))) * 100, 2
                    ) if float(est) != 0 else None,
                }
                break

        return {
            "period_start": str(prices[0]["date"]),
            "period_end": str(prices[-1]["date"]),
            "first_close": round(first_close, 2),
            "last_close": round(last_close, 2),
            "price_change_pct": round(price_change_pct, 2),
            "vs_spx_return": vs_spx_return,
            "eps_comparison": eps_comparison,
        }

    def _build_portfolio_section(
        self,
        pnl_data: list[dict],
        concentration_data: list[dict],
        ticker: str,
    ) -> dict[str, Any]:
        """Build portfolio position section (Section 4). Exempt from citation."""
        if not pnl_data:
            return {"note": f"{ticker} is not currently held in any portfolio."}

        positions: list[dict[str, Any]] = []
        for row in pnl_data:
            pos: dict[str, Any] = {
                "portfolio": row["portfolio"],
                "side": row["side"],
                "shares_held": float(row["shares_held"]) if row.get("shares_held") else 0,
                "market_value": float(row["market_value"]) if row.get("market_value") else 0,
                "unrealized_pnl": float(row["unrealized_pnl"]) if row.get("unrealized_pnl") else 0,
                "realized_pnl": float(row["realized_pnl"]) if row.get("realized_pnl") else 0,
                "cumulative_return": float(row["cumulative_return"]) if row.get("cumulative_return") else 0,
                "ytd_pnl": float(row["ytd_pnl"]) if row.get("ytd_pnl") else 0,
            }
            # Add concentration data if available
            conc = next(
                (c for c in concentration_data
                 if c["portfolio"] == row["portfolio"] and c["side"] == row["side"]),
                None,
            )
            if conc:
                pos["position_weight"] = float(conc["position_weight"]) if conc.get("position_weight") else 0
            positions.append(pos)

        return {"positions": positions}

    def _build_alt_data_section(
        self,
        alt_data_raw: list[dict],
        citations: list[dict[str, str]],
        ticker: str,
    ) -> dict[str, Any]:
        """Build alt data signals section (Section 5)."""
        if not alt_data_raw:
            return {"note": f"No alternative data available for {ticker}."}

        # Group by data_type
        by_type: dict[str, list[dict]] = {}
        for row in alt_data_raw:
            dt = row["data_type"]
            by_type.setdefault(dt, []).append(row)

        signals: dict[str, Any] = {}
        for data_type, rows in by_type.items():
            sorted_rows = sorted(rows, key=lambda r: r["date"], reverse=True)
            most_recent = sorted_rows[0]
            signals[data_type] = {
                "most_recent_date": str(most_recent["date"]),
                "value": float(most_recent["value"]) if most_recent.get("value") is not None else None,
                "growth": float(most_recent["growth"]) if most_recent.get("growth") is not None else None,
                "unit": most_recent.get("unit"),
                "source_vendor": most_recent.get("source_vendor"),
                "date_frequency": most_recent.get("date_frequency"),
                "data_points_available": len(sorted_rows),
            }
            citations.append({
                "ticker": ticker,
                "source": "alt_data",
                "metric": data_type,
                "period": str(most_recent["date"]),
                "citation": f"[{ticker} | Alt Data | {data_type} | {most_recent['date']}]",
            })

        return {"signals": signals}

    # ------------------------------------------------------------------
    # Registry entry
    # ------------------------------------------------------------------
    @classmethod
    def get_registry_entry(cls) -> dict[str, Any]:
        return {
            "workflow_name": "earnings_preview",
            "display_name": "Earnings Preview",
            "description": (
                "Full pre-earnings briefing covering estimates, actuals, price, "
                "portfolio position, and alt data signals"
            ),
            "required_inputs": {
                "ticker": "required",
                "reporting_period": "required",
                "forward_period": "required",
            },
            "output_table": "workflow_outputs_earnings_preview",
            "trigger_type": "both",
            "schedule_rule": (
                "7 days before earnings_calendar.report_date "
                "for all portfolio tickers"
            ),
        }
