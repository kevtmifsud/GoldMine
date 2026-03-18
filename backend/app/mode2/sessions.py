"""WF-10: Session & Conversation Management.

Session history assembly, rolling summary compression, conversation lifecycle.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime

import anthropic
from dotenv import load_dotenv

from .cost import get_model_config, calculate_cost, emit_cost_event
from .db import get_conn

logger = logging.getLogger(__name__)

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))


async def create_conversation(
    user_id: str,
    title: str | None = None,
    ticker_context: list[str] | None = None,
    origin_path: str | None = None,
) -> dict:
    """Create a new conversation and its first session."""
    conv_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())

    async with get_conn() as conn:
        await conn.execute(
            """INSERT INTO conversations (id, user_id, title, ticker_context, origin_path)
               VALUES ($1, $2, $3, $4, $5)""",
            conv_id, user_id, title, ticker_context or [], origin_path,
        )
        await conn.execute(
            """INSERT INTO sessions (id, conversation_id, user_id)
               VALUES ($1, $2, $3)""",
            session_id, conv_id, user_id,
        )

    return {"conversation_id": conv_id, "session_id": session_id}


async def create_session(conversation_id: str, user_id: str) -> str:
    """Create a new session within an existing conversation."""
    session_id = str(uuid.uuid4())
    async with get_conn() as conn:
        await conn.execute(
            """INSERT INTO sessions (id, conversation_id, user_id)
               VALUES ($1, $2, $3)""",
            session_id, conversation_id, user_id,
        )
    return session_id


async def get_session(session_id: str) -> dict | None:
    """Get session with its messages."""
    async with get_conn() as conn:
        session = await conn.fetchrow(
            """SELECT id, conversation_id, user_id, turn_count,
                      rolling_summary, summary_covers_through,
                      total_cost_usd, created_at, updated_at
               FROM sessions WHERE id = $1""",
            session_id,
        )
        if not session:
            return None

        messages = await conn.fetch(
            """SELECT id, role, content, query_type, tickers_referenced,
                      source_chunks, created_at
               FROM messages
               WHERE session_id = $1
               ORDER BY created_at""",
            session_id,
        )

    return {
        "session_id": session["id"],
        "conversation_id": session["conversation_id"],
        "turn_count": session["turn_count"] or 0,
        "rolling_summary": session["rolling_summary"],
        "summary_covers_through": session["summary_covers_through"],
        "created_at": session["created_at"],
        "messages": [
            {
                "message_id": str(m["id"]),
                "role": m["role"],
                "content": m["content"],
                "query_type": m["query_type"],
                "tickers_referenced": m["tickers_referenced"] or [],
                "source_chunks": json.loads(m["source_chunks"]) if m["source_chunks"] else [],
                "created_at": m["created_at"],
            }
            for m in messages
        ],
    }


async def get_session_history(session_id: str) -> list[dict[str, str]]:
    """Get message history for context assembly.

    Returns last N turns based on session state:
    - If <10 turns: all turns
    - If >=10 turns: rolling summary context + last 4 turns
    """
    async with get_conn() as conn:
        session = await conn.fetchrow(
            "SELECT turn_count, rolling_summary, summary_covers_through FROM sessions WHERE id = $1",
            session_id,
        )
        if not session:
            return []

        messages = await conn.fetch(
            """SELECT role, content FROM messages
               WHERE session_id = $1
               ORDER BY created_at""",
            session_id,
        )

    history = [{"role": m["role"], "content": m["content"]} for m in messages]

    turn_count = session["turn_count"] or 0
    if turn_count >= 10:
        # Return only last 8 messages (4 exchanges)
        return history[-8:]

    return history


async def get_rolling_summary(session_id: str) -> str | None:
    """Get the rolling summary for a session."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT rolling_summary FROM sessions WHERE id = $1", session_id
        )
    return row["rolling_summary"] if row else None


async def save_user_message(
    session_id: str,
    user_id: str,
    content: str,
    message_id: str | None = None,
) -> str:
    """Save a user message and return its ID."""
    msg_id = message_id or str(uuid.uuid4())
    async with get_conn() as conn:
        await conn.execute(
            """INSERT INTO messages (id, session_id, user_id, role, content)
               VALUES ($1, $2, $3, 'user', $4)""",
            msg_id, session_id, user_id, content,
        )
        await conn.execute(
            """UPDATE sessions
               SET turn_count = COALESCE(turn_count, 0) + 1, updated_at = NOW()
               WHERE id = $1""",
            session_id,
        )
    return msg_id


