"""DS-03: FastAPI endpoints for Mode 2 API.

All endpoints under /api/v1/ as specified in the architecture.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from .classifier import classify_query
from .ticker_resolver import resolve_tickers
from .generator import generate_response
from .steps import StepCollector
from .sessions import (
    create_conversation,
    create_session,
    get_session,
    get_session_history,
    get_rolling_summary,
    save_user_message,
    maybe_compress_session,
    auto_title_conversation,
    list_conversations,
    set_conversation_visibility,
    get_visible_conversations,
)
from .qa_library import submit_feedback
from .sharing import share_conversation, share_insight, get_shared_conversations
from .db import get_conn
from .models import (
    BugReportRequest,
    BugReportResponse,
    BugReportSummary,
    ChatMessageRequest,
    CreateConversationRequest,
    CreateConversationResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    CreateInsightRequest,
    CreateTickerListRequest,
    ConversationDetail,
    ConversationSummary,
    FeedbackRequest,
    FeedbackResponse,
    FeatureRequestAck,
    RenameConversationRequest,
    InsightSummary,
    SessionMessage,
    SessionResponse,
    ShareRequest,
    TickerList,
    CostSummary,
    ModelConfigEntry,
    UpdateModelRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["mode2"])


def _get_user_id(request: Request) -> str:
    """Extract user ID from authenticated request."""
    user = getattr(request.state, "user", None)
    if user and hasattr(user, "username"):
        return user.username
    return "anonymous"


# ---------------------------------------------------------------------------
# Chat endpoints
# ---------------------------------------------------------------------------
@router.post("/chat/message")
async def chat_message(request: Request, body: ChatMessageRequest):
    """Main chat endpoint — streams response via SSE."""
    user_id = _get_user_id(request)

    # Handle /request slash command
    if body.content.strip().startswith("/request"):
        return await _handle_feature_request(body, user_id)

    # Save user message
    user_msg_id = str(uuid.uuid4())
    await save_user_message(body.session_id, user_id, body.content, user_msg_id)

    # Generate assistant message ID
    assistant_msg_id = str(uuid.uuid4())

    async def event_stream():
        try:
            steps = StepCollector()

            # WF-06: Classify query
            history = await get_session_history(body.session_id)
            classified = await classify_query(
                body.content,
                history=history,
                user_id=user_id,
                session_id=body.session_id,
                message_id=assistant_msg_id,
                steps=steps,
            )

            # Emit classify steps
            for step in steps.drain():
                yield f"data: {json.dumps(step)}\n\n"

            # Inject context tickers if provided
            if body.context_tickers:
                for t in body.context_tickers:
                    if t not in classified.tickers:
                        classified.tickers.append(t)

            # WF-07: Resolve tickers
            t0 = time.time()
            universe = await resolve_tickers(classified, user_id=user_id)
            resolve_ms = int((time.time() - t0) * 1000)
            ticker_str = ", ".join(universe.tickers[:5]) + ("..." if len(universe.tickers) > 5 else "")
            yield f"data: {json.dumps({'type': 'step', 'label': f'Resolving tickers: {ticker_str}' if universe.tickers else 'Resolving tickers', 'detail': 'Ticker lookup and list expansion', 'source': 'supabase', 'model': None, 'cost_usd': 0.0, 'duration_ms': resolve_ms, 'result_summary': f'{len(universe.tickers)} tickers'})}\n\n"

            # WF-08/09: Agentic retrieval + generation (streaming)
            rolling_summary = await get_rolling_summary(body.session_id)

            async for event in generate_response(
                body.content, classified, universe,
                history=history,
                rolling_summary=rolling_summary,
                session_id=body.session_id,
                message_id=assistant_msg_id,
                user_id=user_id,
                steps=steps,
            ):
                yield f"data: {json.dumps(event)}\n\n"

            # WF-10: Async compression check (fire-and-forget)
            asyncio.create_task(
                maybe_compress_session(body.session_id, user_id)
            )

            # Auto-title conversation if this is the first exchange
            session = await get_session(body.session_id)
            if session and session["turn_count"] <= 2:
                # Check if conversation needs title
                async with get_conn() as conn:
                    conv = await conn.fetchrow(
                        "SELECT title FROM conversations WHERE id = $1",
                        body.conversation_id,
                    )
                    if conv and not conv["title"]:
                        msgs = session["messages"]
                        if len(msgs) >= 2:
                            title = await auto_title_conversation(
                                body.conversation_id,
                                msgs[-2]["content"],
                                msgs[-1]["content"],
                                user_id,
                            )
                            if title:
                                yield f"data: {json.dumps({'type': 'metadata', 'title': title})}\n\n"

        except Exception as e:
            logger.exception("Error in chat stream")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _handle_feature_request(body: ChatMessageRequest, user_id: str) -> FeatureRequestAck:
    """Handle /request slash command."""
    request_text = body.content.strip().removeprefix("/request").strip()
    request_id = str(uuid.uuid4())

    async with get_conn() as conn:
        await conn.execute(
            """INSERT INTO feature_requests (id, user_id, session_id, request_text)
               VALUES ($1, $2, $3, $4)""",
            request_id, user_id, body.session_id, request_text,
        )

    return FeatureRequestAck(
        message=f"Feature request received. We'll review it shortly.",
        request_id=request_id,
    )


@router.post("/chat/session", status_code=201)
async def create_chat_session(
    request: Request, body: CreateSessionRequest
) -> CreateSessionResponse:
    """Create a new session in a conversation."""
    user_id = _get_user_id(request)
    session_id = await create_session(body.conversation_id, user_id)
    return CreateSessionResponse(
        session_id=session_id,
        conversation_id=body.conversation_id,
        created_at=datetime.utcnow(),
    )


@router.get("/chat/session/{session_id}")
async def get_chat_session(session_id: str) -> SessionResponse:
    """Get session with full message history."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return SessionResponse(
        session_id=session["session_id"],
        conversation_id=session["conversation_id"],
        messages=[
            {
                "message_id": m["message_id"],
                "role": m["role"],
                "content": m["content"],
                "query_type": m.get("query_type"),
                "tickers_referenced": m.get("tickers_referenced", []),
                "source_chunks": m.get("source_chunks", []),
                "feedback": None,
                "created_at": m["created_at"],
            }
            for m in session["messages"]
        ],
        turn_count=session["turn_count"],
        created_at=session["created_at"],
    )


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(request: Request, session_id: str) -> list[dict]:
    """Return messages for a session — lightweight endpoint for pack page."""
    session = await get_session(session_id)
    if not session:
        return []
    return [
        {
            "id": m["message_id"],
            "role": m["role"],
            "content": m["content"],
            "query_type": m.get("query_type"),
            "tickers_referenced": m.get("tickers_referenced", []),
            "created_at": str(m.get("created_at", "")),
        }
        for m in session.get("messages", [])
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]


