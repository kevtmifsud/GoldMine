from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class WidgetStateOverride(BaseModel):
    widget_id: str
    server_filters: dict[str, str] = Field(default_factory=dict)
    sort_by: str | None = None
    sort_order: str | None = None
    visible_columns: list[str] | None = None
    page_size: int | None = None
    column_filters: dict | None = None


class SavedView(BaseModel):
    view_id: str
    name: str
    owner: str
    entity_type: str
    entity_id: str
    widget_overrides: list[WidgetStateOverride] = Field(default_factory=list)
    is_shared: bool = False
    is_default: bool = False
    created_at: str = ""
    updated_at: str = ""


class SavedViewCreate(BaseModel):
    name: str
    entity_type: str
    entity_id: str
    widget_overrides: list[WidgetStateOverride] = Field(default_factory=list)
    is_shared: bool = False
    is_default: bool = False


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
    row: int = 0
    col: int = 0


class MCPTileRef(BaseModel):
    """An MCP-driven tile in a pack.

    Stores a live MCP tool call that fetches data at render time.
    """
    tile_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    tool: str  # e.g. "get_estimates"
    params: dict = Field(default_factory=dict)
    display_type: str = "ag_grid"  # ag_grid | plotly_line | plotly_bar | number_card
    chart_config: dict | None = None
    grid_config: dict | None = None
    state_override: dict | None = None
    is_template: bool = False
    row: int = 0
    col: int = 0
    title_override: str | None = None


class AnalystPack(BaseModel):
    pack_id: str
    name: str
    owner: str
    owner_display_name: str = ""
    description: str = ""
    widgets: list[PackWidgetRef] = Field(default_factory=list)
    mcp_tiles: list[MCPTileRef] = Field(default_factory=list)
    is_shared: bool = False
    created_at: str = ""
    updated_at: str = ""
    row_columns: list[int] = Field(default_factory=lambda: [2])
    row_heights: list[int] = Field(default_factory=list)
    row_descriptions: list[str] = Field(default_factory=list)
    entity_type: str | None = None
    entity_id: str | None = None
    ticker_context: str | None = None
    source_conversation_id: str | None = None


class AnalystPackCreate(BaseModel):
    name: str
    description: str = ""
    widgets: list[PackWidgetRef] = Field(default_factory=list)
    mcp_tiles: list[MCPTileRef] = Field(default_factory=list)
    is_shared: bool = False
    row_columns: list[int] = Field(default_factory=lambda: [2])
    row_heights: list[int] = Field(default_factory=list)
    row_descriptions: list[str] = Field(default_factory=list)
    entity_type: str | None = None
    entity_id: str | None = None
    ticker_context: str | None = None
    source_conversation_id: str | None = None


class AnalystPackUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    widgets: list[PackWidgetRef] | None = None
    mcp_tiles: list[MCPTileRef] | None = None
    is_shared: bool | None = None
    row_columns: list[int] | None = None
    row_heights: list[int] | None = None
    row_descriptions: list[str] | None = None
    ticker_context: str | None = None
