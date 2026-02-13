from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.config.settings import settings
from app.email.interfaces import EmailProvider
from app.logging_config import get_logger

logger = get_logger(__name__)


class ConsoleEmailProvider(EmailProvider):
    def __init__(self) -> None:
        self._log_path = Path(settings.SCHEDULES_DIR).resolve() / "email_log.json"

    def send_email(self, recipients: list[str], subject: str, html_body: str, text_body: str, images: list[tuple[str, bytes]] | None = None) -> bool:
        logger.info(
            "email_sent",
            recipients=recipients,
            subject=subject,
            html_length=len(html_body),
            text_length=len(text_body),
        )

        entry = {
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "recipients": recipients,
            "subject": subject,
            "html_body": html_body,
            "text_body": text_body,
        }

        # Append to log file
        existing: list[dict] = []
        if self._log_path.exists():
            try:
                with open(self._log_path) as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, OSError):
                existing = []

        existing.append(entry)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._log_path, "w") as f:
            json.dump(existing, f, indent=2)

        return True
