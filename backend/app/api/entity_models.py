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


class FilterOption(BaseModel):
    value: str
    label: str


class FilterDefinition(BaseModel):
    field: str
    label: str
    filter_type: str = "select"
    options: list[FilterOption] = Field(default_factory=list)


class SecondaryLine(BaseModel):
    y_key: str
    y_key_alt: str | None = None
    label: str
    label_alt: str | None = None
    color: str = "#e86319"


class BarConfig(BaseModel):
    y_key: str
    y_key_alt: str | None = None
    label: str
    color: str


class ChartConfig(BaseModel):
    chart_type: str  # "bar" or "line"
    x_key: str
    y_key: str
    x_label: str
    y_label: str
    color: str = "#2a4a7f"
    y_format: str | None = None  # "currency", "number", or None (raw)
    y_key_alt: str | None = None
    y_label_alt: str | None = None
    y_format_alt: str | None = None
    color_key: str | None = None
    bars: list[BarConfig] = Field(default_factory=list)
    stacked: bool = False
    secondary_y_label: str | None = None
    secondary_y_label_alt: str | None = None
    secondary_lines: list[SecondaryLine] = Field(default_factory=list)


class ColumnConfig(BaseModel):
    key: str
    label: str
    format: str = "text"
    sortable: bool = True
    visible: bool = True
    entity_type: str | None = None       # e.g. "stock", "person", "portfolio"
    entity_id_field: str | None = None   # when display value != entity ID (e.g. name → person_id)


class WidgetConfig(BaseModel):
    widget_id: str
    title: str
    endpoint: str
    columns: list[ColumnConfig]
    default_page_size: int = 10
    widget_type: str = "table"
    chart_config: ChartConfig | None = None
    filter_definitions: list[FilterDefinition] = Field(default_factory=list)
    client_filterable_columns: list[str] = Field(default_factory=list)
    full_width: bool = False
    has_overrides: bool = False
    initial_filters: dict[str, str] = Field(default_factory=dict)
    initial_sort_by: str | None = None
    initial_sort_order: str | None = None
    initial_column_filters: dict | None = None


class EntityDetail(BaseModel):
    entity_type: str
    entity_id: str
    display_name: str
    header_fields: list[EntityField]
    widgets: list[WidgetConfig]
    active_view_id: str | None = None
    active_view_name: str | None = None
