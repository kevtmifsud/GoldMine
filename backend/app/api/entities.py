from __future__ import annotations

import math
from typing import Any

from fastapi import APIRouter, Query, Request

from app.api.entity_models import (
    ChartConfig,
    ColumnConfig,
    EntityCandidate,
    EntityDetail,
    EntityField,
    EntityResolution,
    FilterDefinition,
    FilterOption,
    WidgetConfig,
)
from app.data_access.factory import get_data_provider
from app.data_access.models import FilterParams, PaginatedResponse
from app.exceptions import NotFoundError
from app.logging_config import get_logger
from app.object_storage.factory import get_storage_provider

logger = get_logger(__name__)

router = APIRouter(prefix="/api/entities", tags=["entities"])


# ---------------------------------------------------------------------------
# Resolution endpoint
# ---------------------------------------------------------------------------

@router.get("/resolve")
async def resolve_entity(q: str = Query(..., min_length=1)) -> EntityResolution:
    provider = get_data_provider()
    query = q.strip()
    query_lower = query.lower()

    # 1. Exact ticker match (case-insensitive)
    stocks = provider.query("stocks", FilterParams(page=1, page_size=200)).data
    for stock in stocks:
        if stock.get("ticker", "").lower() == query_lower:
            return EntityResolution(
                resolved=True,
                entity_type="stock",
                entity_id=stock["ticker"],
                display_name=f"{stock['company_name']} ({stock['ticker']})",
            )

    # 2. Exact person_id match (case-insensitive)
    people = provider.query("people", FilterParams(page=1, page_size=200)).data
    for person in people:
        if person.get("person_id", "").lower() == query_lower:
            return EntityResolution(
                resolved=True,
                entity_type="person",
                entity_id=person["person_id"],
                display_name=person["name"],
            )

    # 3. Exact dataset name match (case-insensitive)
    datasets = provider.list_datasets()
    for ds in datasets:
        if ds.name.lower() == query_lower:
            return EntityResolution(
                resolved=True,
                entity_type="dataset",
                entity_id=ds.name,
                display_name=ds.display_name,
            )

    # 4-6. Fuzzy matching
    candidates: list[EntityCandidate] = []

    # Fuzzy: company_name contains query
    for stock in stocks:
        if query_lower in stock.get("company_name", "").lower():
            candidates.append(EntityCandidate(
                entity_type="stock",
                entity_id=stock["ticker"],
                display_name=f"{stock['company_name']} ({stock['ticker']})",
            ))

    # Fuzzy: person name contains query
    for person in people:
        if query_lower in person.get("name", "").lower():
            candidates.append(EntityCandidate(
                entity_type="person",
                entity_id=person["person_id"],
                display_name=person["name"],
            ))

    # Fuzzy: dataset display_name contains query
    for ds in datasets:
        if query_lower in ds.display_name.lower():
            candidates.append(EntityCandidate(
                entity_type="dataset",
                entity_id=ds.name,
                display_name=ds.display_name,
            ))

    # 7. Single fuzzy match → resolved
    if len(candidates) == 1:
        c = candidates[0]
        return EntityResolution(
            resolved=True,
            entity_type=c.entity_type,
            entity_id=c.entity_id,
            display_name=c.display_name,
        )

    # 8. Multiple fuzzy matches → disambiguation
    if len(candidates) > 1:
        return EntityResolution(
            resolved=False,
            message="Multiple matches found",
            candidates=candidates,
        )

    # 9. No matches
    return EntityResolution(resolved=False, message="No results")


# ---------------------------------------------------------------------------
# Entity detail endpoint
# ---------------------------------------------------------------------------

@router.get("/{entity_type}/{entity_id}")
async def get_entity_detail(
    request: Request,
    entity_type: str,
    entity_id: str,
    view_id: str | None = Query(default=None),
) -> EntityDetail:
    if entity_type == "stock":
        detail = _build_stock_detail(entity_id)
    elif entity_type == "person":
        detail = _build_person_detail(entity_id)
    elif entity_type == "dataset":
        detail = _build_dataset_detail(entity_id)
    else:
        raise NotFoundError(f"Unknown entity type: {entity_type}")

    if view_id:
        detail = _apply_view_overrides(detail, view_id, request.state.user.username)

    return detail


