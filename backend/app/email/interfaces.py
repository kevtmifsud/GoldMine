from __future__ import annotations

from abc import ABC, abstractmethod

from app.email.models import EmailLog, EmailSchedule, EmailScheduleCreate, EmailScheduleUpdate


class EmailProvider(ABC):
    @abstractmethod
    def send_email(
        self,
        recipients: list[str],
        subject: str,
        html_body: str,
        text_body: str,
        images: list[tuple[str, bytes]] | None = None,
    ) -> bool:
        """Send an email. Returns True on success.

        images: optional list of (cid, png_bytes) tuples for inline images.
        """


class ScheduleProvider(ABC):
    @abstractmethod
    def create_schedule(self, schedule: EmailScheduleCreate, owner: str) -> EmailSchedule:
        """Create a new email schedule."""

    @abstractmethod
    def get_schedule(self, schedule_id: str) -> EmailSchedule | None:
        """Get a schedule by ID."""

    @abstractmethod
    def list_schedules(self, owner: str | None = None, entity_type: str | None = None, entity_id: str | None = None) -> list[EmailSchedule]:
        """List schedules with optional filters."""

    @abstractmethod
    def update_schedule(self, schedule_id: str, update: EmailScheduleUpdate) -> EmailSchedule | None:
        """Update a schedule. Returns None if not found."""

    @abstractmethod
    def delete_schedule(self, schedule_id: str) -> bool:
        """Delete a schedule. Returns True if deleted."""

    @abstractmethod
    def get_due_schedules(self) -> list[EmailSchedule]:
        """Return active schedules where next_run_at <= now."""

    @abstractmethod
    def add_log(self, log: EmailLog) -> EmailLog:
        """Add a delivery log entry."""

    @abstractmethod
    def get_logs(self, schedule_id: str) -> list[EmailLog]:
        """Get delivery logs for a schedule, sorted by sent_at desc."""
