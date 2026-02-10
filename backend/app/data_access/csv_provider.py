from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

from app.config.settings import settings
from app.data_access.interfaces import DataAccessProvider
from app.data_access.models import DatasetInfo, FilterParams, PaginatedResponse
from app.exceptions import DataAccessError, NotFoundError
from app.logging_config import get_logger

logger = get_logger(__name__)

# Dataset name → ID field mapping (loaded from datasets.csv)
_ID_FIELDS: dict[str, str] = {}


class CsvDataAccessProvider(DataAccessProvider):
    def __init__(self, data_dir: str | None = None):
        self._data_dir = Path(data_dir or settings.DATA_DIR).resolve()
        self._cache: dict[str, list[dict[str, Any]]] = {}
        self._datasets_meta: list[DatasetInfo] = []
        self._load_datasets_meta()

    def _load_datasets_meta(self) -> None:
        datasets_path = self._data_dir / "datasets.csv"
        if not datasets_path.exists():
            logger.warning("datasets_csv_missing", path=str(datasets_path))
            return
        rows = self._read_csv(datasets_path)
        for row in rows:
            info = DatasetInfo(**row)
            self._datasets_meta.append(info)
            _ID_FIELDS[info.name] = info.id_field

    def _read_csv(self, path: Path) -> list[dict[str, Any]]:
        try:
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                return list(reader)
        except Exception as e:
            raise DataAccessError(f"Failed to read {path}: {e}")

    def _get_data(self, dataset: str) -> list[dict[str, Any]]:
        if dataset in self._cache:
            return self._cache[dataset]
        path = self._data_dir / f"{dataset}.csv"
        if not path.exists():
            raise NotFoundError(f"Dataset '{dataset}' not found")
        data = self._read_csv(path)
        self._cache[dataset] = data
        logger.info("csv_loaded", dataset=dataset, rows=len(data))
        return data

    def list_datasets(self) -> list[DatasetInfo]:
        return self._datasets_meta

    def query(self, dataset: str, params: FilterParams) -> PaginatedResponse:
        data = self._get_data(dataset)

        # Apply filters
        filtered = data
        for field, value in params.filters.items():
            filtered = [r for r in filtered if str(r.get(field, "")).lower() == value.lower()]

        # Apply search (searches across all string fields)
        if params.search:
            search_lower = params.search.lower()
            filtered = [
                r for r in filtered
                if any(search_lower in str(v).lower() for v in r.values())
            ]

        # Sort
        if params.sort_by and filtered:
            reverse = params.sort_order == "desc"
            try:
                filtered.sort(key=lambda r: _sort_key(r.get(params.sort_by, "")), reverse=reverse)
            except Exception:
                pass  # Skip sort if field types are inconsistent

        # Enforce max page size
        page_size = min(params.page_size, settings.MAX_PAGE_SIZE)
        total = len(filtered)
        total_pages = max(1, math.ceil(total / page_size))
        page = min(params.page, total_pages)

        start = (page - 1) * page_size
        end = start + page_size
        page_data = filtered[start:end]

        return PaginatedResponse(
            data=page_data,
            page=page,
            page_size=page_size,
            total_records=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        )

    def get_record(self, dataset: str, record_id: str) -> dict[str, Any] | None:
        data = self._get_data(dataset)
        id_field = _ID_FIELDS.get(dataset)
        if not id_field:
            # Fallback: try first column
            if data:
                id_field = list(data[0].keys())[0]
            else:
                return None
        for row in data:
            if str(row.get(id_field, "")) == record_id:
                return row
        return None


def _sort_key(value: Any) -> Any:
    """Try to sort numerically, fall back to string."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return str(value).lower()