async def maybe_compress_session(
    session_id: str,
    user_id: str | None = None,
) -> None:
    """Compress session history if turn count crosses a multiple of 10.

    Runs asynchronously — never blocks user-facing response.
    """
    async with get_conn() as conn:
        session = await conn.fetchrow(
            "SELECT turn_count, summary_covers_through FROM sessions WHERE id = $1",
            session_id,
        )
        if not session:
            return

        turn_count = session["turn_count"] or 0
        covered = session["summary_covers_through"] or 0

        # Only compress at multiples of 10
        if turn_count < 10 or turn_count % 10 != 0:
            return

        # Get messages not yet covered by summary (up to turn_count - 4)
        messages = await conn.fetch(
            """SELECT role, content FROM messages
               WHERE session_id = $1
               ORDER BY created_at""",
            session_id,
        )

    if not messages:
        return

    # Messages to summarize: from covered+1 to turn_count-4
    all_msgs = [{"role": m["role"], "content": m["content"]} for m in messages]
    to_summarize = all_msgs[covered : max(covered, len(all_msgs) - 8)]

    if not to_summarize:
        return

    # Call Haiku for compression
    config = await get_model_config("session_compressor")
    model = config["model"]

    conversation_text = "\n".join(
        f"{m['role']}: {m['content'][:500]}" for m in to_summarize
    )

    prompt = f"""Summarize the following conversation turns concisely. Preserve:
- Specific ticker names and financial figures mentioned
- Questions asked and conclusions reached
- Any follow-up threads the user indicated interest in

Do NOT summarize themes — preserve specific facts and numbers.

Conversation:
{conversation_text}

Summary:"""

    api_key = os.environ.get("GOLDMINE_ANTHROPIC_API_KEY", "")
    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model=model,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    summary = response.content[0].text.strip()
    cost = await calculate_cost(model, response.usage.input_tokens, response.usage.output_tokens)

    emit_cost_event(
        mode="mode_2",
        component="session_compressor",
        model=model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        cost_usd=cost,
        session_id=session_id,
        user_id=user_id,
    )

    # Update session
    new_covered = max(covered, len(all_msgs) - 8)
    async with get_conn() as conn:
        await conn.execute(
            """UPDATE sessions
               SET rolling_summary = $1, summary_covers_through = $2, updated_at = NOW()
               WHERE id = $3""",
            summary, new_covered, session_id,
        )


async def auto_title_conversation(
    conversation_id: str,
    first_question: str,
    first_answer: str,
    user_id: str | None = None,
) -> str | None:
    """Generate a 4-6 word title for a conversation after first exchange."""
    config = await get_model_config("session_compressor")
    model = config["model"]

    prompt = f"""Generate a concise 4-6 word title for this research conversation. Return ONLY the title, nothing else.

Question: {first_question[:200]}
Answer: {first_answer[:300]}

Title:"""

    api_key = os.environ.get("GOLDMINE_ANTHROPIC_API_KEY", "")
    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model=model,
        max_tokens=32,
        messages=[{"role": "user", "content": prompt}],
    )

    title = response.content[0].text.strip().strip('"')
    cost = await calculate_cost(model, response.usage.input_tokens, response.usage.output_tokens)

    emit_cost_event(
        mode="mode_2",
        component="session_compressor",
        model=model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        cost_usd=cost,
        session_id=None,
        user_id=user_id,
    )

    async with get_conn() as conn:
        await conn.execute(
            "UPDATE conversations SET title = $1, updated_at = NOW() WHERE id = $2",
            title, conversation_id,
        )

    return title


async def list_conversations(
    user_id: str,
    limit: int = 50,
    offset: int = 0,
    ticker: str | None = None,
    search: str | None = None,
) -> list[dict]:
    """List user's conversations with tickers aggregated from messages."""
    conditions = ["c.user_id = $1"]
    params: list = [user_id]
    idx = 2

    if ticker:
        # Filter by tickers found in messages, not just conversation-level ticker_context
        conditions.append(
            f"""EXISTS (
                SELECT 1 FROM messages m
                JOIN sessions s ON m.session_id = s.id
                WHERE s.conversation_id = c.id
                AND ${idx} = ANY(m.tickers_referenced)
            )"""
        )
        params.append(ticker)
        idx += 1

    if search:
        # Search both title and message content
        conditions.append(
            f"""(c.title ILIKE ${idx} OR EXISTS (
                SELECT 1 FROM messages m
                JOIN sessions s ON m.session_id = s.id
                WHERE s.conversation_id = c.id
                AND m.content ILIKE ${idx}
            ))"""
        )
        params.append(f"%{search}%")
        idx += 1

    where = " AND ".join(conditions)

    async with get_conn() as conn:
        rows = await conn.fetch(
            f"""SELECT c.id, c.title, c.ticker_context, c.updated_at, c.origin_path,
                       (SELECT COUNT(*) FROM sessions s WHERE s.conversation_id = c.id) as session_count,
                       EXISTS(SELECT 1 FROM conversation_shares cs WHERE cs.conversation_id = c.id) as is_shared,
                       (SELECT content FROM messages m
                        JOIN sessions s ON m.session_id = s.id
                        WHERE s.conversation_id = c.id AND m.role = 'user'
                        ORDER BY m.created_at LIMIT 1) as first_message,
                       (SELECT array_agg(DISTINCT ticker ORDER BY ticker)
                        FROM (
                            SELECT unnest(m.tickers_referenced) as ticker
                            FROM messages m
                            JOIN sessions s ON m.session_id = s.id
                            WHERE s.conversation_id = c.id
                            AND m.tickers_referenced IS NOT NULL
                        ) t) as tickers_mentioned
                FROM conversations c
                WHERE {where}
                AND c.is_archived = FALSE
                ORDER BY c.updated_at DESC
                LIMIT ${idx} OFFSET ${idx + 1}""",
            *params, limit, offset,
        )

    return [
        {
            "id": str(r["id"]),
            "title": r["title"],
            "ticker_context": r["tickers_mentioned"] or r["ticker_context"] or [],
            "session_count": r["session_count"],
            "last_active": r["updated_at"],
            "is_shared": r["is_shared"],
            "first_message": r["first_message"],
            "origin_path": r["origin_path"],
        }
        for r in rows
    ]
