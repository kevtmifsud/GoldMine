from __future__ import annotations

from abc import ABC, abstractmethod

from app.studios.models import (
    Studio,
    StudioCreate,
    StudioUpdate,
)


class StudiosProvider(ABC):
    @abstractmethod
    def list_studios(self, owner: str | None = None) -> list[Studio]:
        """List studios. If owner is given, return owned + shared studios."""

    @abstractmethod
    def get_studio(self, studio_id: str) -> Studio | None:
        """Get a single studio by ID."""

    @abstractmethod
    def create_studio(self, studio: StudioCreate, owner: str) -> Studio:
        """Create a new studio."""

    @abstractmethod
    def update_studio(self, studio_id: str, update: StudioUpdate) -> Studio | None:
        """Update a studio. Returns None if not found."""

    @abstractmethod
    def delete_studio(self, studio_id: str) -> bool:
        """Delete a studio. Returns True if deleted, False if not found."""
