from __future__ import annotations

from pydantic import BaseModel, Field


class ChartSeries(BaseModel):
    y_key: str
    label: str
    color: str = "#3182ce"


class StudioChartConfig(BaseModel):
    x_key: str
    y_key: str
    y_label: str = ""
    y_format: str | None = None  # "currency" | "number" | "percent"
    color: str = "#3182ce"
    series: list[ChartSeries] = Field(default_factory=list)


class DataSource(BaseModel):
    type: str  # "financials" | "dataset" | "price_history" | "portfolio_pnl" | "multi_price_indexed" | "multi_financials" | "none"
    # financials
    ticker: str | None = None
    statement_type: str | None = None
    period: str | None = None
    metrics: list[str] | None = None
    # dataset
    dataset: str | None = None
    filters: dict[str, str] | None = None
    sort_by: str | None = None
    sort_order: str | None = None
    limit: int | None = None
    # portfolio_pnl
    portfolio_name: str | None = None
    metric: str | None = None
    # multi_price_indexed
    tickers: list[str] | None = None
    indexed: bool = False


class StudioWidget(BaseModel):
    widget_id: str
    title: str
    chart_type: str  # "bar" | "line" | "echarts"
    chart_config: StudioChartConfig
    data_source: DataSource
    data: list[dict] = Field(default_factory=list)
    echarts_option: dict | None = None
    row: int = 0
    col: int = 0


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class Studio(BaseModel):
    studio_id: str
    name: str
    owner: str
    owner_display_name: str = ""
    description: str = ""
    is_shared: bool = False
    widgets: list[StudioWidget] = Field(default_factory=list)
    row_columns: list[int] = Field(default_factory=lambda: [2])
    row_heights: list[int] = Field(default_factory=list)
    messages: list[ChatMessage] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class StudioCreate(BaseModel):
    name: str
    description: str = ""
    is_shared: bool = False


class StudioUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_shared: bool | None = None
    widgets: list[StudioWidget] | None = None
    row_columns: list[int] | None = None
    row_heights: list[int] | None = None
    messages: list[ChatMessage] | None = None


class StudioChatRequest(BaseModel):
    message: str
    conversation_history: list[ChatMessage] = Field(default_factory=list)


class StudioChatResponse(BaseModel):
    reply: str
    widgets: list[StudioWidget] = Field(default_factory=list)
    row_columns: list[int] = Field(default_factory=lambda: [2])
    row_heights: list[int] = Field(default_factory=list)
    model: str = ""
    token_usage: dict[str, int] = Field(default_factory=dict)