# ---------------------------------------------------------------------------
# Conversation visibility & listing
# ---------------------------------------------------------------------------
@router.patch("/conversations/{conversation_id}/visibility")
async def update_conversation_visibility(
    request: Request, conversation_id: str, body: dict
):
    """Update conversation visibility (private/public). Owner only."""
    user_id = _get_user_id(request)
    visibility = body.get("visibility", "")
    if visibility not in ("private", "public"):
        raise HTTPException(400, "visibility must be 'private' or 'public'")
    ok = await set_conversation_visibility(conversation_id, visibility, user_id)
    if not ok:
        raise HTTPException(404, "Conversation not found or not owned by you")
    return {"status": "updated", "visibility": visibility}


@router.get("/visible-conversations")
async def list_visible_conversations(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List conversations visible to current user (own + public from others)."""
    user_id = _get_user_id(request)
    user = getattr(request.state, "user", None)
    is_admin = getattr(user, "is_admin", False) if user else False
    conversations = await get_visible_conversations(
        user_id, is_admin=is_admin,
        limit=limit, offset=offset,
    )
    return conversations


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------
@router.post("/messages/{message_id}/feedback", status_code=201)
async def post_feedback(
    request: Request, message_id: str, body: FeedbackRequest
) -> FeedbackResponse:
    """Submit feedback on a message."""
    user_id = _get_user_id(request)
    result = await submit_feedback(
        message_id, body.feedback_type, body.edited_content, user_id
    )
    return FeedbackResponse(**result)


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------
@router.get("/conversations")
async def get_conversations(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ticker: str | None = None,
    search: str | None = None,
) -> list[ConversationSummary]:
    """List user's conversations."""
    user_id = _get_user_id(request)
    convs = await list_conversations(user_id, limit, offset, ticker, search)
    return [ConversationSummary(**c) for c in convs]


@router.post("/conversations", status_code=201)
async def create_new_conversation(
    request: Request, body: CreateConversationRequest
) -> CreateConversationResponse:
    """Create a new conversation."""
    user_id = _get_user_id(request)
    result = await create_conversation(user_id, body.title, body.ticker_context, body.origin_path)
    return CreateConversationResponse(
        id=result["conversation_id"],
        title=body.title,
        ticker_context=body.ticker_context,
        created_at=datetime.utcnow(),
        origin_path=body.origin_path,
    )


@router.patch("/conversations/{conversation_id}")
async def rename_conversation(
    request: Request, conversation_id: str, body: RenameConversationRequest
):
    """Rename a conversation."""
    user_id = _get_user_id(request)
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE conversations SET title = $1, updated_at = NOW() WHERE id = $2 AND user_id = $3",
            body.title, conversation_id, user_id,
        )
    return {"status": "updated", "title": body.title}


