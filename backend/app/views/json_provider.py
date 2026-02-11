from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.logging_config import get_logger
from app.views.interfaces import ViewsProvider
from app.views.models import (
    AnalystPack,
    AnalystPackCreate,
    AnalystPackUpdate,
    SavedView,
    SavedViewCreate,
    SavedViewUpdate,
)

logger = get_logger(__name__)


class JsonViewsProvider(ViewsProvider):
    def __init__(self, views_dir: str) -> None:
        self._dir = Path(views_dir).resolve()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._views_path = self._dir / "views.json"
        self._packs_path = self._dir / "packs.json"
        logger.info("views_provider_init", dir=str(self._dir))

    # -- internal helpers -------------------------------------------------------

    def _read_views(self) -> list[SavedView]:
        if not self._views_path.exists():
            return []
        with open(self._views_path) as f:
            data = json.load(f)
        return [SavedView(**v) for v in data]

    def _write_views(self, views: list[SavedView]) -> None:
        with open(self._views_path, "w") as f:
            json.dump([v.model_dump() for v in views], f, indent=2)

    def _read_packs(self) -> list[AnalystPack]:
        if not self._packs_path.exists():
            return []
        with open(self._packs_path) as f:
            data = json.load(f)
        return [AnalystPack(**p) for p in data]

    def _write_packs(self, packs: list[AnalystPack]) -> None:
        with open(self._packs_path, "w") as f:
            json.dump([p.model_dump() for p in packs], f, indent=2)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    # -- views ------------------------------------------------------------------

    def list_views(self, owner: str | None = None, entity_type: str | None = None, entity_id: str | None = None) -> list[SavedView]:
        views = self._read_views()
        if owner is not None:
            views = [v for v in views if v.owner == owner or v.is_shared]
        if entity_type is not None:
            views = [v for v in views if v.entity_type == entity_type]
        if entity_id is not None:
            views = [v for v in views if v.entity_id == entity_id]
        return views

    def get_view(self, view_id: str) -> SavedView | None:
        for v in self._read_views():
            if v.view_id == view_id:
                return v
        return None

    def create_view(self, view: SavedViewCreate, owner: str) -> SavedView:
        views = self._read_views()
        now = self._now()
        saved = SavedView(
            view_id=str(uuid.uuid4()),
            name=view.name,
            owner=owner,
            entity_type=view.entity_type,
            entity_id=view.entity_id,
            widget_overrides=view.widget_overrides,
            is_shared=view.is_shared,
            created_at=now,
            updated_at=now,
        )
        views.append(saved)
        self._write_views(views)
        logger.info("view_created", view_id=saved.view_id, owner=owner)
        return saved

    def update_view(self, view_id: str, update: SavedViewUpdate) -> SavedView | None:
        views = self._read_views()
        for i, v in enumerate(views):
            if v.view_id == view_id:
                data = v.model_dump()
                update_data = update.model_dump(exclude_none=True)
                # Convert widget_overrides back to dicts if present
                if "widget_overrides" in update_data:
                    update_data["widget_overrides"] = [
                        wo.model_dump() if hasattr(wo, "model_dump") else wo
                        for wo in update_data["widget_overrides"]
                    ]
                data.update(update_data)
                data["updated_at"] = self._now()
                views[i] = SavedView(**data)
                self._write_views(views)
                return views[i]
        return None

    def delete_view(self, view_id: str) -> bool:
        views = self._read_views()
        new_views = [v for v in views if v.view_id != view_id]
        if len(new_views) == len(views):
            return False
        self._write_views(new_views)
        logger.info("view_deleted", view_id=view_id)
        return True

    # -- packs ------------------------------------------------------------------

    def list_packs(self, owner: str | None = None) -> list[AnalystPack]:
        packs = self._read_packs()
        if owner is not None:
            packs = [p for p in packs if p.owner == owner or p.is_shared]
        return packs

    def get_pack(self, pack_id: str) -> AnalystPack | None:
        for p in self._read_packs():
            if p.pack_id == pack_id:
                return p
        return None

    def create_pack(self, pack: AnalystPackCreate, owner: str) -> AnalystPack:
        packs = self._read_packs()
        now = self._now()
        saved = AnalystPack(
            pack_id=str(uuid.uuid4()),
            name=pack.name,
            owner=owner,
            description=pack.description,
            widgets=pack.widgets,
            is_shared=pack.is_shared,
            created_at=now,
            updated_at=now,
        )
        packs.append(saved)
        self._write_packs(packs)
        logger.info("pack_created", pack_id=saved.pack_id, owner=owner)
        return saved

    def update_pack(self, pack_id: str, update: AnalystPackUpdate) -> AnalystPack | None:
        packs = self._read_packs()
        for i, p in enumerate(packs):
            if p.pack_id == pack_id:
                data = p.model_dump()
                update_data = update.model_dump(exclude_none=True)
                if "widgets" in update_data:
                    update_data["widgets"] = [
                        w.model_dump() if hasattr(w, "model_dump") else w
                        for w in update_data["widgets"]
                    ]
                data.update(update_data)
                data["updated_at"] = self._now()
                packs[i] = AnalystPack(**data)
                self._write_packs(packs)
                return packs[i]
        return None

    def delete_pack(self, pack_id: str) -> bool:
        packs = self._read_packs()
        new_packs = [p for p in packs if p.pack_id != pack_id]
        if len(new_packs) == len(packs):
            return False
        self._write_packs(new_packs)
        logger.info("pack_deleted", pack_id=pack_id)
        return True
