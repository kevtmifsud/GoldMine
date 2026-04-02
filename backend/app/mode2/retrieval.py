"""WF-08: Retrieval functions.

Contains all _query_* functions, vector search, Q&A library lookup,
screening cache, and screening prefilter. These are called by
tools.execute_tool() in the agentic pipeline.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime

import time

import anthropic
from openai import OpenAI
from dotenv import load_dotenv

from .cost import get_model_config, calculate_cost, emit_cost_event
from .db import get_conn
from .models import (
    ChunkResult,
    ClassifiedQuery,
    QALibraryEntry,
)
from .steps import StepCollector, format_sql

logger = logging.getLogger(__name__)

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))


async def _embed_query(
    text: str,
    session_id: str | None = None,
    message_id: str | None = None,
    user_id: str | None = None,
    steps: StepCollector | None = None,
) -> list[float]:
    """Embed a query string using the query_embedder model from config."""
    config = await get_model_config("query_embedder")
    model = config["model"]

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
    t0 = time.time()
    response = client.embeddings.create(model=model, input=[text], dimensions=1536)
    embed_duration_ms = int((time.time() - t0) * 1000)
    embedding = response.data[0].embedding
    tokens = response.usage.total_tokens

    cost = await calculate_cost(model, tokens)
    if steps:
        steps.add(
            label="Embedding your query",
            detail=f"OpenAI embeddings ({tokens} tokens)",
            source="openai",
            model=model,
            cost_usd=cost,
            duration_ms=embed_duration_ms,
            result_summary=f"{len(embedding)}-dim vector",
        )
    emit_cost_event(
        mode="mode_2",
        component="query_embedder",
        model=model,
        input_tokens=tokens,
        cost_usd=cost,
        session_id=session_id,
        message_id=message_id,
        user_id=user_id,
    )
    return embedding


async def _lookup_qa_library(
    query_embedding: list[float],
    steps: StepCollector | None = None,
) -> list[QALibraryEntry]:
    """Search Q&A library for validated entries similar to the query."""
    t0 = time.time()
    emb_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
    async with get_conn() as conn:
        rows = await conn.fetch(
            """SELECT id, question, answer, tickers_referenced, query_type,
                      fiscal_periods, validation_type, validation_weight,
                      1 - (question_embedding <=> $1::vector) AS similarity
               FROM qa_library
               WHERE validation_type IS NOT NULL
               AND 1 - (question_embedding <=> $1::vector) > 0.88
               ORDER BY (1 - (question_embedding <=> $1::vector)) * validation_weight DESC
               LIMIT 2""",
            emb_str,
        )
    qa_duration_ms = int((time.time() - t0) * 1000)
    results = [
        QALibraryEntry(
            id=str(r["id"]),
            question=r["question"],
            answer=r["answer"],
            tickers_referenced=r["tickers_referenced"] or [],
            query_type=r["query_type"],
            fiscal_periods=r["fiscal_periods"] or [],
            validation_type=r["validation_type"],
            validation_weight=float(r["validation_weight"]),
            similarity=float(r["similarity"]),
        )
        for r in rows
    ]
    if steps:
        steps.add(
            label="Checking Q&A library",
            detail="pgvector similarity on qa_library table",
            source="supabase",
            duration_ms=qa_duration_ms,
            result_summary=f"{len(results)} hits" if results else "no matches",
        )
    return results


async def _check_screening_cache(query: str, fiscal_periods: list[str]) -> dict | None:
    """Check screening cache for a cached result."""
    cache_key = hashlib.md5((query + "|".join(fiscal_periods)).encode()).hexdigest()
    async with get_conn() as conn:
        row = await conn.fetchrow(
            """SELECT result_content, cache_key FROM screening_cache
               WHERE query_hash = $1 AND expires_at > NOW()""",
            cache_key,
        )
        if row:
            await conn.execute(
                "UPDATE screening_cache SET hit_count = hit_count + 1 WHERE query_hash = $1",
                cache_key,
            )
            return json.loads(row["result_content"])
    return None


async def _write_screening_cache(query: str, fiscal_periods: list[str], result: dict) -> None:
    cache_key = hashlib.md5((query + "|".join(fiscal_periods)).encode()).hexdigest()
    async with get_conn() as conn:
        await conn.execute(
            """INSERT INTO screening_cache (query_hash, query_text, result_content, expires_at)
               VALUES ($1, $2, $3, NOW() + INTERVAL '24 hours')
               ON CONFLICT (query_hash) DO UPDATE
               SET result_content = $3, expires_at = NOW() + INTERVAL '24 hours', hit_count = 0""",
            cache_key, query, json.dumps(result),
        )


async def _vector_search(
    query_embedding: list[float],
    tickers: list[str],
    limit_per_ticker: int = 6,
    section_type: str | None = None,
    fiscal_periods: list[str] | None = None,
    doc_types: list[str] | None = None,
    steps: StepCollector | None = None,
) -> list[ChunkResult]:
    """Perform pgvector cosine similarity search."""
    t0 = time.time()
    emb_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

    conditions = ["is_active = TRUE"]
    params: list = [emb_str]
    idx = 2

    if tickers:
        placeholders = ", ".join(f"${i}" for i in range(idx, idx + len(tickers)))
        conditions.append(f"ticker IN ({placeholders})")
        params.extend(tickers)
        idx += len(tickers)

    if section_type:
        conditions.append(f"section_type = ${idx}")
        params.append(section_type)
        idx += 1

    if fiscal_periods:
        placeholders = ", ".join(f"${i}" for i in range(idx, idx + len(fiscal_periods)))
        conditions.append(f"fiscal_period IN ({placeholders})")
        params.extend(fiscal_periods)
        idx += len(fiscal_periods)

    if doc_types:
        placeholders = ", ".join(f"${i}" for i in range(idx, idx + len(doc_types)))
        conditions.append(f"document_type IN ({placeholders})")
        params.extend(doc_types)
        idx += len(doc_types)

    where = " AND ".join(conditions)

    # For multi-ticker, use LATERAL join to get top N per ticker
    if len(tickers) > 1:
        total_limit = limit_per_ticker * len(tickers)
        query = f"""
            SELECT chunk_id, document_id, ticker, document_type, fiscal_period,
                   section_name, section_type, chunk_text, word_count,
                   1 - (embedding <=> $1::vector) AS similarity
            FROM chunks
            WHERE {where}
            ORDER BY embedding <=> $1::vector
            LIMIT {total_limit}
        """
    else:
        query = f"""
            SELECT chunk_id, document_id, ticker, document_type, fiscal_period,
                   section_name, section_type, chunk_text, word_count,
                   1 - (embedding <=> $1::vector) AS similarity
            FROM chunks
            WHERE {where}
            ORDER BY embedding <=> $1::vector
            LIMIT {limit_per_ticker}
        """

    async with get_conn() as conn:
        rows = await conn.fetch(query, *params)

    search_duration_ms = int((time.time() - t0) * 1000)
    results = [
        ChunkResult(
            chunk_id=str(r["chunk_id"]) if r["chunk_id"] else None,
            document_id=str(r["document_id"]) if r["document_id"] else None,
            ticker=r["ticker"],
            document_type=r["document_type"],
            fiscal_period=r["fiscal_period"],
            section_name=r["section_name"],
            section_type=r["section_type"],
            chunk_text=r["chunk_text"],
            word_count=r["word_count"],
            similarity=float(r["similarity"]),
        )
        for r in rows
    ]
    if steps:
        ticker_str = ", ".join(tickers[:3]) + ("..." if len(tickers) > 3 else "")
        steps.add(
            label=f"Searching {ticker_str} documents" if tickers else "Searching documents",
            detail="pgvector cosine similarity on chunks table",
            source="supabase",
            duration_ms=search_duration_ms,
            result_summary=f"{len(results)} chunks found",
            query=format_sql(query, params),
        )
    return results


async def _structured_query(
    tickers: list[str],
    topic: str,
    fiscal_periods: list[str] | None = None,
    steps: StepCollector | None = None,
) -> list[dict]:
    """Query financial_metrics table for quantitative answers."""
    t0 = time.time()
    ticker = tickers[0] if tickers else None
    if not ticker:
        return []

    # Determine which metrics to fetch based on topic
    topic_lower = topic.lower()
    metrics: list[str] = []

    if any(kw in topic_lower for kw in ["revenue", "margin", "income", "eps", "earnings", "profit", "sales"]):
        metrics.extend(["total_revenue", "gross_profit", "operating_income", "net_income",
                        "diluted_eps", "ebitda", "operating_expense", "cost_of_revenue"])
    if any(kw in topic_lower for kw in ["debt", "asset", "equity", "balance", "cash and equivalents", "liabilities"]):
        metrics.extend(["total_assets", "total_liabilities_net_minority_interest",
                        "stockholders_equity", "total_debt", "cash_and_cash_equivalents"])
    if any(kw in topic_lower for kw in ["cash flow", "capex", "capital expenditure", "free cash flow", "operating cash", "fcf"]):
        metrics.extend(["operating_cash_flow", "free_cash_flow", "capital_expenditure",
                        "investing_cash_flow", "financing_cash_flow"])

    if not metrics:
        metrics = ["total_revenue", "gross_profit", "operating_income", "net_income", "diluted_eps"]

    metrics_sql = """SELECT metric_name, period_end, period_type, value
               FROM financial_metrics
               WHERE ticker = $1 AND metric_name = ANY($2)
               ORDER BY period_end DESC LIMIT 50"""
    async with get_conn() as conn:
        rows = await conn.fetch(metrics_sql, ticker, metrics)

    results = [dict(r) for r in rows]

    structured_duration_ms = int((time.time() - t0) * 1000)
    if steps:
        steps.add(
            label=f"Fetching {ticker} financial data",
            detail=f"SQL query on financial_metrics ({len(metrics)} metrics)",
            source="supabase",
            duration_ms=structured_duration_ms,
            result_summary=f"{len(results)} rows",
            query=format_sql(metrics_sql, [ticker, metrics]),
        )
    return results


async def _query_financial_metrics(
    tickers: list[str],
    classified: ClassifiedQuery,
    steps: StepCollector | None = None,
) -> list[dict]:
    """Query financial_metrics — delegates to existing _structured_query."""
    return await _structured_query(
        tickers, classified.topic, classified.fiscal_periods or None, steps=steps,
    )


def _normalize_estimate_period(period: str) -> str:
    """Normalize period format to match daily_estimates storage.

    FY2025 → 2025A, 2025 → 2025A, Q4_2025 → 2025Q4, 2025Q4 → 2025Q4.
    """
    period = period.strip()
    if period.startswith("FY"):
        return period[2:] + "A"
    if period.endswith("A") or "Q" in period:
        if "_" in period:
            # Q4_2025 → 2025Q4
            parts = period.split("_")
            if len(parts) == 2:
                return parts[1] + parts[0]
        return period
    if len(period) == 4 and period.isdigit():
        return period + "A"
    return period


_METRIC_ALIASES: dict[str, str] = {
    "eps": "diluted_eps",
    "earnings per share": "diluted_eps",
    "revenue": "total_revenue",
    "sales": "total_revenue",
    "fcf": "free_cash_flow",
    "cash flow": "free_cash_flow",
}


async def _query_estimates(
    tickers: list[str],
    metrics: list[str] | None = None,
    periods: list[str] | None = None,
    sources: list[str] | None = None,
    steps: StepCollector | None = None,
) -> list[dict]:
    """Unified estimates query — always returns individual rows, never aggregates.

    One row per source/firm/analyst. Enriched with YoY vs prior year actual.
    """
    if not tickers:
        return []

    t0 = time.time()

    # Resolve metric aliases
    resolved_metrics: list[str] | None = None
    if metrics:
        resolved_metrics = [_METRIC_ALIASES.get(m.lower(), m) for m in metrics]

    conditions = ["ticker = ANY($1)"]
    params: list = [tickers]
    idx = 2

    if resolved_metrics:
        conditions.append(f"metric = ANY(${idx})")
        params.append(resolved_metrics)
        idx += 1

    if periods:
        normalized = [_normalize_estimate_period(p) for p in periods]
        conditions.append(f"period = ANY(${idx})")
        params.append(normalized)
        idx += 1

    if sources:
        conditions.append(f"source = ANY(${idx})")
        params.append(sources)
        idx += 1

    # Most recent as_of_date per ticker/metric/period/source/firm/analyst
    conditions.append(
        "as_of_date = ("
        "  SELECT MAX(de2.as_of_date)"
        "  FROM daily_estimates de2"
        "  WHERE de2.ticker = daily_estimates.ticker"
        "    AND de2.metric = daily_estimates.metric"
        "    AND de2.period = daily_estimates.period"
        "    AND de2.source = daily_estimates.source"
        "    AND COALESCE(de2.firm, '') = COALESCE(daily_estimates.firm, '')"
        "    AND COALESCE(de2.analyst_name, '') = COALESCE(daily_estimates.analyst_name, '')"
        ")"
    )

    where = " AND ".join(conditions)

    estimates_sql = f"""SELECT
                    ticker, metric, period,
                    period_start_date, period_end_date,
                    source, firm, analyst_name,
                    value, unit,
                    estimate_date, as_of_date,
                    staleness_days
                FROM daily_estimates
                WHERE {where}
                ORDER BY ticker, metric, period,
                    source, firm, analyst_name NULLS LAST"""

    async with get_conn() as conn:
        estimate_rows = await conn.fetch(estimates_sql, *params)

        if not estimate_rows:
            duration_ms = int((time.time() - t0) * 1000)
            if steps:
                steps.add(
                    label="Fetching estimates",
                    detail="daily_estimates: 0 rows",
                    source="supabase",
                    duration_ms=duration_ms,
                    result_summary="0 estimate rows",
                    query=format_sql(estimates_sql, params),
                )
            return []

        # Get prior year actuals for YoY enrichment — split by period type
        unique_tickers = list({r["ticker"] for r in estimate_rows})
        unique_metrics = list({r["metric"] for r in estimate_rows})

        # 1) Annual actuals: all annual actuals per ticker+metric (keyed by year)
        #    so 2027A estimate looks up 2026 actual, 2026A looks up 2025, etc.
        annual_actual_rows = await conn.fetch(
            """SELECT ticker, metric_name, value, period_end,
                      EXTRACT(YEAR FROM period_end)::int AS fiscal_year
               FROM financial_metrics
               WHERE ticker = ANY($1)
                 AND metric_name = ANY($2)
                 AND period_type = 'annual'
                 AND value IS NOT NULL
               ORDER BY ticker, metric_name, period_end DESC""",
            unique_tickers,
            unique_metrics,
        )

        # 2) Quarterly actuals: same quarter one year prior for each quarterly estimate
        #    Collect unique (ticker, metric, prior_year_start, prior_year_end) windows
        from datetime import date as date_type
        quarterly_windows: list[tuple[str, str, date_type, date_type]] = []
        for r in estimate_rows:
            if "Q" in r["period"] and r["period_start_date"] and r["period_end_date"]:
                psd = r["period_start_date"]
                ped = r["period_end_date"]
                # Ensure we have date objects for asyncpg
                if isinstance(psd, str):
                    psd = date_type.fromisoformat(psd)
                if isinstance(ped, str):
                    ped = date_type.fromisoformat(ped)
                quarterly_windows.append((r["ticker"], r["metric"], psd, ped))

        quarterly_actual_rows: list = []
        if quarterly_windows:
            # Build a VALUES table of (ticker, metric, prior_start, prior_end) and join
            # Use a single query with unnest for efficiency
            q_tickers = [w[0] for w in quarterly_windows]
            q_metrics = [w[1] for w in quarterly_windows]
            q_starts = [w[2] for w in quarterly_windows]
            q_ends = [w[3] for w in quarterly_windows]

            quarterly_actual_rows = await conn.fetch(
                """SELECT DISTINCT ON (w.ticker, w.metric, w.prior_start)
                          w.ticker, w.metric, fm.value, fm.period_end,
                          w.prior_start, w.prior_end
                   FROM unnest($1::text[], $2::text[], $3::date[], $4::date[])
                        AS w(ticker, metric, prior_start, prior_end)
                   JOIN financial_metrics fm
                     ON fm.ticker = w.ticker
                    AND fm.metric_name = w.metric
                    AND fm.period_type = 'quarterly'
                    AND fm.period_end BETWEEN (w.prior_start - INTERVAL '1 year')
                                         AND (w.prior_end - INTERVAL '1 year')
                    AND fm.value IS NOT NULL
                   ORDER BY w.ticker, w.metric, w.prior_start, fm.period_end DESC""",
                q_tickers, q_metrics, q_starts, q_ends,
            )

    # Build actual lookups
    # Annual: (ticker, metric, fiscal_year) -> (value, period_end)
    annual_actuals: dict[tuple[str, str, int], tuple[float, str]] = {}
    for a in annual_actual_rows:
        key = (a["ticker"], a["metric_name"], a["fiscal_year"])
        if key not in annual_actuals:  # first row per key is most recent
            annual_actuals[key] = (float(a["value"]), str(a["period_end"]))

    # Quarterly: (ticker, metric, period_start_str) -> (value, period_end)
    quarterly_actuals: dict[tuple[str, str, str], tuple[float, str]] = {}
    for a in quarterly_actual_rows:
        quarterly_actuals[(a["ticker"], a["metric"], str(a["prior_start"]))] = (
            float(a["value"]),
            str(a["period_end"]),
        )

    # Enrich results with YoY
    results: list[dict] = []
    for row in estimate_rows:
        r = dict(row) | {"_table": "daily_estimates"}
        ticker_metric = (r["ticker"], r["metric"])

        actual_val: float | None = None
        actual_period: str | None = None

        if "Q" in r["period"] and r["period_start_date"]:
            # Quarterly: look up same quarter prior year
            qkey = (r["ticker"], r["metric"], str(r["period_start_date"]))
            q_actual = quarterly_actuals.get(qkey)
            if q_actual:
                actual_val, actual_period = q_actual
        elif r["period"].endswith("A"):
            # Annual: look up prior year actual (2027A → 2026 actual)
            import re as _re
            year_match = _re.search(r"\d{4}", r["period"])
            if year_match:
                est_year = int(year_match.group())
                a_actual = annual_actuals.get((r["ticker"], r["metric"], est_year - 1))
                if a_actual:
                    actual_val, actual_period = a_actual

        if actual_val and actual_val > 0:
            r["prior_year_actual"] = actual_val
            r["prior_year_period"] = actual_period
            est_val = float(r["value"]) if r["value"] is not None else None
            if est_val is not None:
                r["yoy_vs_actual"] = round((est_val / actual_val - 1) * 100, 1)
            else:
                r["yoy_vs_actual"] = None
        else:
            r["prior_year_actual"] = None
            r["prior_year_period"] = None
            r["yoy_vs_actual"] = None

        results.append(r)

    duration_ms = int((time.time() - t0) * 1000)

    if steps:
        n_tickers = len({r["ticker"] for r in results})
        n_sources = len({r["source"] for r in results})
        steps.add(
            label="Fetching estimates",
            detail=f"daily_estimates: {n_tickers} ticker(s), {len(results)} rows, {n_sources} sources",
            source="supabase",
            duration_ms=duration_ms,
            result_summary=f"{len(results)} estimate rows",
            query=format_sql(estimates_sql, params),
        )

    return results


# ---------------------------------------------------------------------------
# Portfolio name normalization — DB stores Title Case with spaces
# ---------------------------------------------------------------------------
PORTFOLIO_MAP: dict[str, str | None] = {
    "long_only": "Long Only",
    "long only": "Long Only",
    "flagship": "Flagship",
    "all": None,  # None = no filter (all portfolios)
}


def _normalize_portfolio(raw: str | None) -> str | None:
    """Map tool-level portfolio input to actual DB value.

    Returns None when no portfolio filter should be applied.
    """
    if not raw:
        return None
    key = raw.strip().lower()
    if key in PORTFOLIO_MAP:
        return PORTFOLIO_MAP[key]
    # Fallback: try title-casing
    return raw.strip().title()


async def _query_estimates_timeseries(
    tickers: list[str],
    metric: str,
    period: str,
) -> list[dict]:
    """Query daily_estimates across ALL as_of_dates for charting.

    Returns the full time series for a single metric+period combo,
    sampled weekly to keep row count manageable.
    """
    if not tickers:
        return []

    async with get_conn() as conn:
        rows = await conn.fetch(
            """SELECT ticker, metric, period,
                      period_start_date, period_end_date,
                      source, firm, analyst_name,
                      analyst_person_id,
                      value, unit,
                      estimate_date, as_of_date,
                      staleness_days
               FROM daily_estimates
               WHERE ticker = ANY($1)
               AND metric = $2
               AND period = $3
               AND EXTRACT(DOW FROM as_of_date) = 1
               ORDER BY as_of_date, source, firm, analyst_name""",
            tickers, metric, period,
        )

    return [dict(r) | {"_table": "daily_estimates"} for r in rows]


async def _query_daily_pnl(
    tickers: list[str] | None = None,
    classified: ClassifiedQuery | None = None,
    steps: StepCollector | None = None,
    portfolio: str | None = None,
    date: str | None = None,
    date_range: dict | None = None,
    group_by: list[str] | None = None,
    ticker: str | None = None,
    limit: int | None = None,
    order_by: str | None = None,
    order_dir: str | None = None,
) -> list[dict]:
    """Query daily_pnl with flexible filtering for portfolio queries.

    When no tickers are provided, queries across ALL positions (required
    for portfolio-wide queries like 'top 5 holdings').
    """
    t0 = time.time()

    conditions: list[str] = []
    params: list = []
    idx = 1

    # Portfolio filter
    norm_portfolio = _normalize_portfolio(portfolio)
    if norm_portfolio:
        conditions.append(f"portfolio = ${idx}")
        params.append(norm_portfolio)
        idx += 1

    # Ticker filter — single ticker takes precedence
    if ticker:
        conditions.append(f"ticker = ${idx}")
        params.append(ticker.upper())
        idx += 1
    elif tickers:
        conditions.append(f"ticker = ANY(${idx})")
        params.append(tickers)
        idx += 1
    # else: no ticker filter — return all positions

    # Date filter
    if date:
        conditions.append(f"date = ${idx}::date")
        params.append(date)
        idx += 1
    elif date_range and date_range.get("start") and date_range.get("end"):
        conditions.append(f"date BETWEEN ${idx}::date AND ${idx + 1}::date")
        params.extend([date_range["start"], date_range["end"]])
        idx += 2
    else:
        conditions.append("date = (SELECT MAX(date) FROM daily_pnl)")

    where = " AND ".join(conditions) if conditions else "TRUE"

    # Order
    safe_order_by = order_by if order_by in (
        "unrealized_pnl", "realized_pnl", "market_value", "cost_basis",
        "daily_return", "cumulative_return", "contribution_to_portfolio",
        "ticker", "date", "shares_held",
    ) else "unrealized_pnl"
    safe_order_dir = "ASC" if (order_dir or "").lower() == "asc" else "DESC"
    safe_limit = min(limit or 100, 500)

    # When querying all portfolios, always group results by portfolio first
    # so they come back separated (never mixed)
    portfolio_order_prefix = "" if norm_portfolio else "portfolio, "

    # Group by aggregation
    if group_by:
        safe_group_cols = [c for c in group_by if c in (
            "portfolio", "side", "sector", "industry", "ticker", "date",
        )]
        if not safe_group_cols:
            safe_group_cols = ["portfolio", "side"]
        # Always include portfolio in group when querying all
        if not norm_portfolio and "portfolio" not in safe_group_cols:
            safe_group_cols.insert(0, "portfolio")
        group_str = ", ".join(safe_group_cols)
        sql = f"""
            SELECT {group_str},
                   SUM(unrealized_pnl) AS unrealized_pnl,
                   SUM(realized_pnl) AS realized_pnl,
                   SUM(market_value) AS market_value,
                   SUM(cost_basis) AS cost_basis,
                   AVG(daily_return) AS daily_return,
                   SUM(contribution_to_portfolio) AS contribution_to_portfolio,
                   SUM(daily_realized_pnl) AS daily_realized_pnl,
                   SUM(ytd_pnl) AS ytd_pnl,
                   SUM(itd_pnl) AS itd_pnl
            FROM daily_pnl
            WHERE {where}
            GROUP BY {group_str}
            ORDER BY {portfolio_order_prefix}{safe_order_by} {safe_order_dir}
            LIMIT {safe_limit}
        """
    else:
        sql = f"""
            SELECT date, ticker, portfolio, side, sector, industry,
                   unrealized_pnl, realized_pnl, daily_return,
                   cumulative_return, contribution_to_portfolio,
                   shares_held, market_value, cost_basis,
                   daily_realized_pnl, ytd_pnl, itd_pnl
            FROM daily_pnl
            WHERE {where}
            ORDER BY {portfolio_order_prefix}{safe_order_by} {safe_order_dir}
            LIMIT {safe_limit}
        """

    async with get_conn() as conn:
        rows = await conn.fetch(sql, *params)

    results = [dict(r) | {"_table": "daily_pnl"} for r in rows]
    duration_ms = int((time.time() - t0) * 1000)
    if steps:
        steps.add(
            label="Fetching P&L data",
            detail=f"daily_pnl ({len(results)} rows)",
            source="supabase",
            duration_ms=duration_ms,
            result_summary=f"{len(results)} rows",
            query=format_sql(sql, params),
        )
    return results


async def _query_portfolio_concentration(
    tickers: list[str] | None = None,
    classified: ClassifiedQuery | None = None,
    steps: StepCollector | None = None,
    portfolio: str | None = None,
    ticker: str | None = None,
) -> list[dict]:
    """Query portfolio_concentration for most recent date."""
    t0 = time.time()
    conditions = ["date = (SELECT MAX(date) FROM portfolio_concentration)"]
    params: list = []
    idx = 1

    norm_portfolio = _normalize_portfolio(portfolio)
    if norm_portfolio:
        conditions.append(f"portfolio = ${idx}")
        params.append(norm_portfolio)
        idx += 1

    if ticker:
        conditions.append(f"ticker = ${idx}")
        params.append(ticker.upper())
        idx += 1
    elif tickers:
        conditions.append(f"ticker = ANY(${idx})")
        params.append(tickers)
        idx += 1

    where = " AND ".join(conditions)
    portfolio_order = "" if norm_portfolio else "portfolio, "
    concentration_sql = f"""SELECT date, ticker, portfolio, side, sector, industry,
                       position_weight, sector_weight, industry_weight,
                       is_market_neutral_compliant
                FROM portfolio_concentration
                WHERE {where}
                ORDER BY {portfolio_order}position_weight DESC
                LIMIT 200"""
    async with get_conn() as conn:
        rows = await conn.fetch(concentration_sql, *params)
    results = [dict(r) | {"_table": "portfolio_concentration"} for r in rows]
    duration_ms = int((time.time() - t0) * 1000)
    if steps:
        steps.add(
            label="Fetching concentration data",
            detail=f"portfolio_concentration ({len(results)} rows)",
            source="supabase",
            duration_ms=duration_ms,
            result_summary=f"{len(results)} rows",
            query=format_sql(concentration_sql, params),
        )
    return results


async def _query_portfolio_risk(
    tickers: list[str] | None = None,
    classified: ClassifiedQuery | None = None,
    steps: StepCollector | None = None,
    portfolio: str | None = None,
    ticker: str | None = None,
) -> list[dict]:
    """Query portfolio_risk for most recent date."""
    t0 = time.time()
    conditions = ["date = (SELECT MAX(date) FROM portfolio_risk)"]
    params: list = []
    idx = 1

    norm_portfolio = _normalize_portfolio(portfolio)
    if norm_portfolio:
        conditions.append(f"portfolio = ${idx}")
        params.append(norm_portfolio)
        idx += 1

    if ticker:
        conditions.append(f"ticker = ${idx}")
        params.append(ticker.upper())
        idx += 1
    elif tickers:
        conditions.append(f"ticker = ANY(${idx})")
        params.append(tickers)
        idx += 1

    where = " AND ".join(conditions)
    portfolio_order = "" if norm_portfolio else "portfolio, "
    risk_sql = f"""SELECT date, ticker, portfolio, side, sector,
                       beta, weighted_beta_contribution
                FROM portfolio_risk
                WHERE {where}
                ORDER BY {portfolio_order}weighted_beta_contribution DESC
                LIMIT 200"""
    async with get_conn() as conn:
        rows = await conn.fetch(risk_sql, *params)
    results = [dict(r) | {"_table": "portfolio_risk"} for r in rows]
    duration_ms = int((time.time() - t0) * 1000)
    if steps:
        steps.add(
            label="Fetching risk data",
            detail=f"portfolio_risk ({len(results)} rows)",
            source="supabase",
            duration_ms=duration_ms,
            result_summary=f"{len(results)} rows",
            query=format_sql(risk_sql, params),
        )
    return results


async def _query_trade_requests(
    tickers: list[str] | None = None,
    classified: ClassifiedQuery | None = None,
    steps: StepCollector | None = None,
    ticker: str | None = None,
    status: str | None = None,
    portfolio: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Query trade_requests with flexible filtering, most recent first."""
    t0 = time.time()

    conditions: list[str] = []
    params: list = []
    idx = 1

    # Support both tickers list and single ticker
    effective_tickers = tickers or []
    if ticker and ticker not in effective_tickers:
        effective_tickers = [ticker.upper()]

    if effective_tickers:
        conditions.append(f"ticker = ANY(${idx})")
        params.append(effective_tickers)
        idx += 1

    if status:
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1

    if portfolio:
        conditions.append(f"portfolio = ${idx}")
        params.append(portfolio)
        idx += 1

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    trade_sql = f"""SELECT ticker, portfolio, action, side, target_pct, status,
                      created_at, executed_at
               FROM trade_requests
               {where}
               ORDER BY created_at DESC
               LIMIT ${idx}"""
    params.append(limit)

    async with get_conn() as conn:
        rows = await conn.fetch(trade_sql, *params)
    results = [dict(r) | {"_table": "trade_requests"} for r in rows]
    duration_ms = int((time.time() - t0) * 1000)
    if steps:
        steps.add(
            label="Fetching trade requests",
            detail=f"trade_requests ({len(results)} rows)",
            source="supabase",
            duration_ms=duration_ms,
            result_summary=f"{len(results)} rows",
            query=format_sql(trade_sql, params),
        )
    return results


