from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class WidgetStateOverride(BaseModel):
    widget_id: str
    server_filters: dict[str, str] = Field(default_factory=dict)
    sort_by: str | None = None
    sort_order: str | None = None
    visible_columns: list[str] | None = None
    page_size: int | None = None


class SavedView(BaseModel):
    view_id: str
    name: str
    owner: str
    entity_type: str
    entity_id: str
    widget_overrides: list[WidgetStateOverride] = Field(default_factory=list)
    is_shared: bool = False
    created_at: str = ""
    updated_at: str = ""


class SavedViewCreate(BaseModel):
    name: str
    entity_type: str
    entity_id: str
    widget_overrides: list[WidgetStateOverride] = Field(default_factory=list)
    is_shared: bool = False


class SavedViewUpdate(BaseModel):
    name: str | None = None
    widget_overrides: list[WidgetStateOverride] | None = None
    is_shared: bool | None = None


class PackWidgetRef(BaseModel):
    source_entity_type: str
    source_entity_id: str
    widget_id: str
    title_override: str | None = None
    overrides: WidgetStateOverride | None = None


class AnalystPack(BaseModel):
    pack_id: str
    name: str
    owner: str
    description: str = ""
    widgets: list[PackWidgetRef] = Field(default_factory=list)
    is_shared: bool = False
    created_at: str = ""
    updated_at: str = ""


class AnalystPackCreate(BaseModel):
    name: str
    description: str = ""
    widgets: list[PackWidgetRef] = Field(default_factory=list)
    is_shared: bool = False


class AnalystPackUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    widgets: list[PackWidgetRef] | None = None
    is_shared: bool | None = None
