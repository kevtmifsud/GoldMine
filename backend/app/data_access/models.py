from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FilterParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)
    sort_by: str | None = None
    sort_order: str = Field(default="asc", pattern="^(asc|desc)$")
    filters: dict[str, str] = Field(default_factory=dict)
    search: str | None = None


class PaginatedResponse(BaseModel):
    data: list[dict[str, Any]]
    page: int
    page_size: int
    total_records: int
    total_pages: int
    has_next: bool
    has_previous: bool


class DatasetInfo(BaseModel):
    dataset_id: str
    name: str
    display_name: str
    description: str
    record_count: int
    id_field: str
    category: str