async def _query_guidance(
    tickers: list[str],
    classified: ClassifiedQuery,
    steps: StepCollector | None = None,
) -> list[dict]:
    """Query guidance for tickers and optional periods."""
    if not tickers:
        return []
    t0 = time.time()
    params: list = [tickers]
    period_clause = ""
    if classified.fiscal_periods:
        period_clause = " AND period = ANY($2)"
        params.append(classified.fiscal_periods)
    guidance_sql = f"""SELECT ticker, metric, period,
                       value, unit, guidance_type,
                       source, issued_date
                FROM guidance
                WHERE ticker = ANY($1){period_clause}
                ORDER BY issued_date DESC
                LIMIT 50"""
    async with get_conn() as conn:
        rows = await conn.fetch(guidance_sql, *params)
    results = [dict(r) | {"_table": "guidance"} for r in rows]
    duration_ms = int((time.time() - t0) * 1000)
    if steps:
        steps.add(
            label="Fetching guidance",
            detail=f"guidance ({len(results)} rows)",
            source="supabase",
            duration_ms=duration_ms,
            result_summary=f"{len(results)} rows",
            query=format_sql(guidance_sql, params),
        )
    return results


async def _query_alt_data(
    ticker: str,
    data_types: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int | None = None,
    steps: StepCollector | None = None,
) -> list[dict]:
    """Query alt_data for a single ticker. No aggregation — raw rows only."""
    if not ticker:
        return []
    t0 = time.time()

    conditions = ["ticker = $1"]
    params: list = [ticker]
    idx = 2

    if data_types:
        conditions.append(f"data_type = ANY(${idx})")
        params.append(data_types)
        idx += 1
    if date_from:
        conditions.append(f"date >= ${idx}::date")
        params.append(date_from)
        idx += 1
    if date_to:
        conditions.append(f"date <= ${idx}::date")
        params.append(date_to)
        idx += 1

    where = " AND ".join(conditions)
    row_limit = limit or 30
    params.append(row_limit)

    query = f"""
        WITH ranked AS (
            SELECT ticker, data_type, date_frequency, date,
                   value, growth, unit, source_vendor,
                   data_as_of_date, as_of_date,
                   ROW_NUMBER() OVER (
                       PARTITION BY data_type ORDER BY date DESC
                   ) as rn
            FROM alt_data
            WHERE {where}
        )
        SELECT ticker, data_type, date_frequency, date,
               value, growth, unit, source_vendor,
               data_as_of_date, as_of_date
        FROM ranked
        WHERE rn <= ${idx}
        ORDER BY data_type, date DESC
    """

    async with get_conn() as conn:
        rows = await conn.fetch(query, *params)

    results = [dict(r) | {"_table": "alt_data"} for r in rows]
    duration_ms = int((time.time() - t0) * 1000)

    if steps:
        signal_counts: dict[str, int] = {}
        for r in results:
            dt = r["data_type"]
            signal_counts[dt] = signal_counts.get(dt, 0) + 1
        summary = ", ".join(f"{k}({v})" for k, v in signal_counts.items())
        steps.add(
            label="Fetching alt data",
            detail=f"alt_data: {ticker} — {len(results)} rows across {len(signal_counts)} signals",
            source="supabase",
            duration_ms=duration_ms,
            result_summary=summary or f"{len(results)} rows",
            query=format_sql(query, params),
        )
    return results