@router.get("/conversations/{conversation_id}")
async def get_conversation_detail(
    request: Request, conversation_id: str
) -> ConversationDetail:
    """Get conversation with all messages across sessions."""
    user_id = _get_user_id(request)

    async with get_conn() as conn:
        conv = await conn.fetchrow(
            """SELECT id, title, ticker_context, visibility, created_at, updated_at, origin_path,
                      EXISTS(SELECT 1 FROM conversation_shares cs WHERE cs.conversation_id = c.id) as is_shared
               FROM conversations c
               WHERE id = $1 AND user_id = $2""",
            conversation_id, user_id,
        )
        if not conv:
            raise HTTPException(404, "Conversation not found")

        messages = await conn.fetch(
            """SELECT m.id, m.role, m.content, m.query_type,
                      m.tickers_referenced, m.source_chunks, m.created_at
               FROM messages m
               JOIN sessions s ON m.session_id = s.id
               WHERE s.conversation_id = $1
               ORDER BY m.created_at""",
            conversation_id,
        )

    return ConversationDetail(
        id=str(conv["id"]),
        title=conv["title"],
        ticker_context=conv["ticker_context"] or [],
        messages=[
            SessionMessage(
                message_id=str(m["id"]),
                role=m["role"],
                content=m["content"],
                query_type=m["query_type"],
                tickers_referenced=m["tickers_referenced"] or [],
                source_chunks=(
                    m["source_chunks"] if isinstance(m["source_chunks"], list)
                    else json.loads(m["source_chunks"]) if m["source_chunks"]
                    else []
                ),
                feedback=None,
                created_at=m["created_at"],
            )
            for m in messages
        ],
        turn_count=len(messages),
        is_shared=conv["is_shared"],
        visibility=conv["visibility"],
        created_at=conv["created_at"],
        last_active=conv["updated_at"],
        origin_path=conv["origin_path"],
    )


@router.post("/conversations/{conversation_id}/share")
async def share_conv(
    request: Request, conversation_id: str, body: ShareRequest
):
    """Share a conversation."""
    user_id = _get_user_id(request)
    share_id = await share_conversation(
        conversation_id, user_id, body.share_with_user_id, body.share_with_team
    )
    return {"share_id": share_id}


