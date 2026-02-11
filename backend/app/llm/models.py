from __future__ import annotations

from pydantic import BaseModel, Field


class LLMQueryRequest(BaseModel):
    query: str
    entity_type: str
    entity_id: str


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