async def _query_model_outputs(
    tickers: list[str],
    classified: ClassifiedQuery,
    steps: StepCollector | None = None,
) -> list[dict]:
    """Query model_outputs, most recent version per ticker.

    Uses the DISTINCT ON pattern from data-schema.md:
        SELECT DISTINCT ON (ticker, sheet, metric, period, scenario) *
        FROM model_outputs
        ORDER BY ticker, sheet, metric, period, scenario, as_of_date DESC
    """
    if not tickers:
        return []
    t0 = time.time()
    model_sql = """SELECT DISTINCT ON (ticker, sheet, metric, period, scenario)
                      ticker, sheet, metric, period, scenario,
                      value, unit, version, as_of_date, created_by, created_at
               FROM model_outputs
               WHERE ticker = ANY($1)
               ORDER BY ticker, sheet, metric, period, scenario, as_of_date DESC
               LIMIT 500"""
    async with get_conn() as conn:
        rows = await conn.fetch(model_sql, tickers)
    results = [dict(r) | {"_table": "model_outputs"} for r in rows]
    duration_ms = int((time.time() - t0) * 1000)
    if steps:
        steps.add(
            label="Fetching model outputs",
            detail=f"model_outputs ({len(results)} rows)",
            source="supabase",
            duration_ms=duration_ms,
            result_summary=f"{len(results)} rows",
            query=format_sql(model_sql, [tickers]),
        )
    return results


