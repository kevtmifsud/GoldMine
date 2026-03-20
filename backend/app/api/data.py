from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.api.entities import _DATASET_JOINS, _JOIN_EXCLUDE_COLUMNS
from app.data_access.factory import get_data_provider
from app.data_access.models import DatasetInfo, FilterParams, PaginatedResponse
from app.exceptions import NotFoundError

router = APIRouter(prefix="/api/data", tags=["data"])

_KNOWN_PARAMS = {"page", "page_size", "sort_by", "sort_order", "search"}


def _enrich_rows(dataset: str, rows: list[dict], provider) -> list[dict]:
    """Join columns from related datasets onto each row.

    When a join target has a column that already exists natively (e.g.
    company_name), the join value overwrites the native one so that the
    canonical stocks-table data takes precedence.
    """
    joins = _DATASET_JOINS.get(dataset, [])
    if not joins or not rows:
        return rows
    native_keys = set(rows[0].keys())
    enriched = [dict(row) for row in rows]
    for target_dataset, source_key, target_key in joins:
        try:
            target_result = provider.query(target_dataset, FilterParams(page=1, page_size=1000))
            target_data = target_result.data
        except Exception:
            continue
        if not target_data:
            continue
        lookup = {r[target_key]: r for r in target_data}
        # Include columns that overlap with native keys (overwrite with join values)
        joinable_keys = [
            k for k in target_data[0]
            if k != target_key and k not in _JOIN_EXCLUDE_COLUMNS
        ]
        native_keys.update(joinable_keys)
        for row in enriched:
            target_row = lookup.get(row.get(source_key, ""))
            for k in joinable_keys:
                row[k] = target_row.get(k, "") if target_row else ""
    return enriched


@router.get("/")
async def list_datasets() -> list[DatasetInfo]:
    provider = get_data_provider()
    return provider.list_datasets()


@router.get("/{dataset}")
async def query_dataset(
    request: Request,
    dataset: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=1000),
    sort_by: str | None = Query(default=None),
    sort_order: str = Query(default="asc", pattern="^(asc|desc)$"),
    search: str | None = Query(default=None),
) -> PaginatedResponse:
    # Extract unknown query params as filters
    filters: dict[str, str] = {
        k: v for k, v in request.query_params.items() if k not in _KNOWN_PARAMS
    }
    provider = get_data_provider()
    params = FilterParams(
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        search=search,
        filters=filters,
    )
    result = provider.query(dataset, params)
    result.data = _enrich_rows(dataset, result.data, provider)
    return result


@router.get("/{dataset}/{record_id}")
async def get_record(dataset: str, record_id: str) -> dict:
    provider = get_data_provider()
    record = provider.get_record(dataset, record_id)
    if record is None:
        raise NotFoundError(f"Record '{record_id}' not found in '{dataset}'")
    enriched = _enrich_rows(dataset, [record], provider)
    return enriched[0]
