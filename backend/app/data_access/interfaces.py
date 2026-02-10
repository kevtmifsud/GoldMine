from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.data_access.models import DatasetInfo, FilterParams, PaginatedResponse


class DataAccessProvider(ABC):
    @abstractmethod
    def list_datasets(self) -> list[DatasetInfo]:
        """Return metadata about all available datasets."""

    @abstractmethod
    def query(self, dataset: str, params: FilterParams) -> PaginatedResponse:
        """Query a dataset with filtering, sorting, and pagination."""

    @abstractmethod
    def get_record(self, dataset: str, record_id: str) -> dict[str, Any] | None:
        """Get a single record by ID from a dataset."""