async def _query_stock_history(
    tickers: list[str],
    classified: ClassifiedQuery | None = None,
    lookback_days: int = 90,
    steps: StepCollector | None = None,
) -> list[dict]:
    """Query stock_history for tickers with configurable lookback."""
    if not tickers:
        return []
    t0 = time.time()
    history_sql = f"""SELECT
                 ticker,
                 date::date AS date,
                 close::numeric AS close,
                 NULLIF(eps_estimate, '')::numeric AS eps_estimate,
                 NULLIF(eps_actual, '')::numeric AS eps_actual
               FROM stock_history
               WHERE ticker = ANY($1)
                 AND date::date >= CURRENT_DATE - INTERVAL '{lookback_days} days'
               ORDER BY date::date DESC
               LIMIT 500"""
    async with get_conn() as conn:
        rows = await conn.fetch(history_sql, tickers)
    results = [dict(r) | {"_table": "stock_history"} for r in rows]
    duration_ms = int((time.time() - t0) * 1000)
    if steps:
        steps.add(
            label="Fetching price history",
            detail=f"stock_history ({len(results)} rows, {lookback_days}d)",
            source="supabase",
            duration_ms=duration_ms,
            result_summary=f"{len(results)} rows",
            query=format_sql(history_sql, [tickers]),
        )
    return results


