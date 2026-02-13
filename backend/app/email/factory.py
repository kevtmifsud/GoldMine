from __future__ import annotations

from app.config.settings import settings
from app.email.interfaces import EmailProvider, ScheduleProvider

_email_provider: EmailProvider | None = None
_schedule_provider: ScheduleProvider | None = None


def get_email_provider() -> EmailProvider:
    global _email_provider
    if _email_provider is not None:
        return _email_provider

    from app.email.console_provider import ConsoleEmailProvider
    _email_provider = ConsoleEmailProvider()
    return _email_provider


def get_schedule_provider() -> ScheduleProvider:
    global _schedule_provider
    if _schedule_provider is not None:
        return _schedule_provider

    from app.email.json_schedule_provider import JsonScheduleProvider
    _schedule_provider = JsonScheduleProvider(settings.SCHEDULES_DIR)
    return _schedule_provider
