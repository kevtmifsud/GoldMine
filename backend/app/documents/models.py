from __future__ import annotations

from pydantic import BaseModel, Field


class EntityAssociation(BaseModel):
    entity_type: str
    entity_id: str


class DocumentChunk(BaseModel):
    chunk_id: str
    file_id: str
    chunk_index: int
    text: str
    char_start: int
    char_end: int


class DocumentRecord(BaseModel):
    file_id: str
    filename: str
    title: str
    doc_type: str
    mime_type: str
    date: str
    description: str
    entities: list[EntityAssociation] = Field(default_factory=list)
    chunks: list[DocumentChunk] = Field(default_factory=list)
    indexed_at: str = ""


class DocumentSearchResult(BaseModel):
    file_id: str
    filename: str
    title: str
    doc_type: str
    date: str
    description: str
    entities: list[EntityAssociation] = Field(default_factory=list)
    matching_chunks: list[DocumentChunk] = Field(default_factory=list)
    score: float = 0.0


class DocumentListItem(BaseModel):
    file_id: str
    filename: str
    title: str
    doc_type: str
    date: str
    description: str
    entities: list[EntityAssociation] = Field(default_factory=list)
    chunk_count: int = 0
    indexed_at: str = ""