async def _query_workflow_registry(
    tickers: list[str],
    classified: ClassifiedQuery,
    steps: StepCollector | None = None,
) -> list[dict]:
    """Query workflow_registry by name if specified."""
    t0 = time.time()
    if classified.workflow_name:
        registry_sql = """SELECT workflow_name, description, input_schema, output_table,
                          schedule, is_active
                   FROM workflow_registry
                   WHERE workflow_name = $1
                   LIMIT 10"""
        registry_params: list = [classified.workflow_name]
        async with get_conn() as conn:
            rows = await conn.fetch(registry_sql, *registry_params)
    else:
        registry_sql = """SELECT workflow_name, description, input_schema, output_table,
                          schedule, is_active
                   FROM workflow_registry
                   WHERE is_active = TRUE
                   LIMIT 50"""
        registry_params = []
        async with get_conn() as conn:
            rows = await conn.fetch(registry_sql)
    results = [dict(r) | {"_table": "workflow_registry"} for r in rows]
    duration_ms = int((time.time() - t0) * 1000)
    if steps:
        steps.add(
            label="Fetching workflow info",
            detail=f"workflow_registry ({len(results)} rows)",
            source="supabase",
            duration_ms=duration_ms,
            result_summary=f"{len(results)} rows",
            query=format_sql(registry_sql, registry_params),
        )
    return results


