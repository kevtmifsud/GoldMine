"""WF-11: Q&A Library Management.

Captures validated answers as institutional memory. Surfaced to future
analysts asking similar questions.
"""
from __future__ import annotations

import json
import logging
import os
import uuid

from openai import OpenAI
from dotenv import load_dotenv

from .cost import get_model_config, calculate_cost, emit_cost_event
from .db import get_conn

logger = logging.getLogger(__name__)

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))


async def promote_to_library(
    message_id: str,
    feedback_type: str,
    edited_content: str | None = None,
    user_id: str | None = None,
) -> str | None:
    """Promote a message to Q&A library on positive feedback.

    Returns library entry ID if promoted, None otherwise.
    """
    if feedback_type not in ("thumbs_up", "edited"):
        return None

    async with get_conn() as conn:
        # Get the original message and the user question before it
        msg = await conn.fetchrow(
            """SELECT m.id, m.session_id, m.content, m.query_type,
                      m.tickers_referenced, m.source_chunks
               FROM messages m WHERE m.id = $1""",
            message_id,
        )
        if not msg:
            return None

        # Find the user question that preceded this assistant message
        user_msg = await conn.fetchrow(
            """SELECT content FROM messages
               WHERE session_id = $1 AND role = 'user' AND created_at < (
                   SELECT created_at FROM messages WHERE id = $2
               )
               ORDER BY created_at DESC LIMIT 1""",
            msg["session_id"], message_id,
        )

    if not user_msg:
        return None

    question = user_msg["content"]
    answer = edited_content if edited_content else msg["content"]
    validation_type = "edited_approved" if feedback_type == "edited" else "thumbs_up"
    validation_weight = 1.5 if feedback_type == "edited" else 1.0

    # Embed the question
    config = await get_model_config("qa_library_embedder")
    model = config["model"]

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
    response = client.embeddings.create(model=model, input=[question], dimensions=1536)
    embedding = response.data[0].embedding
    tokens = response.usage.total_tokens

    cost = await calculate_cost(model, tokens)
    emit_cost_event(
        mode="mode_2",
        component="qa_library_embedder",
        model=model,
        input_tokens=tokens,
        cost_usd=cost,
        user_id=user_id,
    )

    # Insert into qa_library
    entry_id = str(uuid.uuid4())
    emb_str = "[" + ",".join(str(v) for v in embedding) + "]"

    # Extract fiscal periods from source chunks
    fiscal_periods = []
    if msg["source_chunks"]:
        try:
            chunks = json.loads(msg["source_chunks"]) if isinstance(msg["source_chunks"], str) else msg["source_chunks"]
            fiscal_periods = list({c.get("fiscal_period", "") for c in chunks if c.get("fiscal_period")})
        except (json.JSONDecodeError, TypeError):
            pass

    async with get_conn() as conn:
        await conn.execute(
            """INSERT INTO qa_library
               (id, question, answer, question_embedding, source_chunks,
                tickers_referenced, query_type, fiscal_periods,
                validation_type, validation_weight, created_by)
               VALUES ($1, $2, $3, $4::vector, $5, $6, $7, $8, $9, $10, $11)""",
            entry_id, question, answer, emb_str,
            json.dumps(msg["source_chunks"] if msg["source_chunks"] else []),
            msg["tickers_referenced"] or [],
            msg["query_type"],
            fiscal_periods,
            validation_type,
            validation_weight,
            user_id,
        )

    return entry_id


async def submit_feedback(
    message_id: str,
    feedback_type: str,
    edited_content: str | None = None,
    user_id: str | None = None,
) -> dict:
    """Process feedback on a message. Returns feedback_id and whether library entry was created."""
    feedback_id = str(uuid.uuid4())

    async with get_conn() as conn:
        await conn.execute(
            """INSERT INTO message_feedback (id, message_id, user_id, feedback_type, edited_content)
               VALUES ($1, $2, $3, $4, $5)""",
            feedback_id, message_id, user_id, feedback_type, edited_content,
        )

    # Promote to Q&A library on positive feedback
    library_entry_id = None
    if feedback_type in ("thumbs_up", "edited"):
        library_entry_id = await promote_to_library(
            message_id, feedback_type, edited_content, user_id
        )

    return {
        "feedback_id": feedback_id,
        "qa_library_entry_created": library_entry_id is not None,
    }
