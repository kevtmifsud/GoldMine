"""Supabase (PostgreSQL) implementation of the DataAccessProvider interface."""
from __future__ import annotations

import math
from typing import Any

from app.data_access.db import get_sync_conn
from app.data_access.interfaces import DataAccessProvider
from app.data_access.models import DatasetInfo, FilterParams, PaginatedResponse
from app.exceptions import DataAccessError, NotFoundError
from app.logging_config import get_logger

logger = get_logger(__name__)

# Hard-coded dataset metadata (replaces datasets.csv)
_DATASETS: list[DatasetInfo] = [
    DatasetInfo(dataset_id="DS-001", name="stocks", display_name="Stocks",
                description="Core stock universe with fundamentals",
                record_count=0, id_field="ticker", category="market_data"),
    DatasetInfo(dataset_id="DS-002", name="people", display_name="People",
                description="Corporate officers, executives, and analysts",
                record_count=0, id_field="person_id", category="contacts"),
    DatasetInfo(dataset_id="DS-003", name="sectors", display_name="Sectors",
                description="Sector and industry taxonomy",
                record_count=0, id_field="sector", category="reference"),
    DatasetInfo(dataset_id="DS-004", name="watchlists", display_name="Watchlists",
                description="Portfolio manager watchlists",
                record_count=0, id_field="watchlist_id", category="portfolio"),
    DatasetInfo(dataset_id="DS-005", name="meetings", display_name="Meeting Notes",
                description="Research meeting records",
                record_count=0, id_field="meeting_id", category="research"),
    DatasetInfo(dataset_id="DS-006", name="ratings", display_name="Analyst Ratings",
                description="Internal analyst ratings and targets",
                record_count=0, id_field="rating_id", category="research"),
    DatasetInfo(dataset_id="DS-007", name="portfolios", display_name="Portfolios",
                description="Portfolio holdings and allocations",
                record_count=0, id_field="portfolio_id", category="portfolio"),
    DatasetInfo(dataset_id="DS-008", name="events", display_name="Corporate Events",
                description="Earnings calls, conferences, filings",
                record_count=0, id_field="event_id", category="market_data"),
    DatasetInfo(dataset_id="DS-009", name="macro", display_name="Macro Indicators",
                description="Macroeconomic data points",
                record_count=0, id_field="indicator_id", category="market_data"),
    DatasetInfo(dataset_id="DS-012", name="portfolio_trades", display_name="Trades",
                description="Portfolio trade history",
                record_count=0, id_field="ticker", category="portfolio"),
    DatasetInfo(dataset_id="DS-013", name="sec_filings", display_name="SEC Filings",
                description="SEC filing records for tracked companies",
                record_count=0, id_field="symbol", category="compliance"),
    DatasetInfo(dataset_id="DS-014", name="transcripts_list", display_name="Transcripts",
                description="Available earnings call transcript listing",
                record_count=0, id_field="symbol", category="market_data"),
]

# Dataset name → primary-key / id field
_ID_FIELDS: dict[str, str] = {ds.name: ds.id_field for ds in _DATASETS}

# Datasets that have a real table in Supabase
_TABLE_DATASETS: set[str] = {
    "stocks", "people", "portfolios", "portfolio_trades",
    "stock_history", "stock_betas", "earnings_calendar",
    "sec_filings", "transcripts_list",
}

# Large columns to exclude from list queries (fetched separately via dedicated endpoints)
_EXCLUDE_COLUMNS: dict[str, set[str]] = {
    "transcripts_list": {"transcripts"},
}

# Text columns per table used for ILIKE search
_TEXT_COLUMNS: dict[str, list[str]] = {
    "stocks": ["ticker", "company_name", "sector", "industry", "exchange", "country"],
    "people": ["person_id", "name", "title", "organization", "type", "tickers"],
    "portfolios": ["portfolio_id", "name", "strategy", "status"],
    "portfolio_trades": ["ticker", "action", "portfolio", "side"],
    "stock_betas": ["ticker"],
    "earnings_calendar": ["ticker"],
    "sec_filings": ["symbol", "company_name", "form_type", "form_type_description"],
    "transcripts_list": ["symbol", "transcripts_id"],
}