def _build_stock_detail(ticker: str) -> EntityDetail:
    provider = get_data_provider()
    record = provider.get_record("stocks", ticker)
    if record is None:
        raise NotFoundError(f"Stock '{ticker}' not found")

    header_fields = [
        EntityField(label="Ticker", value=record.get("ticker"), format="text"),
        EntityField(label="Company", value=record.get("company_name"), format="text"),
        EntityField(label="Sector", value=record.get("sector"), format="text"),
        EntityField(label="Industry", value=record.get("industry"), format="text"),
        EntityField(label="Price", value=record.get("price"), format="currency"),
        EntityField(label="Market Cap ($B)", value=record.get("market_cap_b"), format="number"),
        EntityField(label="P/E Ratio", value=record.get("pe_ratio"), format="number"),
        EntityField(label="Dividend Yield", value=record.get("dividend_yield"), format="percent"),
        EntityField(label="52W High", value=record.get("52w_high"), format="currency"),
        EntityField(label="52W Low", value=record.get("52w_low"), format="currency"),
        EntityField(label="EPS", value=record.get("eps"), format="currency"),
        EntityField(label="Exchange", value=record.get("exchange"), format="text"),
    ]

    widgets = [
        WidgetConfig(
            widget_id="price_vs_peers",
            title="Price vs Sector Peers",
            endpoint=f"/api/entities/stock/{ticker}/peers",
            widget_type="chart",
            chart_config=ChartConfig(
                chart_type="bar",
                x_key="ticker",
                y_key="market_cap_b",
                x_label="Ticker",
                y_label="Market Cap ($B)",
            ),
            columns=[],
        ),
        WidgetConfig(
            widget_id="related_people",
            title="Related People",
            endpoint=f"/api/entities/stock/{ticker}/people",
            columns=[
                ColumnConfig(key="name", label="Name"),
                ColumnConfig(key="title", label="Title"),
                ColumnConfig(key="organization", label="Organization"),
                ColumnConfig(key="type", label="Type"),
            ],
            filter_definitions=[
                FilterDefinition(
                    field="type",
                    label="Type",
                    options=[
                        FilterOption(value="executive", label="Executive"),
                        FilterOption(value="analyst", label="Analyst"),
                    ],
                ),
            ],
            client_filterable_columns=["name", "organization"],
        ),
        WidgetConfig(
            widget_id="related_files",
            title="Related Files",
            endpoint=f"/api/entities/stock/{ticker}/files",
            columns=[
                ColumnConfig(key="filename", label="Filename"),
                ColumnConfig(key="type", label="Type"),
                ColumnConfig(key="date", label="Date"),
                ColumnConfig(key="description", label="Description"),
            ],
            filter_definitions=[
                FilterDefinition(
                    field="type",
                    label="Type",
                    options=[
                        FilterOption(value="transcript", label="Transcript"),
                        FilterOption(value="report", label="Report"),
                        FilterOption(value="data_export", label="Data Export"),
                        FilterOption(value="audio", label="Audio"),
                    ],
                ),
            ],
        ),
    ]

    return EntityDetail(
        entity_type="stock",
        entity_id=ticker,
        display_name=f"{record['company_name']} ({ticker})",
        header_fields=header_fields,
        widgets=widgets,
    )


