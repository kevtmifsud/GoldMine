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


_INVALID_SUMMARY_PHRASES = [
    "no data available",
    "not available",
    "not yet ingested",
    "data management interface",
    "no estimates",
    "no results found",
    "empty",
    "not in the database",
    "not currently available",
]


def _validate_summary(summary: str) -> str:
    """Strip sentences containing data-availability noise from summary."""
    sentences = summary.split(". ")
    valid = [
        s for s in sentences
        if not any(phrase in s.lower() for phrase in _INVALID_SUMMARY_PHRASES)
    ]
    stripped = len(sentences) - len(valid)
    if stripped > 0:
        logger.warning(
            "compression_quality_check: stripped %d sentences containing data availability statements",
            stripped,
        )
    return ". ".join(valid)


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
            """SELECT id, role, content FROM messages
               WHERE session_id = $1
               ORDER BY created_at""",
            session_id,
        )

    if not messages:
        return

    # Messages to summarize: from covered+1 to turn_count-4
    all_msgs = [{"id": str(m["id"]), "role": m["role"], "content": m["content"]} for m in messages]
    to_summarize = all_msgs[covered : max(covered, len(all_msgs) - 8)]

    if not to_summarize:
        return

    # Check for negatively-flagged messages in the compression window
    msg_ids = [m["id"] for m in to_summarize]
    flagged_ids: set[str] = set()
    async with get_conn() as conn:
        flagged_rows = await conn.fetch(
            """SELECT message_id, feedback_type
               FROM message_feedback
               WHERE message_id = ANY($1)
               AND feedback_type IN ('thumbs_down', 'flagged', 'edited')""",
            msg_ids,
        )
    flagged_ids = {str(r["message_id"]) for r in flagged_rows}

    # Build flagged-message notes for the compression prompt
    flagged_notes = ""
    if flagged_ids:
        notes = []
        for m in to_summarize:
            if m["id"] in flagged_ids and m["role"] == "assistant":
                notes.append(
                    f"NOTE: The assistant response (message {m['id']}) was marked "
                    f"incorrect by the user. Do NOT include that response's content "
                    f"in the summary. If the user provided a correction, include "
                    f"only the correction."
                )
        if notes:
            flagged_notes = "\n".join(notes) + "\n\n"

    # Call Haiku for compression
    config = await get_model_config("session_compressor")
    model = config["model"]

    conversation_text = "\n".join(
        f"{m['role']}: {m['content'][:500]}" for m in to_summarize
    )

    prompt = f"""{flagged_notes}Summarize the following conversation turns into a rolling summary.

INCLUDE — Always keep these:
- Tickers, sectors, and topics under research
- Questions asked and analytical themes
- Key verified findings from successful data retrieval (qualitative insights, not specific stale numbers)
- Analyst stated preferences (e.g. "prefers tables", "focus on margins")
- Follow-up items mentioned
- Workflow outputs that were reviewed and discussed

EXCLUDE — Remove these entirely:
- Transient data availability: any statement that data was unavailable, not found, empty, or not yet ingested. These change as the database is updated and must never be treated as permanent facts.
- User-reported incorrect responses: any response the user indicated was wrong, corrected, or disputed. If the user said "that's wrong" or provided a correction, exclude the original incorrect statement and include only the correction if it was factual.
- Stale time-sensitive figures: specific numeric values for things that change daily (prices, P&L amounts, market values, specific estimate values with a date). Include the topic but not the specific stale number. Instead of "AAPL market value was $594M as of March 20", write "Analyst reviewed AAPL portfolio position and P&L".
- Error messages and failures: API errors, database failures, timeout errors.
- Workflow execution status: "Earnings preview was generated", "Model was created successfully". The outputs are stored in the database. Include what was reviewed, not that it ran.

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
    summary = _validate_summary(summary)
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


async def set_conversation_visibility(
    conversation_id: str,
    visibility: str,
    user_id: str,
) -> bool:
    """Set visibility on a conversation. Only the owner can change it.
    Affects all sessions within that conversation.
    """
    if visibility not in ("private", "public"):
        raise ValueError(f"Invalid visibility: {visibility}")
    async with get_conn() as conn:
        result = await conn.execute(
            """UPDATE conversations SET visibility = $1, updated_at = NOW()
               WHERE id = $2 AND user_id = $3""",
            visibility, conversation_id, user_id,
        )
    return result == "UPDATE 1"


async def get_visible_conversations(
    user_id: str,
    is_admin: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Return conversations visible to this user.

    Rules:
    - Admin sees all conversations
    - Users see their own (any visibility)
    - Users see others' public conversations
    """
    if is_admin:
        where = "TRUE"
        params: list = [limit, offset]
        idx = 1
    else:
        where = "(c.user_id = $1 OR c.visibility = 'public')"
        params = [user_id, limit, offset]
        idx = 2

    async with get_conn() as conn:
        rows = await conn.fetch(
            f"""SELECT c.id, c.user_id, c.title, c.ticker_context,
                       c.visibility, c.is_archived, c.origin_path,
                       c.created_at, c.updated_at,
                       COUNT(s.id) as session_count,
                       MAX(s.updated_at) as last_active,
                       (SELECT content FROM messages m
                        JOIN sessions s2 ON m.session_id = s2.id
                        WHERE s2.conversation_id = c.id AND m.role = 'user'
                        ORDER BY m.created_at LIMIT 1) as first_message
                FROM conversations c
                LEFT JOIN sessions s ON s.conversation_id = c.id
                WHERE {where}
                AND c.is_archived = FALSE
                GROUP BY c.id
                ORDER BY COALESCE(MAX(s.updated_at), c.updated_at) DESC
                LIMIT ${idx} OFFSET ${idx + 1}""",
            *params,
        )

    return [
        {
            "id": str(r["id"]),
            "user_id": r["user_id"],
            "title": r["title"],
            "ticker_context": r["ticker_context"] or [],
            "visibility": r["visibility"],
            "session_count": r["session_count"],
            "last_active": r["last_active"] or r["updated_at"],
            "first_message": r["first_message"],
            "origin_path": r["origin_path"],
        }
        for r in rows
    ]


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
