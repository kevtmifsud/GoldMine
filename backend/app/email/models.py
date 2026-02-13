from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


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
    time_of_day: str = Field(default="09:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    days_of_week: list[int] = Field(default=[0, 1, 2, 3, 4])
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
    time_of_day: str = Field(default="09:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    days_of_week: list[int] = Field(default=[0, 1, 2, 3, 4])
    widget_overrides: list[WidgetOverrideRef] = Field(default_factory=list)

    @field_validator("days_of_week")
    @classmethod
    def validate_days(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("days_of_week must contain at least one day")
        if any(d < 0 or d > 6 for d in v):
            raise ValueError("days_of_week values must be 0-6 (Mon=0, Sun=6)")
        return sorted(set(v))


class EmailScheduleUpdate(BaseModel):
    name: str | None = None
    recipients: list[str] | None = None
    time_of_day: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    days_of_week: list[int] | None = None
    status: str | None = Field(default=None, pattern="^(active|paused|failed)$")
    widget_overrides: list[WidgetOverrideRef] | None = None

    @field_validator("days_of_week")
    @classmethod
    def validate_days(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return v
        if not v:
            raise ValueError("days_of_week must contain at least one day")
        if any(d < 0 or d > 6 for d in v):
            raise ValueError("days_of_week values must be 0-6 (Mon=0, Sun=6)")
        return sorted(set(v))
