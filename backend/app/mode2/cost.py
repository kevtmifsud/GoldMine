"""DS-04: Cost tracking — async, non-blocking cost event logging."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from .db import get_pool

logger = logging.getLogger(__name__)


async def _log_cost_event(
    mode: str,
    component: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_usd: float = 0.0,
    session_id: str | None = None,
    message_id: str | None = None,
    user_id: str | None = None,
    query_type: str | None = None,
    ticker_count: int | None = None,
    document_id: str | None = None,
) -> None:
    """Insert a cost event row. Runs as fire-and-forget task."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO api_cost_events
                   (mode, component, model, input_tokens, output_tokens, cost_usd,
                    session_id, message_id, user_id, query_type, ticker_count)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)""",
                mode, component, model, input_tokens, output_tokens, cost_usd,
                session_id, message_id, user_id, query_type, ticker_count,
            )
    except Exception:
        logger.exception("Failed to log cost event for %s/%s", mode, component)


def emit_cost_event(**kwargs: Any) -> None:
    """Schedule a cost event to be logged asynchronously (non-blocking)."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_log_cost_event(**kwargs))
    except RuntimeError:
        # No running loop — log synchronously as fallback
        asyncio.run(_log_cost_event(**kwargs))


async def get_model_config(component: str) -> dict[str, str]:
    """Read model assignment from model_config table at runtime."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT model, provider FROM model_config WHERE component = $1",
            component,
        )
    if row is None:
        raise ValueError(f"No model_config entry for component '{component}'")
    return {"model": row["model"], "provider": row["provider"]}


async def calculate_cost(model: str, input_tokens: int, output_tokens: int = 0) -> float:
    """Calculate USD cost using api_pricing table."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT input_per_1m, output_per_1m FROM api_pricing WHERE model = $1 AND is_current = TRUE",
            model,
        )
    if row is None:
        return 0.0
    cost = (input_tokens / 1_000_000) * float(row["input_per_1m"])
    if output_tokens and row["output_per_1m"] is not None:
        cost += (output_tokens / 1_000_000) * float(row["output_per_1m"])
    return cost
