"""Pydantic models for Mode 2 API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# WF-06: Query Classification
# ---------------------------------------------------------------------------
QueryType = Literal[
    "single_ticker_qualitative",
    "single_ticker_quantitative",
    "cross_ticker",
    "screening",
    "trend_analysis",
]


class ClassifiedQuery(BaseModel):
    query_type: QueryType
    tickers: list[str] = Field(default_factory=list)
    list_references: list[str] = Field(default_factory=list)
    fiscal_periods: list[str] = Field(default_factory=list)
    topic: str = ""
    needs_structured_data: bool = False
    needs_vector_search: bool = True
    section_type_hint: str | None = None
    time_range_quarters: int | None = None


# ---------------------------------------------------------------------------
# WF-07: Ticker Resolution
# ---------------------------------------------------------------------------
class ResolvedUniverse(BaseModel):
    tickers: list[str] = Field(default_factory=list)
    resolution_sources: dict[str, str] = Field(default_factory=dict)
    was_truncated: bool = False
    original_list_references: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# WF-08: Retrieval Context
# ---------------------------------------------------------------------------
class ChunkResult(BaseModel):
    chunk_id: str | None = None
    document_id: str | None = None
    ticker: str
    document_type: str
    fiscal_period: str
    section_name: str
    section_type: str
    chunk_text: str
    word_count: int = 0
    similarity: float = 0.0


class QALibraryEntry(BaseModel):
    id: str
    question: str
    answer: str
    tickers_referenced: list[str] = Field(default_factory=list)
    query_type: str | None = None
    fiscal_periods: list[str] = Field(default_factory=list)
    validation_type: str | None = None
    validation_weight: float = 1.0
    similarity: float = 0.0


class RetrievalContext(BaseModel):
    query_type: str
    structured_data: list[dict[str, Any]] | None = None
    chunks: list[ChunkResult] = Field(default_factory=list)
    qa_library_hits: list[QALibraryEntry] = Field(default_factory=list)
    cache_hit: bool = False
    total_chunks_retrieved: int = 0
    total_input_tokens_estimate: int = 0


# ---------------------------------------------------------------------------
# DS-03: API Request / Response Models
# ---------------------------------------------------------------------------

# -- Chat --
class ChatMessageRequest(BaseModel):
    session_id: str
    conversation_id: str
    content: str
    context_tickers: list[str] = Field(default_factory=list)


class CreateSessionRequest(BaseModel):
    conversation_id: str


class CreateSessionResponse(BaseModel):
    session_id: str
    conversation_id: str
    created_at: datetime


class SessionMessage(BaseModel):
    message_id: str
    role: str
    content: str
    query_type: str | None = None
    tickers_referenced: list[str] = Field(default_factory=list)
    source_chunks: list[dict[str, Any]] = Field(default_factory=list)
    feedback: dict[str, Any] | None = None
    created_at: datetime


class SessionResponse(BaseModel):
    session_id: str
    conversation_id: str
    messages: list[SessionMessage] = Field(default_factory=list)
    turn_count: int = 0
    created_at: datetime


# -- Conversations --
class ConversationSummary(BaseModel):
    id: str
    title: str | None = None
    ticker_context: list[str] = Field(default_factory=list)
    session_count: int = 0
    last_active: datetime | None = None
    is_shared: bool = False
    first_message: str | None = None


class ConversationDetail(BaseModel):
    id: str
    title: str | None = None
    ticker_context: list[str] = Field(default_factory=list)
    messages: list[SessionMessage] = Field(default_factory=list)
    turn_count: int = 0
    is_shared: bool = False
    created_at: datetime
    last_active: datetime | None = None


class CreateConversationRequest(BaseModel):
    title: str | None = None
    ticker_context: list[str] = Field(default_factory=list)


class CreateConversationResponse(BaseModel):
    id: str
    title: str | None = None
    ticker_context: list[str] = Field(default_factory=list)
    created_at: datetime


class ShareRequest(BaseModel):
    share_with_user_id: str | None = None
    share_with_team: bool = False


# -- Feedback --
class FeedbackRequest(BaseModel):
    feedback_type: Literal["thumbs_up", "thumbs_down", "edited", "flagged"]
    edited_content: str | None = None


class FeedbackResponse(BaseModel):
    feedback_id: str
    qa_library_entry_created: bool = False


# -- Insights --
class InsightSummary(BaseModel):
    insight_id: str
    title: str
    content: str
    ticker_context: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    is_shared: bool = False


class CreateInsightRequest(BaseModel):
    message_id: str
    session_id: str
    title: str
    content: str
    ticker_context: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


# -- Ticker Lists --
class TickerList(BaseModel):
    list_name: str
    tickers: list[str] = Field(default_factory=list)
    ticker_count: int = 0


class CreateTickerListRequest(BaseModel):
    list_name: str
    tickers: list[str]


# -- Feature Requests --
class FeatureRequestAck(BaseModel):
    type: str = "feature_request_received"
    message: str
    request_id: str


# -- Admin --
class CostSummary(BaseModel):
    total_cost_usd: float
    period: dict[str, str]
    breakdown: list[dict[str, Any]] = Field(default_factory=list)


class ModelConfigEntry(BaseModel):
    component: str
    model: str
    provider: str
    previous_model: str | None = None
    switched_at: datetime | None = None


class UpdateModelRequest(BaseModel):
    model: str
    provider: str


# -- Error --
class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail
