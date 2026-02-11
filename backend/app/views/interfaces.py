from __future__ import annotations

from abc import ABC, abstractmethod

from app.views.models import (
    AnalystPack,
    AnalystPackCreate,
    AnalystPackUpdate,
    SavedView,
    SavedViewCreate,
    SavedViewUpdate,
)


class ViewsProvider(ABC):
    @abstractmethod
    def list_views(self, owner: str | None = None, entity_type: str | None = None, entity_id: str | None = None) -> list[SavedView]:
        """List views. If owner is given, return owned + shared views."""

    @abstractmethod
    def get_view(self, view_id: str) -> SavedView | None:
        """Get a single view by ID."""

    @abstractmethod
    def create_view(self, view: SavedViewCreate, owner: str) -> SavedView:
        """Create a new saved view."""

    @abstractmethod
    def update_view(self, view_id: str, update: SavedViewUpdate) -> SavedView | None:
        """Update a saved view. Returns None if not found."""

    @abstractmethod
    def delete_view(self, view_id: str) -> bool:
        """Delete a view. Returns True if deleted, False if not found."""

    @abstractmethod
    def list_packs(self, owner: str | None = None) -> list[AnalystPack]:
        """List packs. If owner is given, return owned + shared packs."""

    @abstractmethod
    def get_pack(self, pack_id: str) -> AnalystPack | None:
        """Get a single pack by ID."""

    @abstractmethod
    def create_pack(self, pack: AnalystPackCreate, owner: str) -> AnalystPack:
        """Create a new analyst pack."""

    @abstractmethod
    def update_pack(self, pack_id: str, update: AnalystPackUpdate) -> AnalystPack | None:
        """Update a pack. Returns None if not found."""

    @abstractmethod
    def delete_pack(self, pack_id: str) -> bool:
        """Delete a pack. Returns True if deleted, False if not found."""