def _build_person_detail(person_id: str) -> EntityDetail:
    provider = get_data_provider()
    record = provider.get_record("people", person_id)
    if record is None:
        raise NotFoundError(f"Person '{person_id}' not found")

    header_fields = [
        EntityField(label="Person ID", value=record.get("person_id"), format="text"),
        EntityField(label="Name", value=record.get("name"), format="text"),
        EntityField(label="Title", value=record.get("title"), format="text"),
        EntityField(label="Organization", value=record.get("organization"), format="text"),
        EntityField(label="Type", value=record.get("type"), format="text"),
    ]

    widgets = [
        WidgetConfig(
            widget_id="coverage_by_sector",
            title="Coverage by Sector",
            endpoint=f"/api/entities/person/{person_id}/coverage-sectors",
            widget_type="chart",
            chart_config=ChartConfig(
                chart_type="bar",
                x_key="sector",
                y_key="count",
                x_label="Sector",
                y_label="Stocks Covered",
            ),
            columns=[],
        ),
        WidgetConfig(
            widget_id="covered_stocks",
            title="Covered Stocks",
            endpoint=f"/api/entities/person/{person_id}/stocks",
            columns=[
                ColumnConfig(key="ticker", label="Ticker"),
                ColumnConfig(key="company_name", label="Company"),
                ColumnConfig(key="sector", label="Sector"),
                ColumnConfig(key="price", label="Price", format="currency"),
                ColumnConfig(key="market_cap_b", label="Market Cap ($B)", format="number"),
                ColumnConfig(key="pe_ratio", label="P/E Ratio", format="number"),
            ],
            filter_definitions=[
                FilterDefinition(
                    field="sector",
                    label="Sector",
                    options=_get_sector_options(),
                ),
            ],
            client_filterable_columns=["ticker", "company_name"],
        ),
    ]

    return EntityDetail(
        entity_type="person",
        entity_id=person_id,
        display_name=record["name"],
        header_fields=header_fields,
        widgets=widgets,
    )


def _build_dataset_detail(dataset_name: str) -> EntityDetail:
    provider = get_data_provider()

    # Find dataset metadata
    datasets = provider.list_datasets()
    ds_meta = None
    for ds in datasets:
        if ds.name.lower() == dataset_name.lower():
            ds_meta = ds
            break
    if ds_meta is None:
        raise NotFoundError(f"Dataset '{dataset_name}' not found")

    header_fields = [
        EntityField(label="Dataset ID", value=ds_meta.dataset_id, format="text"),
        EntityField(label="Name", value=ds_meta.display_name, format="text"),
        EntityField(label="Description", value=ds_meta.description, format="text"),
        EntityField(label="Record Count", value=str(ds_meta.record_count), format="number"),
        EntityField(label="Category", value=ds_meta.category, format="text"),
    ]

    # Dynamically derive columns from CSV headers
    columns: list[ColumnConfig] = []
    if ds_meta.record_count > 0:
        try:
            result = provider.query(ds_meta.name, FilterParams(page=1, page_size=1))
            if result.data:
                for key in result.data[0].keys():
                    columns.append(ColumnConfig(key=key, label=key.replace("_", " ").title()))
        except Exception:
            pass

    widgets: list[WidgetConfig] = []
    if columns:
        filter_defs = _get_dataset_filter_definitions(ds_meta.name)
        widgets.append(
            WidgetConfig(
                widget_id="dataset_contents",
                title=f"{ds_meta.display_name} Contents",
                endpoint=f"/api/data/{ds_meta.name}",
                columns=columns,
                default_page_size=20,
                filter_definitions=filter_defs,
            ),
        )
        # Add distribution chart for stocks dataset
        if ds_meta.name.lower() == "stocks":
            widgets.append(
                WidgetConfig(
                    widget_id="sector_distribution",
                    title="Sector Distribution",
                    endpoint=f"/api/entities/dataset/{ds_meta.name}/distribution?group_by=sector",
                    widget_type="chart",
                    chart_config=ChartConfig(
                        chart_type="bar",
                        x_key="sector",
                        y_key="count",
                        x_label="Sector",
                        y_label="Number of Stocks",
                    ),
                    columns=[],
                ),
            )

    return EntityDetail(
        entity_type="dataset",
        entity_id=ds_meta.name,
        display_name=ds_meta.display_name,
        header_fields=header_fields,
        widgets=widgets,
    )


# ---------------------------------------------------------------------------
# Widget data endpoints
# ---------------------------------------------------------------------------

@router.get("/stock/{ticker}/people")
async def get_stock_people(
    request: Request,
    ticker: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=200),
    sort_by: str | None = Query(default=None),
    sort_order: str = Query(default="asc", pattern="^(asc|desc)$"),
) -> PaginatedResponse:
    provider = get_data_provider()
    # Verify stock exists
    stock = provider.get_record("stocks", ticker)
    if stock is None:
        raise NotFoundError(f"Stock '{ticker}' not found")

    # Get all people and filter by ticker in their semicolon-separated tickers field
    all_people = provider.query("people", FilterParams(page=1, page_size=200)).data
    ticker_upper = ticker.upper()
    filtered = [
        p for p in all_people
        if ticker_upper in [t.strip() for t in p.get("tickers", "").split(";")]
    ]

    return _paginate(filtered, page, page_size, sort_by, sort_order, _extract_filters(request))


