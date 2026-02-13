from __future__ import annotations

import uuid
from datetime import datetime, timezone

from dateutil.relativedelta import relativedelta
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
    next_run = _compute_initial_next_run(body.recurrence)
    from app.email.scheduler import _update_schedule_fields
    _update_schedule_fields(schedule.schedule_id, {"next_run_at": next_run})

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

    # If recurrence changed, recompute next_run_at
    if body.recurrence is not None and body.recurrence != existing.recurrence:
        next_run = _compute_initial_next_run(body.recurrence)
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

    subject, html_body, text_body = render_email(
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


def _compute_initial_next_run(recurrence: str) -> str:
    """Compute the first next_run_at based on recurrence."""
    now = datetime.now(timezone.utc)

    if recurrence == "daily":
        # Tomorrow at 05:00 UTC
        next_dt = (now + relativedelta(days=1)).replace(hour=5, minute=0, second=0, microsecond=0)
    elif recurrence == "weekly":
        # Next Monday at 05:00 UTC
        days_until_monday = (7 - now.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        next_dt = (now + relativedelta(days=days_until_monday)).replace(hour=5, minute=0, second=0, microsecond=0)
    elif recurrence == "monthly":
        # First of next month at 05:00 UTC
        next_dt = (now + relativedelta(months=1)).replace(day=1, hour=5, minute=0, second=0, microsecond=0)
    else:
        next_dt = (now + relativedelta(days=1)).replace(hour=5, minute=0, second=0, microsecond=0)

    return next_dt.isoformat()
