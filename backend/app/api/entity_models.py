from __future__ import annotations

from pydantic import BaseModel, Field


class EntityCandidate(BaseModel):
    entity_type: str
    entity_id: str
    display_name: str


class EntityResolution(BaseModel):
    resolved: bool
    entity_type: str | None = None
    entity_id: str | None = None
    display_name: str | None = None
    message: str | None = None
    candidates: list[EntityCandidate] = Field(default_factory=list)


class EntityField(BaseModel):
    label: str
    value: str | None = None
    format: str = "text"  # "currency", "percent", "number", "text"


class ColumnConfig(BaseModel):
    key: str
    label: str
    format: str = "text"
    sortable: bool = True


class WidgetConfig(BaseModel):
    widget_id: str
    title: str
    endpoint: str
    columns: list[ColumnConfig]
    default_page_size: int = 10


class EntityDetail(BaseModel):
    entity_type: str
    entity_id: str
    display_name: str
    header_fields: list[EntityField]
    widgets: list[WidgetConfig]