@router.get("/stock/{ticker}/files")
async def get_stock_files(
    request: Request,
    ticker: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=200),
    sort_by: str | None = Query(default=None),
    sort_order: str = Query(default="asc", pattern="^(asc|desc)$"),
) -> PaginatedResponse:
    provider = get_data_provider()
    # Verify stock exists
    stock = provider.get_record("stocks", ticker)
    if stock is None:
        raise NotFoundError(f"Stock '{ticker}' not found")

    # Get all files from manifest and filter by ticker
    storage = get_storage_provider()
    all_files = storage.list_files()
    ticker_upper = ticker.upper()
    filtered = [
        {
            "file_id": f.file_id,
            "filename": f.filename,
            "type": f.type,
            "date": f.date,
            "description": f.description,
        }
        for f in all_files
        if ticker_upper in f.tickers
    ]

    return _paginate(filtered, page, page_size, sort_by, sort_order, _extract_filters(request))


@router.get("/person/{person_id}/stocks")
async def get_person_stocks(
    request: Request,
    person_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=200),
    sort_by: str | None = Query(default=None),
    sort_order: str = Query(default="asc", pattern="^(asc|desc)$"),
) -> PaginatedResponse:
    provider = get_data_provider()

    # Get the person record
    person = provider.get_record("people", person_id)
    if person is None:
        raise NotFoundError(f"Person '{person_id}' not found")

    # Parse their tickers and look up each stock
    tickers_str = person.get("tickers", "")
    ticker_list = [t.strip() for t in tickers_str.split(";") if t.strip()]

    stock_records: list[dict[str, Any]] = []
    for ticker in ticker_list:
        stock = provider.get_record("stocks", ticker)
        if stock:
            stock_records.append(stock)

    return _paginate(stock_records, page, page_size, sort_by, sort_order, _extract_filters(request))


# ---------------------------------------------------------------------------
# Chart data endpoints
# ---------------------------------------------------------------------------

@router.get("/stock/{ticker}/peers")
async def get_stock_peers(ticker: str) -> PaginatedResponse:
    provider = get_data_provider()
    stock = provider.get_record("stocks", ticker)
    if stock is None:
        raise NotFoundError(f"Stock '{ticker}' not found")

    sector = stock.get("sector", "")
    all_stocks = provider.query("stocks", FilterParams(page=1, page_size=200)).data
    peers = [s for s in all_stocks if s.get("sector") == sector]
    peers.sort(key=lambda s: float(s.get("market_cap_b", 0) or 0), reverse=True)

    return _paginate(peers, 1, 200, None, "asc")


@router.get("/person/{person_id}/coverage-sectors")
async def get_person_coverage_sectors(person_id: str) -> PaginatedResponse:
    provider = get_data_provider()
    person = provider.get_record("people", person_id)
    if person is None:
        raise NotFoundError(f"Person '{person_id}' not found")

    tickers_str = person.get("tickers", "")
    ticker_list = [t.strip() for t in tickers_str.split(";") if t.strip()]

    sector_counts: dict[str, int] = {}
    for ticker in ticker_list:
        stock = provider.get_record("stocks", ticker)
        if stock:
            sector = stock.get("sector", "Unknown")
            sector_counts[sector] = sector_counts.get(sector, 0) + 1

    data = [{"sector": s, "count": str(c)} for s, c in sorted(sector_counts.items())]
    return _paginate(data, 1, 200, None, "asc")


