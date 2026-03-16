"""WF-12: Sharing & Permissions.

Private by default. Share conversations/insights with specific users or team.
"""
from __future__ import annotations

import uuid

from .db import get_conn


async def share_conversation(
    conversation_id: str,
    shared_by: str,
    share_with_user_id: str | None = None,
    share_with_team: bool = False,
) -> str:
    """Share a conversation. Returns share record ID."""
    share_id = str(uuid.uuid4())
    async with get_conn() as conn:
        await conn.execute(
            """INSERT INTO conversation_shares
               (id, conversation_id, shared_by, shared_with, share_with_team)
               VALUES ($1, $2, $3, $4, $5)""",
            share_id, conversation_id, shared_by,
            share_with_user_id, share_with_team,
        )
    return share_id


async def share_insight(
    insight_id: str,
    shared_by: str,
    share_with_user_id: str | None = None,
    share_with_team: bool = False,
) -> str:
    """Share an insight. Returns share record ID."""
    share_id = str(uuid.uuid4())
    async with get_conn() as conn:
        await conn.execute(
            """INSERT INTO insight_shares
               (id, insight_id, shared_by, shared_with, share_with_team)
               VALUES ($1, $2, $3, $4, $5)""",
            share_id, insight_id, shared_by,
            share_with_user_id, share_with_team,
        )
    return share_id


async def get_shared_conversations(user_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
    """Get conversations shared with this user."""
    async with get_conn() as conn:
        rows = await conn.fetch(
            """SELECT c.id, c.title, c.ticker_context, c.updated_at,
                      cs.shared_by,
                      (SELECT COUNT(*) FROM sessions s WHERE s.conversation_id = c.id) as session_count
               FROM conversations c
               JOIN conversation_shares cs ON c.id = cs.conversation_id
               WHERE cs.shared_with = $1 OR cs.share_with_team = TRUE
               ORDER BY c.updated_at DESC
               LIMIT $2 OFFSET $3""",
            user_id, limit, offset,
        )

    return [
        {
            "id": str(r["id"]),
            "title": r["title"],
            "ticker_context": r["ticker_context"] or [],
            "session_count": r["session_count"],
            "last_active": r["updated_at"],
            "shared_by": r["shared_by"],
            "is_shared": True,
        }
        for r in rows
    ]
