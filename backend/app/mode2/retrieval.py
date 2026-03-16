"""WF-08: Retrieval Orchestration.

Routes each query to correct retrieval strategy, enforces chunk limits,
checks screening cache, surfaces Q&A library hits.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime

import anthropic
from openai import OpenAI
from dotenv import load_dotenv

from .cost import get_model_config, calculate_cost, emit_cost_event
from .db import get_conn
from .models import (
    ChunkResult,
    ClassifiedQuery,
    QALibraryEntry,
    ResolvedUniverse,
    RetrievalContext,
)

logger = logging.getLogger(__name__)

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))


async def _embed_query(
    text: str,
    session_id: str | None = None,
    message_id: str | None = None,
    user_id: str | None = None,
) -> list[float]:
    """Embed a query string using the query_embedder model from config."""
    config = await get_model_config("query_embedder")
    model = config["model"]

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
    response = client.embeddings.create(model=model, input=[text], dimensions=1536)
    embedding = response.data[0].embedding
    tokens = response.usage.total_tokens

    cost = await calculate_cost(model, tokens)
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
) -> list[QALibraryEntry]:
    """Search Q&A library for validated entries similar to the query."""
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
    return [
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
) -> list[ChunkResult]:
    """Perform pgvector cosine similarity search."""
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

    return [
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


async def _structured_query(
    tickers: list[str],
    topic: str,
    fiscal_periods: list[str] | None = None,
) -> list[dict]:
    """Query structured financial tables for quantitative answers."""
    results = []
    ticker = tickers[0] if tickers else None
    if not ticker:
        return results

    async with get_conn() as conn:
        # Determine which table(s) to query based on topic
        topic_lower = topic.lower()

        tables_to_query = []
        if any(kw in topic_lower for kw in ["revenue", "margin", "income", "eps", "earnings", "profit", "sales"]):
            tables_to_query.append("income_statement")
        if any(kw in topic_lower for kw in ["debt", "asset", "equity", "balance", "cash and equivalents", "liabilities"]):
            tables_to_query.append("balance_sheet")
        if any(kw in topic_lower for kw in ["cash flow", "capex", "capital expenditure", "free cash flow", "operating cash", "fcf"]):
            tables_to_query.append("cash_flow_statement")

        if not tables_to_query:
            tables_to_query = ["income_statement"]

        for table in tables_to_query:
            conditions = ["ticker = $1"]
            params: list = [ticker]
            idx = 2

            if fiscal_periods:
                placeholders = ", ".join(f"${i}" for i in range(idx, idx + len(fiscal_periods)))
                conditions.append(f"fiscal_period IN ({placeholders})")
                params.extend(fiscal_periods)
                idx += len(fiscal_periods)

            where = " AND ".join(conditions)
            query = f"SELECT * FROM {table} WHERE {where} ORDER BY fiscal_period DESC LIMIT 8"

            rows = await conn.fetch(query, *params)
            for r in rows:
                row_dict = dict(r)
                row_dict["_table"] = table
                results.append(row_dict)

    return results


async def _screening_prefilter(
    chunks: list[ChunkResult],
    query: str,
    session_id: str | None = None,
    message_id: str | None = None,
    user_id: str | None = None,
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
    response = client.messages.create(
        model=model,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    cost = await calculate_cost(model, response.usage.input_tokens, response.usage.output_tokens)
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
        return [chunks[i] for i in indices if 0 <= i < len(chunks)]
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


# ---------------------------------------------------------------------------
# Main retrieval entry point
# ---------------------------------------------------------------------------
async def retrieve_context(
    classified: ClassifiedQuery,
    universe: ResolvedUniverse,
    user_query: str,
    session_id: str | None = None,
    message_id: str | None = None,
    user_id: str | None = None,
) -> RetrievalContext:
    """Assemble retrieval context based on query type and resolved tickers."""

    # Embed the user query
    query_embedding = await _embed_query(
        user_query, session_id=session_id, message_id=message_id, user_id=user_id
    )

    # Q&A library lookup (runs on every query)
    qa_hits = await _lookup_qa_library(query_embedding)

    structured_data = None
    chunks: list[ChunkResult] = []
    cache_hit = False

    qt = classified.query_type

    if qt == "single_ticker_qualitative":
        chunks = await _vector_search(
            query_embedding,
            tickers=universe.tickers,
            limit_per_ticker=6,
            section_type=classified.section_type_hint,
            fiscal_periods=classified.fiscal_periods or None,
        )

    elif qt == "single_ticker_quantitative":
        if classified.needs_structured_data:
            structured_data = await _structured_query(
                universe.tickers, classified.topic, classified.fiscal_periods or None
            )
        if classified.needs_vector_search:
            chunks = await _vector_search(
                query_embedding,
                tickers=universe.tickers,
                limit_per_ticker=4,
                section_type=classified.section_type_hint,
                fiscal_periods=classified.fiscal_periods or None,
            )

    elif qt == "cross_ticker":
        per_ticker = 3 if len(universe.tickers) <= 20 else 2
        chunks = await _vector_search(
            query_embedding,
            tickers=universe.tickers,
            limit_per_ticker=per_ticker,
            section_type=classified.section_type_hint,
            fiscal_periods=classified.fiscal_periods or None,
        )

    elif qt == "screening":
        # Check cache first
        cached = await _check_screening_cache(user_query, classified.fiscal_periods)
        if cached:
            cache_hit = True
            chunks = [ChunkResult(**c) for c in cached.get("chunks", [])]
        else:
            # Broad retrieval
            raw_chunks = await _vector_search(
                query_embedding,
                tickers=universe.tickers,
                limit_per_ticker=3,
                section_type=classified.section_type_hint,
            )
            # Haiku pre-filter if too many
            chunks = await _screening_prefilter(
                raw_chunks, user_query,
                session_id=session_id, message_id=message_id, user_id=user_id,
            )
            # Cache the result
            await _write_screening_cache(
                user_query, classified.fiscal_periods,
                {"chunks": [c.model_dump() for c in chunks]},
            )

    elif qt == "trend_analysis":
        # Build period list from time_range_quarters
        periods = classified.fiscal_periods
        chunks = await _vector_search(
            query_embedding,
            tickers=universe.tickers,
            limit_per_ticker=3 * (classified.time_range_quarters or 4),
            section_type=classified.section_type_hint,
            fiscal_periods=periods or None,
        )

    token_est = _estimate_tokens(chunks, structured_data)

    return RetrievalContext(
        query_type=qt,
        structured_data=structured_data,
        chunks=chunks,
        qa_library_hits=qa_hits,
        cache_hit=cache_hit,
        total_chunks_retrieved=len(chunks),
        total_input_tokens_estimate=token_est,
    )
