from __future__ import annotations

from pydantic import BaseModel, Field


class ConversationMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class LLMQueryRequest(BaseModel):
    query: str
    entity_type: str
    entity_id: str
    conversation_history: list[ConversationMessage] = Field(default_factory=list)
    is_first_message: bool = True


class LLMSource(BaseModel):
    file_id: str
    filename: str
    chunk_index: int
    excerpt: str


class LLMQueryResponse(BaseModel):
    answer: str
    sources: list[LLMSource] = Field(default_factory=list)
    model: str = ""
    token_usage: dict[str, int] = Field(default_factory=dict)
