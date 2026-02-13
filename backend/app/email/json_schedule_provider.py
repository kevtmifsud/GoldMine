from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.email.interfaces import ScheduleProvider
from app.email.models import EmailLog, EmailSchedule, EmailScheduleCreate, EmailScheduleUpdate
from app.logging_config import get_logger

logger = get_logger(__name__)


class JsonScheduleProvider(ScheduleProvider):
    def __init__(self, schedules_dir: str) -> None:
        self._dir = Path(schedules_dir).resolve()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._schedules_path = self._dir / "schedules.json"
        self._logs_path = self._dir / "delivery_log.json"
        logger.info("schedule_provider_init", dir=str(self._dir))

    # -- internal helpers -------------------------------------------------------

    def _read_schedules(self) -> list[EmailSchedule]:
        if not self._schedules_path.exists():
            return []
        with open(self._schedules_path) as f:
            data = json.load(f)
        return [EmailSchedule(**s) for s in data]

    def _write_schedules(self, schedules: list[EmailSchedule]) -> None:
        with open(self._schedules_path, "w") as f:
            json.dump([s.model_dump() for s in schedules], f, indent=2)

    def _read_logs(self) -> list[EmailLog]:
        if not self._logs_path.exists():
            return []
        with open(self._logs_path) as f:
            data = json.load(f)
        return [EmailLog(**l) for l in data]

    def _write_logs(self, logs: list[EmailLog]) -> None:
        with open(self._logs_path, "w") as f:
            json.dump([l.model_dump() for l in logs], f, indent=2)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    # -- schedules ---------------------------------------------------------------

    def create_schedule(self, schedule: EmailScheduleCreate, owner: str) -> EmailSchedule:
        schedules = self._read_schedules()
        now = self._now()
        saved = EmailSchedule(
            schedule_id=str(uuid.uuid4()),
            owner=owner,
            name=schedule.name,
            entity_type=schedule.entity_type,
            entity_id=schedule.entity_id,
            widget_ids=schedule.widget_ids,
            recipients=schedule.recipients,
            time_of_day=schedule.time_of_day,
            days_of_week=schedule.days_of_week,
            widget_overrides=schedule.widget_overrides,
            created_at=now,
            updated_at=now,
        )
        schedules.append(saved)
        self._write_schedules(schedules)
        logger.info("schedule_created", schedule_id=saved.schedule_id, owner=owner)
        return saved

    def get_schedule(self, schedule_id: str) -> EmailSchedule | None:
        for s in self._read_schedules():
            if s.schedule_id == schedule_id:
                return s
        return None

    def list_schedules(self, owner: str | None = None, entity_type: str | None = None, entity_id: str | None = None) -> list[EmailSchedule]:
        schedules = self._read_schedules()
        if owner is not None:
            schedules = [s for s in schedules if s.owner == owner]
        if entity_type is not None:
            schedules = [s for s in schedules if s.entity_type == entity_type]
        if entity_id is not None:
            schedules = [s for s in schedules if s.entity_id == entity_id]
        return schedules

    def update_schedule(self, schedule_id: str, update: EmailScheduleUpdate) -> EmailSchedule | None:
        schedules = self._read_schedules()
        for i, s in enumerate(schedules):
            if s.schedule_id == schedule_id:
                data = s.model_dump()
                update_data = update.model_dump(exclude_none=True)
                if "widget_overrides" in update_data:
                    update_data["widget_overrides"] = [
                        wo.model_dump() if hasattr(wo, "model_dump") else wo
                        for wo in update_data["widget_overrides"]
                    ]
                data.update(update_data)
                data["updated_at"] = self._now()
                schedules[i] = EmailSchedule(**data)
                self._write_schedules(schedules)
                return schedules[i]
        return None

    def delete_schedule(self, schedule_id: str) -> bool:
        schedules = self._read_schedules()
        new_schedules = [s for s in schedules if s.schedule_id != schedule_id]
        if len(new_schedules) == len(schedules):
            return False
        self._write_schedules(new_schedules)
        logger.info("schedule_deleted", schedule_id=schedule_id)
        return True

    def get_due_schedules(self) -> list[EmailSchedule]:
        now = datetime.now(timezone.utc).isoformat()
        schedules = self._read_schedules()
        return [
            s for s in schedules
            if s.status == "active" and s.next_run_at and s.next_run_at <= now
        ]

    # -- logs -------------------------------------------------------------------

    def add_log(self, log: EmailLog) -> EmailLog:
        logs = self._read_logs()
        logs.append(log)
        self._write_logs(logs)
        return log

    def get_logs(self, schedule_id: str) -> list[EmailLog]:
        logs = self._read_logs()
        filtered = [l for l in logs if l.schedule_id == schedule_id]
        filtered.sort(key=lambda l: l.sent_at, reverse=True)
        return filtered
