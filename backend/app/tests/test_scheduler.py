from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from dateutil.relativedelta import relativedelta

from app.email.factory import get_schedule_provider
from app.email.models import EmailScheduleCreate, WidgetOverrideRef
from app.email.scheduler import _compute_next_run, _process_due_schedules, _update_schedule_fields


@pytest.mark.asyncio
async def test_get_due_schedules():
    provider = get_schedule_provider()
    schedule = provider.create_schedule(
        EmailScheduleCreate(
            name="Due Schedule",
            entity_type="stock",
            entity_id="AAPL",
            recipients=["test@example.com"],
            recurrence="daily",
        ),
        owner="analyst1",
    )
    # Set next_run_at to the past
    past = (datetime.now(timezone.utc) - relativedelta(hours=1)).isoformat()
    _update_schedule_fields(schedule.schedule_id, {"next_run_at": past})

    due = provider.get_due_schedules()
    assert len(due) == 1
    assert due[0].schedule_id == schedule.schedule_id


@pytest.mark.asyncio
async def test_process_due_schedule_success():
    provider = get_schedule_provider()
    schedule = provider.create_schedule(
        EmailScheduleCreate(
            name="Auto Send",
            entity_type="stock",
            entity_id="AAPL",
            recipients=["test@example.com"],
            recurrence="daily",
        ),
        owner="analyst1",
    )
    past = (datetime.now(timezone.utc) - relativedelta(hours=1)).isoformat()
    _update_schedule_fields(schedule.schedule_id, {"next_run_at": past})

    _process_due_schedules()

    # Verify log created
    logs = provider.get_logs(schedule.schedule_id)
    assert len(logs) == 1
    assert logs[0].status == "sent"

    # Verify next_run_at advanced
    updated = provider.get_schedule(schedule.schedule_id)
    assert updated is not None
    assert updated.next_run_at > past
    assert updated.retry_count == 0


@pytest.mark.asyncio
async def test_process_due_schedule_retry():
    provider = get_schedule_provider()
    schedule = provider.create_schedule(
        EmailScheduleCreate(
            name="Failing Schedule",
            entity_type="stock",
            entity_id="AAPL",
            recipients=["test@example.com"],
            recurrence="daily",
        ),
        owner="analyst1",
    )
    past = (datetime.now(timezone.utc) - relativedelta(hours=1)).isoformat()
    _update_schedule_fields(schedule.schedule_id, {"next_run_at": past})

    # Mock email provider to fail
    import app.email.factory as emf
    mock_provider = MagicMock()
    mock_provider.send_email.return_value = False
    emf._email_provider = mock_provider

    _process_due_schedules()

    # Verify failure logged
    logs = provider.get_logs(schedule.schedule_id)
    assert len(logs) == 1
    assert logs[0].status == "failed"

    # Verify retry_count incremented and next_run_at set to ~5 min from now
    updated = provider.get_schedule(schedule.schedule_id)
    assert updated is not None
    assert updated.retry_count == 1
    assert updated.status == "active"
    # next_run_at should be roughly 5 minutes in the future
    next_run = datetime.fromisoformat(updated.next_run_at)
    assert next_run > datetime.now(timezone.utc)
