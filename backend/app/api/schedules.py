from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query, Request
from starlette.responses import Response

from app.email.factory import get_email_provider, get_schedule_provider
from app.email.models import EmailLog, EmailSchedule, EmailScheduleCreate, EmailScheduleUpdate
from app.email.renderer import render_email
from app.exceptions import NotFoundError
from app.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


@router.post("/", status_code=201)
async def create_schedule(request: Request, body: EmailScheduleCreate) -> EmailSchedule:
    user = request.state.user
    provider = get_schedule_provider()
    schedule = provider.create_schedule(body, owner=user.username)

    # Compute initial next_run_at
    next_run = _compute_initial_next_run(body.time_of_day, body.days_of_week, body.recurrence_type, body.day_of_month)
    from app.email.scheduler import _update_schedule_fields
    _update_schedule_fields(schedule.schedule_id, {"next_run_at": next_run})

    # Burst send: immediately send the email on creation
    now = datetime.now(timezone.utc).isoformat()
    try:
        subject, html_body, text_body, images = render_email(
            entity_type=schedule.entity_type,
            entity_id=schedule.entity_id,
            schedule_name=schedule.name,
            widget_ids=schedule.widget_ids,
            widget_overrides=schedule.widget_overrides,
        )
        email_provider = get_email_provider()
        success = email_provider.send_email(
            recipients=schedule.recipients,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            images=images,
        )
        status = "sent" if success else "failed"
        error = None if success else "Email provider returned False"
    except Exception as e:
        status = "failed"
        error = str(e)

    log = EmailLog(
        log_id=str(uuid.uuid4()),
        schedule_id=schedule.schedule_id,
        sent_at=now,
        status=status,
        error=error,
        recipients=schedule.recipients,
    )
    provider.add_log(log)
    _update_schedule_fields(schedule.schedule_id, {"last_run_at": now})

    return provider.get_schedule(schedule.schedule_id) or schedule


@router.get("/")
async def list_schedules(
    request: Request,
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
) -> list[EmailSchedule]:
    user = request.state.user
    provider = get_schedule_provider()
    return provider.list_schedules(owner=user.username, entity_type=entity_type, entity_id=entity_id)


@router.get("/{schedule_id}")
async def get_schedule(request: Request, schedule_id: str) -> EmailSchedule:
    user = request.state.user
    provider = get_schedule_provider()
    schedule = provider.get_schedule(schedule_id)
    if schedule is None or schedule.owner != user.username:
        raise NotFoundError(f"Schedule '{schedule_id}' not found")
    return schedule


@router.put("/{schedule_id}")
async def update_schedule(request: Request, schedule_id: str, body: EmailScheduleUpdate) -> EmailSchedule:
    user = request.state.user
    provider = get_schedule_provider()
    existing = provider.get_schedule(schedule_id)
    if existing is None or existing.owner != user.username:
        raise NotFoundError(f"Schedule '{schedule_id}' not found")

    updated = provider.update_schedule(schedule_id, body)
    if updated is None:
        raise NotFoundError(f"Schedule '{schedule_id}' not found")

    # If scheduling fields changed, recompute next_run_at
    time_changed = body.time_of_day is not None and body.time_of_day != existing.time_of_day
    days_changed = body.days_of_week is not None and body.days_of_week != existing.days_of_week
    recurrence_changed = body.recurrence_type is not None and body.recurrence_type != existing.recurrence_type
    dom_changed = body.day_of_month is not None and body.day_of_month != existing.day_of_month
    if time_changed or days_changed or recurrence_changed or dom_changed:
        new_time = body.time_of_day if body.time_of_day is not None else existing.time_of_day
        new_days = body.days_of_week if body.days_of_week is not None else existing.days_of_week
        new_recurrence = body.recurrence_type if body.recurrence_type is not None else existing.recurrence_type
        new_dom = body.day_of_month if body.day_of_month is not None else existing.day_of_month
        next_run = _compute_initial_next_run(new_time, new_days, new_recurrence, new_dom)
        from app.email.scheduler import _update_schedule_fields
        _update_schedule_fields(schedule_id, {"next_run_at": next_run})
        return provider.get_schedule(schedule_id) or updated

    return updated


@router.delete("/{schedule_id}", status_code=204, response_class=Response)
async def delete_schedule(request: Request, schedule_id: str) -> Response:
    user = request.state.user
    provider = get_schedule_provider()
    existing = provider.get_schedule(schedule_id)
    if existing is None or existing.owner != user.username:
        raise NotFoundError(f"Schedule '{schedule_id}' not found")
    provider.delete_schedule(schedule_id)


@router.get("/{schedule_id}/logs")
async def get_schedule_logs(request: Request, schedule_id: str) -> list[EmailLog]:
    user = request.state.user
    provider = get_schedule_provider()
    existing = provider.get_schedule(schedule_id)
    if existing is None or existing.owner != user.username:
        raise NotFoundError(f"Schedule '{schedule_id}' not found")
    return provider.get_logs(schedule_id)


@router.post("/{schedule_id}/send-now")
async def send_now(request: Request, schedule_id: str) -> EmailLog:
    user = request.state.user
    schedule_provider = get_schedule_provider()
    schedule = schedule_provider.get_schedule(schedule_id)
    if schedule is None or schedule.owner != user.username:
        raise NotFoundError(f"Schedule '{schedule_id}' not found")

    subject, html_body, text_body, images = render_email(
        entity_type=schedule.entity_type,
        entity_id=schedule.entity_id,
        schedule_name=schedule.name,
        widget_ids=schedule.widget_ids,
        widget_overrides=schedule.widget_overrides,
    )

    email_provider = get_email_provider()
    now = datetime.now(timezone.utc).isoformat()

    try:
        success = email_provider.send_email(
            recipients=schedule.recipients,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            images=images,
        )
        status = "sent" if success else "failed"
        error = None if success else "Email provider returned False"
    except Exception as e:
        status = "failed"
        error = str(e)

    log = EmailLog(
        log_id=str(uuid.uuid4()),
        schedule_id=schedule_id,
        sent_at=now,
        status=status,
        error=error,
        recipients=schedule.recipients,
    )
    schedule_provider.add_log(log)
    return log


def _compute_initial_next_run(
    time_of_day: str,
    days_of_week: list[int],
    recurrence_type: str = "weekly",
    day_of_month: int | None = None,
) -> str:
    """Compute the first next_run_at based on recurrence settings."""
    now = datetime.now(timezone.utc)
    hour, minute = map(int, time_of_day.split(":"))

    if recurrence_type == "monthly" and day_of_month is not None:
        # Target this month's day_of_month at the given time
        try:
            candidate = now.replace(day=day_of_month, hour=hour, minute=minute, second=0, microsecond=0)
        except ValueError:
            candidate = now.replace(day=28, hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > now:
            return candidate.isoformat()
        # Otherwise next month
        from dateutil.relativedelta import relativedelta
        candidate = candidate + relativedelta(months=1)
        return candidate.isoformat()

    # daily or weekly: walk forward checking days_of_week
    # For daily, days_of_week should be [0..6] so every day matches
    today_target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now.weekday() in days_of_week and today_target > now:
        return today_target.isoformat()

    for offset in range(1, 8):
        candidate = (now + timedelta(days=offset)).replace(
            hour=hour, minute=minute, second=0, microsecond=0,
        )
        if candidate.weekday() in days_of_week:
            return candidate.isoformat()
    # Fallback: tomorrow
    return (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat()
