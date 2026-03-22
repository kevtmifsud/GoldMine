"""WF-07: Ticker Resolution.

Expands list references and group descriptors into concrete ticker arrays.
Pure database — no LLM calls, no cost events.
"""
from __future__ import annotations

from .db import get_conn
from .models import ClassifiedQuery, ResolvedUniverse

# Maximum tickers per query type
_MAX_TICKERS = {
    "cross_ticker": 50,
    "screening": None,  # No cap
    "trend_analysis": 1,
    "single_ticker_qualitative": 1,
    "single_ticker_quantitative": 1,
}


async def resolve_tickers(
    classified: ClassifiedQuery,
    user_id: str | None = None,
) -> ResolvedUniverse:
    """Resolve tickers from classifier output into concrete ticker list."""
    resolved: dict[str, str] = {}  # ticker -> source
    was_truncated = False

    async with get_conn() as conn:
        # Source 1: Explicit tickers — validate against master table
        if classified.tickers:
            placeholders = ", ".join(f"${i+1}" for i in range(len(classified.tickers)))
            rows = await conn.fetch(
                f"SELECT ticker FROM stocks WHERE ticker IN ({placeholders})",
                *classified.tickers,
            )
            valid = {r["ticker"] for r in rows}
            for t in classified.tickers:
                if t in valid:
                    resolved[t] = "explicit"

        # Source 2: User-defined lists
        if classified.list_references and user_id:
            for list_name in classified.list_references:
                row = await conn.fetchrow(
                    "SELECT tickers FROM user_ticker_lists WHERE user_id = $1 AND list_name = $2",
                    user_id, list_name,
                )
                if row and row["tickers"]:
                    for t in row["tickers"]:
                        if t not in resolved:
                            resolved[t] = f"list:{list_name}"

        # Source 3: Sector/industry/group descriptors (from topic or list_references)
        # Check if any list reference looks like a sector/industry
        if classified.list_references:
            for ref in classified.list_references:
                if ref not in (await _get_user_list_names(conn, user_id)):
                    # Not a user list — try sector/industry
                    rows = await conn.fetch(
                        """SELECT ticker FROM stocks
                           WHERE (sector ILIKE $1 OR industry ILIKE $1)""",
                        f"%{ref}%",
                    )
                    for r in rows:
                        if r["ticker"] not in resolved:
                            resolved[r["ticker"]] = f"group:{ref}"

        # Screening without specified universe: default to all active
        if classified.query_type == "screening" and not resolved:
            rows = await conn.fetch(
                "SELECT ticker FROM stocks ORDER BY ticker"
            )
            for r in rows:
                resolved[r["ticker"]] = "universe"

    # Apply caps
    max_t = _MAX_TICKERS.get(classified.query_type)
    tickers = list(resolved.keys())
    if max_t is not None and len(tickers) > max_t:
        tickers = tickers[:max_t]
        was_truncated = True
        resolved = {t: resolved[t] for t in tickers}

    return ResolvedUniverse(
        tickers=tickers,
        resolution_sources=resolved,
        was_truncated=was_truncated,
        original_list_references=classified.list_references,
    )


async def _get_user_list_names(conn, user_id: str | None) -> set[str]:
    if not user_id:
        return set()
    rows = await conn.fetch(
        "SELECT list_name FROM user_ticker_lists WHERE user_id = $1", user_id
    )
    return {r["list_name"] for r in rows}
