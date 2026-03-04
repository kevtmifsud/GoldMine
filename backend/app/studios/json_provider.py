from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.logging_config import get_logger
from app.studios.interfaces import StudiosProvider
from app.studios.models import (
    Studio,
    StudioCreate,
    StudioUpdate,
)

logger = get_logger(__name__)


class JsonStudiosProvider(StudiosProvider):
    def __init__(self, studios_dir: str) -> None:
        self._dir = Path(studios_dir).resolve()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._studios_path = self._dir / "studios.json"
        logger.info("studios_provider_init", dir=str(self._dir))

    # -- internal helpers -------------------------------------------------------

    def _read_studios(self) -> list[Studio]:
        if not self._studios_path.exists():
            return []
        with open(self._studios_path) as f:
            data = json.load(f)
        return [Studio(**s) for s in data]

    def _write_studios(self, studios: list[Studio]) -> None:
        with open(self._studios_path, "w") as f:
            json.dump([s.model_dump() for s in studios], f, indent=2)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    # -- studios ----------------------------------------------------------------

    def list_studios(self, owner: str | None = None) -> list[Studio]:
        studios = self._read_studios()
        if owner is not None:
            studios = [s for s in studios if s.owner == owner or s.is_shared]
        return studios

    def get_studio(self, studio_id: str) -> Studio | None:
        for s in self._read_studios():
            if s.studio_id == studio_id:
                return s
        return None

    def create_studio(self, studio: StudioCreate, owner: str) -> Studio:
        studios = self._read_studios()
        now = self._now()
        saved = Studio(
            studio_id=str(uuid.uuid4()),
            name=studio.name,
            owner=owner,
            description=studio.description,
            is_shared=studio.is_shared,
            created_at=now,
            updated_at=now,
        )
        studios.append(saved)
        self._write_studios(studios)
        logger.info("studio_created", studio_id=saved.studio_id, owner=owner)
        return saved

    def update_studio(self, studio_id: str, update: StudioUpdate) -> Studio | None:
        studios = self._read_studios()
        for i, s in enumerate(studios):
            if s.studio_id == studio_id:
                data = s.model_dump()
                update_data = update.model_dump(exclude_none=True)
                if "widgets" in update_data:
                    update_data["widgets"] = [
                        w.model_dump() if hasattr(w, "model_dump") else w
                        for w in update_data["widgets"]
                    ]
                if "messages" in update_data:
                    update_data["messages"] = [
                        m.model_dump() if hasattr(m, "model_dump") else m
                        for m in update_data["messages"]
                    ]
                data.update(update_data)
                data["updated_at"] = self._now()
                studios[i] = Studio(**data)
                self._write_studios(studios)
                return studios[i]
        return None

    def delete_studio(self, studio_id: str) -> bool:
        studios = self._read_studios()
        new_studios = [s for s in studios if s.studio_id != studio_id]
        if len(new_studios) == len(studios):
            return False
        self._write_studios(new_studios)
        logger.info("studio_deleted", studio_id=studio_id)
        return True
