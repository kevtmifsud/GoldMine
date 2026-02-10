from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.data_access.factory import get_data_provider
from app.data_access.models import DatasetInfo, FilterParams, PaginatedResponse
from app.exceptions import NotFoundError

router = APIRouter(prefix="/api/data", tags=["data"])

_KNOWN_PARAMS = {"page", "page_size", "sort_by", "sort_order", "search"}


@router.get("/")
async def list_datasets() -> list[DatasetInfo]:
    provider = get_data_provider()
    return provider.list_datasets()


@router.get("/{dataset}")
async def query_dataset(
    request: Request,
    dataset: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
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
    return provider.query(dataset, params)


@router.get("/{dataset}/{record_id}")
async def get_record(dataset: str, record_id: str) -> dict:
    provider = get_data_provider()
    record = provider.get_record(dataset, record_id)
    if record is None:
        raise NotFoundError(f"Record '{record_id}' not found in '{dataset}'")
    return record