@router.get("/conversations/search")
async def search_conversations(
    request: Request,
    q: str = Query(..., min_length=2),
    limit: int = Query(20, ge=1, le=100),
):
    """Semantic search across conversation history."""
    user_id = _get_user_id(request)

    # Embed the search query
    from .retrieval import _embed_query
    query_embedding = await _embed_query(q, user_id=user_id)
    emb_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

    async with get_conn() as conn:
        rows = await conn.fetch(
            """SELECT m.id as message_id, m.content, m.created_at,
                      c.id as conversation_id, c.title as conversation_title,
                      1 - (m.content_embedding <=> $1::vector) AS similarity
               FROM messages m
               JOIN sessions s ON m.session_id = s.id
               JOIN conversations c ON s.conversation_id = c.id
               WHERE c.user_id = $2
               AND m.content_embedding IS NOT NULL
               AND 1 - (m.content_embedding <=> $1::vector) > 0.7
               ORDER BY similarity DESC
               LIMIT $3""",
            emb_str, user_id, limit,
        )

    return [
        {
            "message_id": str(r["message_id"]),
            "conversation_id": str(r["conversation_id"]),
            "conversation_title": r["conversation_title"],
            "excerpt": r["content"][:300],
            "similarity_score": float(r["similarity"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------
@router.get("/insights")
async def get_insights(
    request: Request,
    ticker: str | None = None,
    tag: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[InsightSummary]:
    """Get saved insights."""
    user_id = _get_user_id(request)

    conditions = ["i.user_id = $1"]
    params: list = [user_id]
    idx = 2

    if ticker:
        conditions.append(f"${idx} = ANY(i.ticker_context)")
        params.append(ticker)
        idx += 1
    if tag:
        conditions.append(f"${idx} = ANY(i.tags)")
        params.append(tag)
        idx += 1

    where = " AND ".join(conditions)

    async with get_conn() as conn:
        rows = await conn.fetch(
            f"""SELECT i.id, i.title, i.content, i.ticker_context, i.tags, i.created_at,
                       EXISTS(SELECT 1 FROM insight_shares s WHERE s.insight_id = i.id) as is_shared
                FROM insights i
                WHERE {where}
                ORDER BY i.created_at DESC
                LIMIT ${idx} OFFSET ${idx + 1}""",
            *params, limit, offset,
        )

    return [
        InsightSummary(
            insight_id=str(r["id"]),
            title=r["title"],
            content=r["content"],
            ticker_context=r["ticker_context"] or [],
            tags=r["tags"] or [],
            created_at=r["created_at"],
            is_shared=r["is_shared"],
        )
        for r in rows
    ]


@router.post("/insights", status_code=201)
async def create_insight(request: Request, body: CreateInsightRequest) -> InsightSummary:
    """Save an insight from a session."""
    user_id = _get_user_id(request)
    insight_id = str(uuid.uuid4())

    async with get_conn() as conn:
        await conn.execute(
            """INSERT INTO insights
               (id, user_id, message_id, session_id, title, content, ticker_context, tags)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
            insight_id, user_id, body.message_id, body.session_id,
            body.title, body.content, body.ticker_context, body.tags,
        )

    return InsightSummary(
        insight_id=insight_id,
        title=body.title,
        content=body.content,
        ticker_context=body.ticker_context,
        tags=body.tags,
        created_at=datetime.utcnow(),
    )


@router.post("/insights/{insight_id}/share")
async def share_ins(request: Request, insight_id: str, body: ShareRequest):
    """Share an insight."""
    user_id = _get_user_id(request)
    share_id = await share_insight(
        insight_id, user_id, body.share_with_user_id, body.share_with_team
    )
    return {"share_id": share_id}


# ---------------------------------------------------------------------------
# Ticker Lists
# ---------------------------------------------------------------------------
@router.get("/lists")
async def get_ticker_lists(request: Request) -> list[TickerList]:
    """Get all user's ticker lists."""
    user_id = _get_user_id(request)
    async with get_conn() as conn:
        rows = await conn.fetch(
            "SELECT list_name, tickers FROM user_ticker_lists WHERE user_id = $1",
            user_id,
        )
    return [
        TickerList(
            list_name=r["list_name"],
            tickers=r["tickers"] or [],
            ticker_count=len(r["tickers"] or []),
        )
        for r in rows
    ]


@router.post("/lists", status_code=201)
async def create_ticker_list(request: Request, body: CreateTickerListRequest) -> TickerList:
    """Create or update a ticker list."""
    user_id = _get_user_id(request)
    async with get_conn() as conn:
        await conn.execute(
            """INSERT INTO user_ticker_lists (user_id, list_name, tickers)
               VALUES ($1, $2, $3)
               ON CONFLICT (user_id, list_name)
               DO UPDATE SET tickers = $3, updated_at = NOW()""",
            user_id, body.list_name, body.tickers,
        )
    return TickerList(
        list_name=body.list_name,
        tickers=body.tickers,
        ticker_count=len(body.tickers),
    )


@router.delete("/lists/{list_name}", status_code=204)
async def delete_ticker_list(request: Request, list_name: str):
    """Delete a ticker list."""
    user_id = _get_user_id(request)
    async with get_conn() as conn:
        await conn.execute(
            "DELETE FROM user_ticker_lists WHERE user_id = $1 AND list_name = $2",
            user_id, list_name,
        )


# ---------------------------------------------------------------------------
# Bug Reports
# ---------------------------------------------------------------------------
@router.post("/bug-reports", status_code=201)
async def create_bug_report(
    request: Request, body: BugReportRequest
) -> BugReportResponse:
    """Submit a bug report for a bad LLM response."""
    user_id = _get_user_id(request)
    bug_id = str(uuid.uuid4())

    async with get_conn() as conn:
        await conn.execute(
            """INSERT INTO llm_bug_reports
               (id, conversation_id, session_id, message_id, user_id, category,
                description, user_query, llm_response, error_message,
                tickers_referenced, query_type)
               VALUES ($1, $2::uuid, $3::uuid, $4::uuid, $5, $6, $7, $8, $9, $10, $11, $12)""",
            bug_id,
            body.conversation_id,
            body.session_id,
            body.message_id,
            user_id,
            body.category,
            body.description,
            body.user_query,
            body.llm_response,
            body.error_message,
            body.tickers_referenced,
            body.query_type,
        )

    logger.info("bug_report_created", bug_id=bug_id, category=body.category, user_id=user_id)
    return BugReportResponse(bug_id=bug_id)


@router.get("/bug-reports")
async def list_bug_reports(
    status: str | None = None,
    category: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[BugReportSummary]:
    """List bug reports (admin)."""
    conditions: list[str] = []
    params: list = []
    idx = 1

    if status:
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1
    if category:
        conditions.append(f"category = ${idx}")
        params.append(category)
        idx += 1

    where = " WHERE " + " AND ".join(conditions) if conditions else ""

    async with get_conn() as conn:
        rows = await conn.fetch(
            f"""SELECT id, category, description, user_query, llm_response,
                       error_message, tickers_referenced, query_type, status,
                       resolution, user_id, created_at, resolved_at
                FROM llm_bug_reports{where}
                ORDER BY created_at DESC
                LIMIT ${idx} OFFSET ${idx + 1}""",
            *params, limit, offset,
        )

    return [
        BugReportSummary(
            id=str(r["id"]),
            category=r["category"],
            description=r["description"],
            user_query=r["user_query"],
            llm_response=r["llm_response"][:500],
            error_message=r["error_message"],
            tickers_referenced=r["tickers_referenced"] or [],
            query_type=r["query_type"],
            status=r["status"],
            resolution=r["resolution"],
            user_id=r["user_id"],
            created_at=r["created_at"],
            resolved_at=r["resolved_at"],
        )
        for r in rows
    ]


@router.patch("/bug-reports/{bug_id}")
async def update_bug_report(
    bug_id: str,
    status: str | None = None,
    resolution: str | None = None,
):
    """Update a bug report status/resolution."""
    updates: list[str] = []
    params: list = []
    idx = 1

    if status:
        updates.append(f"status = ${idx}")
        params.append(status)
        idx += 1
        if status == "resolved":
            updates.append("resolved_at = NOW()")
    if resolution is not None:
        updates.append(f"resolution = ${idx}")
        params.append(resolution)
        idx += 1

    if not updates:
        raise HTTPException(400, "No fields to update")

    params.append(bug_id)
    set_clause = ", ".join(updates)

    async with get_conn() as conn:
        await conn.execute(
            f"UPDATE llm_bug_reports SET {set_clause} WHERE id = ${idx}::uuid",
            *params,
        )
    return {"status": "updated"}


# ---------------------------------------------------------------------------
# Admin: Feature Requests
# ---------------------------------------------------------------------------
@router.get("/admin/feature-requests")
async def get_feature_requests(
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List all feature requests (admin only)."""
    conditions = []
    params: list = []
    idx = 1

    if status:
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1

    where = " AND ".join(conditions) if conditions else "TRUE"

    async with get_conn() as conn:
        rows = await conn.fetch(
            f"""SELECT id, user_id, session_id, request_text, status,
                       priority, admin_notes, created_at
                FROM feature_requests
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT ${idx} OFFSET ${idx + 1}""",
            *params, limit, offset,
        )

    return [dict(r) for r in rows]


@router.patch("/admin/feature-requests/{request_id}")
async def update_feature_request(request_id: str, status: str | None = None, priority: str | None = None, admin_notes: str | None = None):
    """Update a feature request."""
    updates = []
    params: list = []
    idx = 1

    if status:
        updates.append(f"status = ${idx}")
        params.append(status)
        idx += 1
    if priority:
        updates.append(f"priority = ${idx}")
        params.append(priority)
        idx += 1
    if admin_notes is not None:
        updates.append(f"admin_notes = ${idx}")
        params.append(admin_notes)
        idx += 1

    if not updates:
        raise HTTPException(400, "No fields to update")

    params.append(request_id)
    set_clause = ", ".join(updates)

    async with get_conn() as conn:
        await conn.execute(
            f"UPDATE feature_requests SET {set_clause}, updated_at = NOW() WHERE id = ${idx}",
            *params,
        )
    return {"status": "updated"}


# ---------------------------------------------------------------------------
# Admin: Costs
# ---------------------------------------------------------------------------
@router.get("/admin/costs/summary")
async def get_cost_summary(
    request: Request,
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    group_by: str = Query("component"),
) -> CostSummary:
    """Get cost summary."""
    conditions = []
    params: list = []
    idx = 1

    if from_date:
        conditions.append(f"created_at >= ${idx}::timestamp")
        params.append(from_date)
        idx += 1
    if to_date:
        conditions.append(f"created_at <= ${idx}::timestamp")
        params.append(to_date)
        idx += 1

    where = " AND ".join(conditions) if conditions else "TRUE"

    valid_groups = {"component", "mode", "model", "query_type", "user_id"}
    if group_by not in valid_groups:
        group_by = "component"

    async with get_conn() as conn:
        total_row = await conn.fetchrow(
            f"SELECT COALESCE(SUM(cost_usd), 0) as total FROM api_cost_events WHERE {where}",
            *params,
        )

        breakdown_rows = await conn.fetch(
            f"""SELECT {group_by}, COUNT(*) as calls,
                       SUM(cost_usd) as total_cost,
                       SUM(input_tokens) as total_input_tokens,
                       SUM(output_tokens) as total_output_tokens
                FROM api_cost_events
                WHERE {where}
                GROUP BY {group_by}
                ORDER BY total_cost DESC""",
            *params,
        )

    return CostSummary(
        total_cost_usd=float(total_row["total"]),
        period={"from": from_date or "all", "to": to_date or "now"},
        breakdown=[dict(r) for r in breakdown_rows],
    )


# ---------------------------------------------------------------------------
# Admin: Models
# ---------------------------------------------------------------------------
@router.get("/admin/models")
async def get_models() -> list[ModelConfigEntry]:
    """Get current model configuration."""
    async with get_conn() as conn:
        rows = await conn.fetch(
            "SELECT component, model, provider, previous_model, switched_at FROM model_config ORDER BY component"
        )
    return [
        ModelConfigEntry(
            component=r["component"],
            model=r["model"],
            provider=r["provider"],
            previous_model=r["previous_model"],
            switched_at=r["switched_at"],
        )
        for r in rows
    ]


@router.put("/admin/models/{component}")
async def update_model(component: str, body: UpdateModelRequest):
    """Update model assignment for a component."""
    async with get_conn() as conn:
        await conn.execute(
            """UPDATE model_config
               SET previous_model = model,
                   model = $1,
                   provider = $2,
                   switched_at = NOW(),
                   updated_at = NOW()
               WHERE component = $3""",
            body.model, body.provider, component,
        )
    return {"status": "updated", "component": component, "model": body.model}
