from __future__ import annotations

from pydantic import BaseModel, Field


class WidgetOverrideRef(BaseModel):
    widget_id: str
    server_filters: dict[str, str] = Field(default_factory=dict)
    sort_by: str | None = None
    sort_order: str | None = None
    visible_columns: list[str] | None = None
    page_size: int | None = None


class EmailSchedule(BaseModel):
    schedule_id: str
    owner: str
    name: str
    entity_type: str
    entity_id: str
    widget_ids: list[str] | None = None
    recipients: list[str]
    recurrence: str = Field(pattern="^(daily|weekly|monthly)$")
    next_run_at: str = ""
    last_run_at: str = ""
    status: str = Field(default="active", pattern="^(active|paused|failed)$")
    widget_overrides: list[WidgetOverrideRef] = Field(default_factory=list)
    retry_count: int = 0
    created_at: str = ""
    updated_at: str = ""


class EmailLog(BaseModel):
    log_id: str
    schedule_id: str
    sent_at: str
    status: str = Field(pattern="^(sent|failed)$")
    error: str | None = None
    recipients: list[str]


class EmailScheduleCreate(BaseModel):
    name: str
    entity_type: str
    entity_id: str
    widget_ids: list[str] | None = None
    recipients: list[str] = Field(min_length=1)
    recurrence: str = Field(pattern="^(daily|weekly|monthly)$")
    widget_overrides: list[WidgetOverrideRef] = Field(default_factory=list)


class EmailScheduleUpdate(BaseModel):
    name: str | None = None
    recipients: list[str] | None = None
    recurrence: str | None = Field(default=None, pattern="^(daily|weekly|monthly)$")
    status: str | None = Field(default=None, pattern="^(active|paused|failed)$")
    widget_overrides: list[WidgetOverrideRef] | None = None
