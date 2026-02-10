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


class ChartConfig(BaseModel):
    chart_type: str  # "bar" or "line"
    x_key: str
    y_key: str
    x_label: str
    y_label: str
    color: str = "#2a4a7f"


class ColumnConfig(BaseModel):
    key: str
    label: str
    format: str = "text"
    sortable: bool = True
    visible: bool = True


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


class EntityDetail(BaseModel):
    entity_type: str
    entity_id: str
    display_name: str
    header_fields: list[EntityField]
    widgets: list[WidgetConfig]