async def _screening_prefilter(
    chunks: list[ChunkResult],
    query: str,
    session_id: str | None = None,
    message_id: str | None = None,
    user_id: str | None = None,
    steps: StepCollector | None = None,
) -> list[ChunkResult]:
    """Use Haiku to pre-filter large screening results down to top 20."""
    if len(chunks) <= 20:
        return chunks

    config = await get_model_config("screening_prefilter")
    model = config["model"]

    chunk_summaries = []
    for i, c in enumerate(chunks):
        chunk_summaries.append(
            f"[{i}] {c.ticker} | {c.fiscal_period} | {c.section_name}: {c.chunk_text[:300]}"
        )

    prompt = f"""You are filtering financial document chunks for a screening query.

Query: {query}

Below are {len(chunks)} chunks. Return a JSON array of the indices (numbers in brackets) of the 20 most relevant chunks that best answer the screening query. Return ONLY a JSON array of integers, nothing else.

{chr(10).join(chunk_summaries)}"""

    api_key = os.environ.get("GOLDMINE_ANTHROPIC_API_KEY", "")
    client = anthropic.Anthropic(api_key=api_key)
    t0 = time.time()
    response = client.messages.create(
        model=model,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    prefilter_duration_ms = int((time.time() - t0) * 1000)

    raw = response.content[0].text.strip()
    cost = await calculate_cost(model, response.usage.input_tokens, response.usage.output_tokens)
    if steps:
        steps.add(
            label="Filtering screening results",
            detail=f"Haiku prefilter ({len(chunks)} → 20 chunks)",
            source="anthropic",
            model=model,
            cost_usd=cost,
            duration_ms=prefilter_duration_ms,
            result_summary="",
        )
    emit_cost_event(
        mode="mode_2",
        component="screening_prefilter",
        model=model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        cost_usd=cost,
        session_id=session_id,
        message_id=message_id,
        user_id=user_id,
    )

    try:
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        indices = json.loads(raw)
        filtered = [chunks[i] for i in indices if 0 <= i < len(chunks)]
        if steps:
            steps.steps[-1]["result_summary"] = f"{len(filtered)} chunks kept"
        return filtered
    except Exception:
        logger.warning("Screening prefilter returned invalid JSON: %s", raw[:200])
        return chunks[:20]


def _estimate_tokens(chunks: list[ChunkResult], structured: list[dict] | None) -> int:
    """Rough estimate of total input tokens from context."""
    total = 500  # system prompt
    total += 1100  # history budget
    for c in chunks:
        total += int(c.word_count * 1.33)
    if structured:
        total += len(json.dumps(structured, default=str)) // 4
    total += 100  # user question
    return total