@router.get("/dataset/{dataset_name}/distribution")
async def get_dataset_distribution(
    dataset_name: str,
    group_by: str = Query(..., min_length=1),
) -> PaginatedResponse:
    provider = get_data_provider()

    # Verify dataset exists
    datasets = provider.list_datasets()
    ds_meta = None
    for ds in datasets:
        if ds.name.lower() == dataset_name.lower():
            ds_meta = ds
            break
    if ds_meta is None:
        raise NotFoundError(f"Dataset '{dataset_name}' not found")

    all_data = provider.query(ds_meta.name, FilterParams(page=1, page_size=200)).data
    counts: dict[str, int] = {}
    for row in all_data:
        val = str(row.get(group_by, "Unknown") or "Unknown")
        counts[val] = counts.get(val, 0) + 1

    data = [{group_by: k, "count": str(v)} for k, v in sorted(counts.items())]
    return _paginate(data, 1, 200, None, "asc")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sort_key(value: Any) -> Any:
    """Try to sort numerically, fall back to string."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return str(value).lower()


def _apply_view_overrides(detail: EntityDetail, view_id: str, username: str) -> EntityDetail:
    from app.views.factory import get_views_provider

    provider = get_views_provider()
    view = provider.get_view(view_id)
    if view is None:
        raise NotFoundError(f"View '{view_id}' not found")
    if view.owner != username and not view.is_shared:
        raise NotFoundError(f"View '{view_id}' not found")
    if view.entity_type != detail.entity_type or view.entity_id != detail.entity_id:
        raise NotFoundError(f"View '{view_id}' does not belong to this entity")

    for override in view.widget_overrides:
        for widget in detail.widgets:
            if widget.widget_id == override.widget_id:
                if override.visible_columns is not None:
                    for col in widget.columns:
                        col.visible = col.key in override.visible_columns
                if override.page_size is not None:
                    widget.default_page_size = override.page_size
                if override.server_filters:
                    widget.initial_filters = override.server_filters
                    widget.has_overrides = True
                if override.sort_by is not None:
                    widget.initial_sort_by = override.sort_by
                    widget.has_overrides = True
                if override.sort_order is not None:
                    widget.initial_sort_order = override.sort_order
                    widget.has_overrides = True
                break

    detail.active_view_id = view.view_id
    detail.active_view_name = view.name
    return detail


_KNOWN_PARAMS = {"page", "page_size", "sort_by", "sort_order", "search"}


def _extract_filters(request: Request) -> dict[str, str]:
    return {k: v for k, v in request.query_params.items() if k not in _KNOWN_PARAMS}


def _get_sector_options() -> list[FilterOption]:
    provider = get_data_provider()
    stocks = provider.query("stocks", FilterParams(page=1, page_size=200)).data
    sectors = sorted({s.get("sector", "") for s in stocks if s.get("sector")})
    return [FilterOption(value=s, label=s) for s in sectors]


def _get_exchange_options() -> list[FilterOption]:
    provider = get_data_provider()
    stocks = provider.query("stocks", FilterParams(page=1, page_size=200)).data
    exchanges = sorted({s.get("exchange", "") for s in stocks if s.get("exchange")})
    return [FilterOption(value=e, label=e) for e in exchanges]


def _get_dataset_filter_definitions(dataset_name: str) -> list[FilterDefinition]:
    name_lower = dataset_name.lower()
    if name_lower == "stocks":
        return [
            FilterDefinition(
                field="sector", label="Sector", options=_get_sector_options(),
            ),
            FilterDefinition(
                field="exchange", label="Exchange", options=_get_exchange_options(),
            ),
        ]
    elif name_lower == "people":
        return [
            FilterDefinition(
                field="type",
                label="Type",
                options=[
                    FilterOption(value="analyst", label="Analyst"),
                    FilterOption(value="executive", label="Executive"),
                ],
            ),
        ]
    return []


def _paginate(
    data: list[dict[str, Any]],
    page: int,
    page_size: int,
    sort_by: str | None,
    sort_order: str,
    filters: dict[str, str] | None = None,
) -> PaginatedResponse:
    # Apply filters (exact match)
    if filters:
        for field, value in filters.items():
            data = [r for r in data if str(r.get(field, "")).lower() == value.lower()]

    # Sort
    if sort_by and data:
        reverse = sort_order == "desc"
        try:
            data.sort(key=lambda r: _sort_key(r.get(sort_by, "")), reverse=reverse)
        except Exception:
            pass

    total = len(data)
    total_pages = max(1, math.ceil(total / page_size))
    page = min(page, total_pages)

    start = (page - 1) * page_size
    end = start + page_size
    page_data = data[start:end]

    return PaginatedResponse(
        data=page_data,
        page=page,
        page_size=page_size,
        total_records=total,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_previous=page > 1,
    )