class SupabaseDataAccessProvider(DataAccessProvider):
    """Query Supabase tables via psycopg2 (synchronous)."""

    def list_datasets(self) -> list[DatasetInfo]:
        conn = get_sync_conn()
        refreshed: list[DatasetInfo] = []
        for ds in _DATASETS:
            if ds.name in _TABLE_DATASETS:
                try:
                    cur = conn.cursor()
                    cur.execute(f"SELECT COUNT(*) FROM {ds.name}")  # noqa: S608
                    count = cur.fetchone()[0]
                    cur.close()
                    refreshed.append(ds.model_copy(update={"record_count": count}))
                except Exception:
                    refreshed.append(ds)
            else:
                refreshed.append(ds)
        return refreshed

    def query(self, dataset: str, params: FilterParams) -> PaginatedResponse:
        if dataset not in _TABLE_DATASETS:
            return PaginatedResponse(
                data=[], page=1, page_size=params.page_size,
                total_records=0, total_pages=1, has_next=False, has_previous=False,
            )

        conn = get_sync_conn()
        cur = conn.cursor()

        where_clauses: list[str] = []
        values: list[Any] = []

        # Exact filters
        for field, value in params.filters.items():
            where_clauses.append(f"LOWER(CAST({_ident(field)} AS TEXT)) = LOWER(%s)")
            values.append(value)

        # Full-text search across text columns
        if params.search:
            text_cols = _TEXT_COLUMNS.get(dataset, [])
            if text_cols:
                or_parts = [f"CAST({_ident(c)} AS TEXT) ILIKE %s" for c in text_cols]
                where_clauses.append(f"({' OR '.join(or_parts)})")
                pattern = f"%{params.search}%"
                values.extend([pattern] * len(text_cols))

        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        # Count total matching rows
        count_sql = f"SELECT COUNT(*) FROM {dataset}{where_sql}"  # noqa: S608
        cur.execute(count_sql, values)
        total = cur.fetchone()[0]

        # Sort
        order_sql = ""
        if params.sort_by:
            direction = "DESC" if params.sort_order == "desc" else "ASC"
            order_sql = f" ORDER BY {_ident(params.sort_by)} {direction}"

        # Pagination
        from app.config.settings import settings
        page_size = min(params.page_size, settings.MAX_PAGE_SIZE)
        total_pages = max(1, math.ceil(total / page_size))
        page = min(params.page, total_pages)
        offset = (page - 1) * page_size

        # Determine column selection (exclude large blob columns from list queries)
        excluded = _EXCLUDE_COLUMNS.get(dataset)
        if excluded:
            # Discover actual columns from the table, then exclude the large ones
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = %s ORDER BY ordinal_position",
                (dataset,),
            )
            all_cols = [r[0] for r in cur.fetchall()]
            select_cols = ", ".join(_ident(c) for c in all_cols if c not in excluded)
        else:
            select_cols = "*"

        data_sql = (
            f"SELECT {select_cols} FROM {dataset}{where_sql}{order_sql}"  # noqa: S608
            f" LIMIT %s OFFSET %s"
        )
        cur.execute(data_sql, values + [page_size, offset])
        columns = [desc[0] for desc in cur.description]
        rows = [dict(zip(columns, row)) for row in cur.fetchall()]
        cur.close()

        # Convert non-string values to strings to match CSV provider behavior
        str_rows = [_stringify_row(r) for r in rows]

        return PaginatedResponse(
            data=str_rows,
            page=page,
            page_size=page_size,
            total_records=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        )

    def get_record(self, dataset: str, record_id: str) -> dict[str, Any] | None:
        if dataset not in _TABLE_DATASETS:
            return None

        id_field = _ID_FIELDS.get(dataset)
        if not id_field:
            return None

        conn = get_sync_conn()
        cur = conn.cursor()
        sql = f"SELECT * FROM {dataset} WHERE {_ident(id_field)} = %s LIMIT 1"  # noqa: S608
        cur.execute(sql, (record_id,))
        row = cur.fetchone()
        if row is None:
            cur.close()
            return None

        columns = [desc[0] for desc in cur.description]
        cur.close()
        return _stringify_row(dict(zip(columns, row)))


def _ident(name: str) -> str:
    """Sanitise a column/table identifier to prevent SQL injection."""
    clean = "".join(c for c in name if c.isalnum() or c == "_")
    return f'"{clean}"'


def _stringify_row(row: dict[str, Any]) -> dict[str, str]:
    """Convert all values to strings (matching CSV provider output)."""
    out: dict[str, str] = {}
    for k, v in row.items():
        if v is None:
            out[k] = ""
        else:
            out[k] = str(v)
    return out
