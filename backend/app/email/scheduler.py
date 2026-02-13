from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI

from app.config.settings import settings
from app.email.factory import get_email_provider, get_schedule_provider
from app.email.models import EmailLog, EmailScheduleUpdate
from dateutil.relativedelta import relativedelta
from app.email.renderer import render_email
from app.logging_config import get_logger

logger = get_logger(__name__)


def start_scheduler(app: FastAPI) -> None:
    """Register a background task that processes due schedules."""

    @app.on_event("startup")
    async def _launch_scheduler() -> None:
        asyncio.create_task(_scheduler_loop())
        logger.info("scheduler_started", interval=settings.SCHEDULER_INTERVAL_SECONDS)

    async def _scheduler_loop() -> None:
        while True:
            await asyncio.sleep(settings.SCHEDULER_INTERVAL_SECONDS)
            try:
                await asyncio.to_thread(_process_due_schedules)
            except Exception:
                logger.exception("scheduler_loop_error")


def _process_due_schedules() -> None:
    """Check for and process all due schedules."""
    schedule_provider = get_schedule_provider()
    email_provider = get_email_provider()

    due = schedule_provider.get_due_schedules()
    if not due:
        return

    logger.info("processing_due_schedules", count=len(due))

    for schedule in due:
        try:
            subject, html_body, text_body, images = render_email(
                entity_type=schedule.entity_type,
                entity_id=schedule.entity_id,
                schedule_name=schedule.name,
                widget_ids=schedule.widget_ids,
                widget_overrides=schedule.widget_overrides,
            )

            success = email_provider.send_email(
                recipients=schedule.recipients,
                subject=subject,
                html_body=html_body,
                text_body=text_body,
                images=images,
            )

            now = datetime.now(timezone.utc).isoformat()

            if success:
                schedule_provider.add_log(EmailLog(
                    log_id=str(uuid.uuid4()),
                    schedule_id=schedule.schedule_id,
                    sent_at=now,
                    status="sent",
                    recipients=schedule.recipients,
                ))
                next_run = _compute_next_run(
                    datetime.fromisoformat(schedule.next_run_at),
                    schedule.days_of_week,
                    schedule.time_of_day,
                    schedule.recurrence_type,
                    schedule.day_of_month,
                )
                schedule_provider.update_schedule(
                    schedule.schedule_id,
                    EmailScheduleUpdate(
                        status="active",
                    ),
                )
                # Direct update for fields not in EmailScheduleUpdate
                _update_schedule_fields(schedule.schedule_id, {
                    "retry_count": 0,
                    "next_run_at": next_run,
                    "last_run_at": now,
                })
                logger.info("schedule_sent", schedule_id=schedule.schedule_id)
            else:
                _handle_failure(schedule, "Email provider returned False", now)

        except Exception as e:
            now = datetime.now(timezone.utc).isoformat()
            _handle_failure(schedule, str(e), now)
            logger.exception("schedule_send_error", schedule_id=schedule.schedule_id)


def _handle_failure(schedule: "EmailSchedule", error: str, now: str) -> None:  # noqa: F821
    """Handle a failed schedule send with retry logic."""
    from app.email.models import EmailSchedule

    schedule_provider = get_schedule_provider()
    new_retry_count = schedule.retry_count + 1

    schedule_provider.add_log(EmailLog(
        log_id=str(uuid.uuid4()),
        schedule_id=schedule.schedule_id,
        sent_at=now,
        status="failed",
        error=error,
        recipients=schedule.recipients,
    ))

    if new_retry_count >= 3:
        _update_schedule_fields(schedule.schedule_id, {
            "status": "failed",
            "retry_count": new_retry_count,
        })
        logger.warning("schedule_failed_permanently", schedule_id=schedule.schedule_id, retries=new_retry_count)
    else:
        # Retry in 5 minutes
        retry_at = datetime.fromisoformat(now) + relativedelta(minutes=5)
        _update_schedule_fields(schedule.schedule_id, {
            "retry_count": new_retry_count,
            "next_run_at": retry_at.isoformat(),
        })
        logger.warning("schedule_retry_queued", schedule_id=schedule.schedule_id, retry_count=new_retry_count)


def _update_schedule_fields(schedule_id: str, fields: dict) -> None:
    """Directly update schedule fields that aren't covered by EmailScheduleUpdate."""
    schedule_provider = get_schedule_provider()
    schedule = schedule_provider.get_schedule(schedule_id)
    if schedule is None:
        return

    schedules = schedule_provider._read_schedules()  # type: ignore[attr-defined]
    for i, s in enumerate(schedules):
        if s.schedule_id == schedule_id:
            data = s.model_dump()
            data.update(fields)
            data["updated_at"] = datetime.now(timezone.utc).isoformat()
            schedules[i] = type(s)(**data)
            schedule_provider._write_schedules(schedules)  # type: ignore[attr-defined]
            return


def _compute_next_run(
    current: datetime,
    days_of_week: list[int],
    time_of_day: str,
    recurrence_type: str = "weekly",
    day_of_month: int | None = None,
) -> str:
    """Compute the next run time based on recurrence settings."""
    hour, minute = map(int, time_of_day.split(":"))

    if recurrence_type == "monthly" and day_of_month is not None:
        candidate = current + relativedelta(months=1)
        try:
            candidate = candidate.replace(day=day_of_month, hour=hour, minute=minute, second=0, microsecond=0)
        except ValueError:
            candidate = candidate.replace(day=28, hour=hour, minute=minute, second=0, microsecond=0)
        return candidate.isoformat()

    # daily or weekly
    for offset in range(1, 8):
        candidate = (current + timedelta(days=offset)).replace(
            hour=hour, minute=minute, second=0, microsecond=0,
        )
        if candidate.weekday() in days_of_week:
            return candidate.isoformat()
    # Fallback
    return (current + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat()
