from __future__ import annotations

import bisect
import math
from typing import Any

from fastapi import APIRouter, Query, Request

from app.api.entity_models import (
    BarConfig,
    ChartConfig,
    ColumnConfig,
    EntityCandidate,
    EntityDetail,
    EntityField,
    EntityResolution,
    FilterDefinition,
    FilterOption,
    SecondaryLine,
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
    stocks = provider.query("stocks", FilterParams(page=1, page_size=600)).data
    for stock in stocks:
        if stock.get("ticker", "").lower() == query_lower:
            return EntityResolution(
                resolved=True,
                entity_type="stock",
                entity_id=stock["ticker"],
                display_name=f"{stock['company_name']} ({stock['ticker']})",
            )

    # 2. Exact person_id match (case-insensitive)
    people = _get_all_people(provider)
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

    # 3b. Exact portfolio name match (case-insensitive)
    portfolios = provider.query("portfolios", FilterParams(page=1, page_size=100)).data
    for pf in portfolios:
        if pf.get("name", "").lower() == query_lower:
            return EntityResolution(
                resolved=True,
                entity_type="portfolio",
                entity_id=pf["name"],
                display_name=f"{pf['name']} Portfolio",
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

    # Fuzzy: portfolio name contains query
    for pf in portfolios:
        if query_lower in pf.get("name", "").lower():
            candidates.append(EntityCandidate(
                entity_type="portfolio",
                entity_id=pf["name"],
                display_name=f"{pf['name']} Portfolio",
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
# Autocomplete endpoint
# ---------------------------------------------------------------------------

@router.get("/autocomplete")
async def autocomplete_entities(
    q: str = Query(..., min_length=1),
    limit: int = Query(15, ge=1, le=50),
) -> list[EntityCandidate]:
    provider = get_data_provider()
    query_lower = q.strip().lower()

    # Collect up to `limit` matches from each category independently
    stock_matches: list[EntityCandidate] = []
    people_matches: list[EntityCandidate] = []

    stocks = provider.query("stocks", FilterParams(page=1, page_size=600)).data
    for stock in stocks:
        ticker = stock.get("ticker", "")
        name = stock.get("company_name", "")
        if query_lower in ticker.lower() or query_lower in name.lower():
            stock_matches.append(EntityCandidate(
                entity_type="stock",
                entity_id=ticker,
                display_name=f"{name} ({ticker})",
            ))
            if len(stock_matches) >= limit:
                break

    people = _get_all_people(provider)
    for person in people:
        name = person.get("name", "")
        if query_lower in name.lower():
            people_matches.append(EntityCandidate(
                entity_type="person",
                entity_id=person.get("person_id", ""),
                display_name=name,
            ))
            if len(people_matches) >= limit:
                break

    portfolio_matches: list[EntityCandidate] = []
    portfolios = provider.query("portfolios", FilterParams(page=1, page_size=100)).data
    for pf in portfolios:
        name = pf.get("name", "")
        if query_lower in name.lower():
            portfolio_matches.append(EntityCandidate(
                entity_type="portfolio",
                entity_id=name,
                display_name=f"{name} Portfolio",
            ))
            if len(portfolio_matches) >= limit:
                break

    # Return stocks first, then people, then portfolios — each capped at `limit`
    return stock_matches + people_matches + portfolio_matches


# ---------------------------------------------------------------------------
# Portfolio comparison endpoint (must be before the generic /{entity_type}/…)
# ---------------------------------------------------------------------------

@router.get("/portfolio/comparison")
async def get_portfolio_comparison(
    start_date: str | None = Query(default=None),
) -> dict[str, Any]:
    """Return merged daily cumulative-return series for all portfolios + S&P 500 benchmark."""
    from app.data_access.db import get_sync_conn
    provider = get_data_provider()
    portfolios = provider.query("portfolios", FilterParams(page=1, page_size=100)).data
    portfolio_names = [pf["name"] for pf in portfolios]

    conn = get_sync_conn()
    cur = conn.cursor()

    # Build cumulative PnL series per portfolio from daily_pnl
    portfolio_pct: dict[str, dict[str, float]] = {}
    portfolio_dollars: dict[str, dict[str, float]] = {}
    portfolio_nav: dict[str, dict[str, float]] = {}
    earliest_date: str | None = None

    for name in portfolio_names:
        cur.execute("""
            SELECT date,
                   SUM(market_value) AS mv,
                   SUM(unrealized_pnl + realized_pnl) AS total_pnl
            FROM daily_pnl
            WHERE portfolio = %s
            GROUP BY date
            ORDER BY date
        """, (name,))
        rows = cur.fetchall()
        if not rows:
            portfolio_pct[name] = {}
            portfolio_dollars[name] = {}
            portfolio_nav[name] = {}
            continue

        initial_capital = float(rows[0][1])  # market_value on first date
        pct_map: dict[str, float] = {}
        dollar_map: dict[str, float] = {}
        nav_map: dict[str, float] = {}
        for date_val, mv, total_pnl in rows:
            d = str(date_val)
            cum_pnl = float(total_pnl)
            cum_pct = (cum_pnl / initial_capital * 100) if initial_capital else 0.0
            pct_map[d] = round(cum_pct, 2)
            dollar_map[d] = round(cum_pnl)
            nav_map[d] = round(initial_capital + cum_pnl)

        portfolio_pct[name] = pct_map
        portfolio_dollars[name] = dollar_map
        portfolio_nav[name] = nav_map
        first_date = str(rows[0][0])
        if earliest_date is None or first_date < earliest_date:
            earliest_date = first_date

    cur.close()

    # Compute S&P 500 equal-weight benchmark
    effective_start = start_date or earliest_date
    sp500: dict[str, float] = {}
    if effective_start:
        sp500 = _compute_sp500_equal_weight_returns(effective_start)

    # Merge into a single series keyed by date
    all_dates: set[str] = set()
    for dm in portfolio_pct.values():
        all_dates.update(dm.keys())
    all_dates.update(sp500.keys())

    sorted_dates = sorted(all_dates)

    # Compute baselines for re-baselining when start_date is provided
    baselines_pct: dict[str, float] = {}
    baselines_dollars: dict[str, float] = {}
    if start_date:
        sorted_dates = [d for d in sorted_dates if d >= start_date]
        for name in portfolio_names:
            pct_map = portfolio_pct.get(name, {})
            dollar_map = portfolio_dollars.get(name, {})
            bl_pct = bl_dollars = 0.0
            for d in sorted(pct_map.keys()):
                if d <= start_date:
                    bl_pct = pct_map[d]
                    bl_dollars = dollar_map.get(d, 0.0)
                else:
                    break
            baselines_pct[name] = bl_pct
            baselines_dollars[name] = bl_dollars

    series: list[dict[str, Any]] = []
    for date in sorted_dates:
        point: dict[str, Any] = {"date": date}
        for name in portfolio_names:
            if date in portfolio_pct.get(name, {}):
                point[name] = round(portfolio_pct[name][date] - baselines_pct.get(name, 0.0), 2)
                point[f"{name}_dollars"] = round(portfolio_dollars[name][date] - baselines_dollars.get(name, 0.0))
                point[f"{name}_mv"] = round(portfolio_nav.get(name, {}).get(date, 0.0))
        if date in sp500:
            point["S&P 500"] = round(sp500[date], 2)
        series.append(point)

    return {"series": series, "portfolios": portfolio_names}


@router.get("/portfolio/{name}/daily-pnl-by-group")
async def get_portfolio_daily_pnl_by_group(
    name: str,
    group_by: str = Query(default="sector"),
    start_date: str | None = Query(default=None),
) -> dict[str, Any]:
    """Return cumulative PnL broken down by sector or industry."""
    if group_by not in ("sector", "industry"):
        group_by = "sector"

    from app.data_access.db import get_sync_conn
    conn = get_sync_conn()
    cur = conn.cursor()

    group_col = "sector" if group_by == "sector" else "industry"
    cur.execute(f"""
        SELECT date, COALESCE({group_col}, 'Unknown') AS grp,
               SUM(unrealized_pnl + realized_pnl) AS pnl,
               SUM(market_value) AS mv
        FROM daily_pnl
        WHERE portfolio = %s
        GROUP BY date, grp
        ORDER BY date
    """, (name,))
    raw = cur.fetchall()
    cur.close()

    if not raw:
        return {"series": [], "groups": []}

    # Get initial gross MV for % denominator
    first_date = raw[0][0]
    initial_gross_mv = sum(float(r[3]) for r in raw if r[0] == first_date)

    # Build per-date points with group PnL
    from collections import OrderedDict
    date_points: OrderedDict[str, dict[str, Any]] = OrderedDict()
    all_groups: set[str] = set()

    for date_val, grp, pnl, mv in raw:
        d = str(date_val)
        if d not in date_points:
            date_points[d] = {"date": d, "Total": 0.0, "Total_dollars": 0.0}
        point = date_points[d]
        pnl_f = float(pnl)
        pnl_pct = (pnl_f / initial_gross_mv * 100) if initial_gross_mv else 0.0
        point[grp] = round(point.get(grp, 0.0) + pnl_pct, 2)
        point[f"{grp}_dollars"] = round(point.get(f"{grp}_dollars", 0.0) + pnl_f)
        point["Total"] = round(point["Total"] + pnl_pct, 2)
        point["Total_dollars"] = round(point["Total_dollars"] + pnl_f)
        all_groups.add(grp)

    series = list(date_points.values())

    # Filter and re-baseline when start_date is provided
    if start_date and series:
        baseline: dict[str, float] = {}
        for point in series:
            if point["date"] <= start_date:
                for key, val in point.items():
                    if key != "date":
                        baseline[key] = float(val)
            else:
                break

        filtered: list[dict[str, Any]] = []
        for point in series:
            if point["date"] < start_date:
                continue
            new_point: dict[str, Any] = {"date": point["date"]}
            for key, val in point.items():
                if key == "date":
                    continue
                new_point[key] = round(float(val) - baseline.get(key, 0.0), 2)
            filtered.append(new_point)
        series = filtered

    # Identify top 8 groups by absolute final cumulative PnL
    if series:
        last_point = series[-1]
        group_scores: list[tuple[str, float]] = []
        for key, val in last_point.items():
            if key in ("date", "Total") or key.endswith("_dollars"):
                continue
            group_scores.append((key, abs(float(val))))
        group_scores.sort(key=lambda x: x[1], reverse=True)
        top_groups = [g for g, _ in group_scores[:8]]
        other_groups = {g for g, _ in group_scores[8:]}

        if other_groups:
            for point in series:
                other_pct = 0.0
                other_dollars = 0.0
                for g in list(point.keys()):
                    if g in other_groups:
                        other_pct += point.pop(g, 0.0)
                    elif g.endswith("_dollars") and g[:-8] in other_groups:
                        other_dollars += point.pop(g, 0.0)
                if other_pct:
                    point["Other"] = round(other_pct, 2)
                if other_dollars:
                    point["Other_dollars"] = round(other_dollars)
            top_groups.append("Other")
    else:
        top_groups = []

    return {"series": series, "groups": top_groups}


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
    elif entity_type == "portfolio":
        detail = _build_portfolio_detail(entity_id)
    elif entity_type == "sector":
        detail = _build_sector_detail(entity_id)
    elif entity_type == "industry":
        detail = _build_industry_detail(entity_id)
    else:
        raise NotFoundError(f"Unknown entity type: {entity_type}")

    username = request.state.user.username
    if view_id:
        detail = _apply_view_overrides(detail, view_id, username)
    else:
        # Auto-apply user's default view for this entity if one exists
        from app.views.factory import get_views_provider
        default_view = get_views_provider().get_default_view(
            owner=username, entity_type=entity_type, entity_id=entity_id,
        )
        if default_view:
            detail = _apply_view_overrides(detail, default_view.view_id, username)

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
            widget_id="price_history",
            title="Price History",
            endpoint=f"/api/entities/stock/{ticker}/price-history",
            widget_type="chart",
            chart_config=ChartConfig(
                chart_type="line",
                x_key="date",
                y_key="close",
                x_label="Date",
                y_label="Close Price ($)",
                secondary_y_label="EPS ($)",
                secondary_lines=[
                    SecondaryLine(y_key="eps_estimate", label="EPS Estimate", color="#805ad5"),
                    SecondaryLine(y_key="eps_actual", label="EPS Actual", color="#38a169"),
                ],
            ),
            columns=[],
            default_page_size=5000,
            full_width=True,
        ),
        WidgetConfig(
            widget_id="valuation_vs_peers",
            title="Valuation vs Peers",
            endpoint=f"/api/entities/stock/{ticker}/peers",
            widget_type="chart",
            chart_config=ChartConfig(
                chart_type="bar",
                x_key="ticker",
                y_key="pe_ratio",
                x_label="Ticker",
                y_label="P/E Ratio",
            ),
            columns=[],
        ),
        WidgetConfig(
            widget_id="earnings_vs_peers",
            title="Earnings vs Peers",
            endpoint=f"/api/entities/stock/{ticker}/peers",
            widget_type="chart",
            chart_config=ChartConfig(
                chart_type="bar",
                x_key="ticker",
                y_key="eps",
                x_label="Ticker",
                y_label="EPS ($)",
            ),
            columns=[],
        ),
        WidgetConfig(
            widget_id="related_people",
            title="Officers & Executives",
            endpoint=f"/api/entities/stock/{ticker}/people",
            columns=[
                ColumnConfig(key="person_id", label="Person ID", visible=False),
                ColumnConfig(key="name", label="Name", entity_type="person", entity_id_field="person_id"),
                ColumnConfig(key="title", label="Title"),
                ColumnConfig(key="age", label="Age"),
                ColumnConfig(key="pay", label="Compensation", format="number"),
            ],
            client_filterable_columns=["name", "title"],
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
                ColumnConfig(key="ticker", label="Ticker", entity_type="stock"),
                ColumnConfig(key="company_name", label="Company", entity_type="stock", entity_id_field="ticker"),
                ColumnConfig(key="sector", label="Sector", entity_type="sector"),
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
    try:
        result = provider.query(ds_meta.name, FilterParams(page=1, page_size=1))
        if result.data:
            sample = result.data[0]
            for key in sample.keys():
                fmt = _infer_column_format(key, sample.get(key))
                columns.append(ColumnConfig(key=key, label=key.replace("_", " ").title(), format=fmt))
    except Exception:
        pass

    # Customise columns for transcripts_list: drop the raw transcript blob
    # and internal ID, add a "View Transcript" action button.
    if ds_meta.name.lower() == "transcripts_list":
        columns = [c for c in columns if c.key not in ("transcripts", "transcripts_id")]
        columns.append(
            ColumnConfig(
                key="_action",
                label="",
                format="transcript_viewer",
                sortable=False,
                visible=True,
            )
        )

    _annotate_entity_columns(ds_meta.name, columns)

    # Add joinable columns from related datasets (hidden by default)
    joins = _DATASET_JOINS.get(ds_meta.name, [])
    native_keys = {c.key for c in columns}
    for target_dataset, _src_key, target_key in joins:
        try:
            target_result = provider.query(target_dataset, FilterParams(page=1, page_size=1))
            if target_result.data:
                for key in target_result.data[0]:
                    if key in native_keys or key == target_key or key in _JOIN_EXCLUDE_COLUMNS:
                        continue
                    fmt = _infer_column_format(key, target_result.data[0].get(key))
                    columns.append(ColumnConfig(
                        key=key, label=key.replace("_", " ").title(),
                        format=fmt, visible=False,
                    ))
                    native_keys.add(key)
        except Exception:
            pass

    # Annotate joined columns with entity links from their source datasets
    for target_dataset, _, _ in joins:
        _annotate_entity_columns(target_dataset, columns)

    widgets: list[WidgetConfig] = []
    if columns:
        filter_defs = _get_dataset_filter_definitions(ds_meta.name)
        widgets.append(
            WidgetConfig(
                widget_id=f"dataset_contents_{ds_meta.name}",
                title=f"{ds_meta.display_name} Contents",
                endpoint=f"/api/data/{ds_meta.name}",
                columns=columns,
                default_page_size=1000,
                filter_definitions=filter_defs,
            ),
        )
    return EntityDetail(
        entity_type="dataset",
        entity_id=ds_meta.name,
        display_name=ds_meta.display_name,
        header_fields=header_fields,
        widgets=widgets,
    )


def _build_sector_detail(sector_name: str) -> EntityDetail:
    provider = get_data_provider()
    stocks = provider.query("stocks", FilterParams(page=1, page_size=600)).data
    sector_stocks = [s for s in stocks if s.get("sector", "").lower() == sector_name.lower()]
    if not sector_stocks:
        raise NotFoundError(f"Sector '{sector_name}' not found")

    # Use the canonical casing from the data
    canonical_name = sector_stocks[0]["sector"]
    industries = sorted({s.get("industry", "") for s in sector_stocks if s.get("industry")})
    total_market_cap = sum(float(s.get("market_cap_b") or 0) for s in sector_stocks)
    avg_pe = 0.0
    pe_stocks = [s for s in sector_stocks if s.get("pe_ratio")]
    if pe_stocks:
        avg_pe = sum(float(s["pe_ratio"]) for s in pe_stocks) / len(pe_stocks)

    header_fields = [
        EntityField(label="Sector", value=canonical_name, format="text"),
        EntityField(label="Stocks", value=str(len(sector_stocks)), format="number"),
        EntityField(label="Industries", value=str(len(industries)), format="number"),
        EntityField(label="Total Market Cap ($B)", value=f"{total_market_cap:.1f}", format="number"),
        EntityField(label="Avg P/E Ratio", value=f"{avg_pe:.1f}", format="number"),
    ]

    # Build columns matching the stocks dataset schema
    stock_columns = [
        ColumnConfig(key="ticker", label="Ticker", entity_type="stock"),
        ColumnConfig(key="company_name", label="Company", entity_type="stock", entity_id_field="ticker"),
        ColumnConfig(key="industry", label="Industry", entity_type="industry"),
        ColumnConfig(key="price", label="Price", format="currency"),
        ColumnConfig(key="market_cap_b", label="Market Cap ($B)", format="number"),
        ColumnConfig(key="pe_ratio", label="P/E Ratio", format="number"),
        ColumnConfig(key="dividend_yield", label="Dividend Yield", format="percent"),
        ColumnConfig(key="eps", label="EPS", format="currency"),
    ]

    widgets = [
        WidgetConfig(
            widget_id="sector_stocks",
            title=f"{canonical_name} Stocks",
            endpoint="/api/data/stocks",
            columns=stock_columns,
            default_page_size=100,
            initial_filters={"sector": canonical_name},
            client_filterable_columns=["ticker", "company_name"],
            filter_definitions=[
                FilterDefinition(
                    field="industry",
                    label="Industry",
                    options=[FilterOption(value=i, label=i) for i in industries],
                ),
            ],
        ),
    ]

    return EntityDetail(
        entity_type="sector",
        entity_id=canonical_name,
        display_name=f"{canonical_name} Sector",
        header_fields=header_fields,
        widgets=widgets,
    )


def _build_industry_detail(industry_name: str) -> EntityDetail:
    provider = get_data_provider()
    stocks = provider.query("stocks", FilterParams(page=1, page_size=600)).data
    industry_stocks = [s for s in stocks if s.get("industry", "").lower() == industry_name.lower()]
    if not industry_stocks:
        raise NotFoundError(f"Industry '{industry_name}' not found")

    # Use the canonical casing from the data
    canonical_name = industry_stocks[0]["industry"]
    sector = industry_stocks[0].get("sector", "")
    total_market_cap = sum(float(s.get("market_cap_b") or 0) for s in industry_stocks)
    avg_pe = 0.0
    pe_stocks = [s for s in industry_stocks if s.get("pe_ratio")]
    if pe_stocks:
        avg_pe = sum(float(s["pe_ratio"]) for s in pe_stocks) / len(pe_stocks)

    header_fields = [
        EntityField(label="Industry", value=canonical_name, format="text"),
        EntityField(label="Sector", value=sector, format="text"),
        EntityField(label="Stocks", value=str(len(industry_stocks)), format="number"),
        EntityField(label="Total Market Cap ($B)", value=f"{total_market_cap:.1f}", format="number"),
        EntityField(label="Avg P/E Ratio", value=f"{avg_pe:.1f}", format="number"),
    ]

    stock_columns = [
        ColumnConfig(key="ticker", label="Ticker", entity_type="stock"),
        ColumnConfig(key="company_name", label="Company", entity_type="stock", entity_id_field="ticker"),
        ColumnConfig(key="sector", label="Sector", entity_type="sector"),
        ColumnConfig(key="price", label="Price", format="currency"),
        ColumnConfig(key="market_cap_b", label="Market Cap ($B)", format="number"),
        ColumnConfig(key="pe_ratio", label="P/E Ratio", format="number"),
        ColumnConfig(key="dividend_yield", label="Dividend Yield", format="percent"),
        ColumnConfig(key="eps", label="EPS", format="currency"),
    ]

    widgets = [
        WidgetConfig(
            widget_id="industry_stocks",
            title=f"{canonical_name} Stocks",
            endpoint="/api/data/stocks",
            columns=stock_columns,
            default_page_size=100,
            initial_filters={"industry": canonical_name},
            client_filterable_columns=["ticker", "company_name"],
        ),
    ]

    return EntityDetail(
        entity_type="industry",
        entity_id=canonical_name,
        display_name=f"{canonical_name}",
        header_fields=header_fields,
        widgets=widgets,
    )


def _build_portfolio_detail(portfolio_name: str) -> EntityDetail:
    provider = get_data_provider()
    portfolios = provider.query("portfolios", FilterParams(page=1, page_size=100)).data
    record = None
    for pf in portfolios:
        if pf.get("name", "").lower() == portfolio_name.lower():
            record = pf
            break
    if record is None:
        raise NotFoundError(f"Portfolio '{portfolio_name}' not found")

    name = record["name"]

    # Portfolio summary from pre-calculated daily_pnl
    from app.data_access.db import get_sync_conn
    pnl_conn = get_sync_conn()
    pnl_cur = pnl_conn.cursor()
    pnl_cur.execute("""
        SELECT date FROM daily_pnl
        WHERE portfolio = %s
        ORDER BY date DESC LIMIT 1
    """, (name,))
    latest_row = pnl_cur.fetchone()
    if latest_row:
        pnl_cur.execute("""
            SELECT COUNT(*),
                   COALESCE(SUM(market_value), 0),
                   COALESCE(SUM(cost_basis), 0),
                   COALESCE(SUM(unrealized_pnl + realized_pnl), 0)
            FROM daily_pnl
            WHERE portfolio = %s AND date = %s
        """, (name, latest_row[0]))
        r = pnl_cur.fetchone()
        num_positions = r[0]
        total_market_value = float(r[1])
        total_cost = float(r[2])
        total_pnl = float(r[3])
    else:
        num_positions = 0
        total_market_value = 0.0
        total_cost = 0.0
        total_pnl = 0.0
    pnl_cur.close()
    pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0.0

    header_fields = [
        EntityField(label="Portfolio", value=name, format="text"),
        EntityField(label="Strategy", value=record.get("strategy"), format="text"),
        EntityField(label="AUM", value=record.get("aum"), format="currency"),
        EntityField(label="Positions", value=str(num_positions), format="number"),
        EntityField(label="Market Value", value=f"{total_market_value:,.0f}", format="text"),
        EntityField(label="Total Cost", value=f"{total_cost:,.0f}", format="text"),
        EntityField(label="Total PnL", value=f"{total_pnl:,.0f}", format="text"),
        EntityField(label="PnL %", value=f"{pnl_pct:.1f}%", format="text"),
        EntityField(label="Inception", value=record.get("inception_date"), format="text"),
        EntityField(label="Rebalance", value=record.get("rebalance_frequency"), format="text"),
        EntityField(label="Status", value=record.get("status"), format="text"),
    ]

    safe_name = name.replace(" ", "%20")
    widgets = [
        WidgetConfig(
            widget_id="daily_pnl",
            title="Daily PnL",
            endpoint=f"/api/entities/portfolio/{safe_name}/daily-pnl",
            widget_type="chart",
            chart_config=ChartConfig(
                chart_type="line",
                x_key="date",
                y_key="cumulative_pnl",
                x_label="Date",
                y_label="Cumulative PnL ($)",
                y_format="currency",
                y_key_alt="cumulative_pnl_pct",
                y_label_alt="Cumulative PnL (%)",
                y_format_alt="percent",
                secondary_y_label="Daily PnL ($)",
                secondary_y_label_alt="Daily PnL (%)",
                secondary_lines=[
                    SecondaryLine(
                        y_key="daily_pnl",
                        y_key_alt="daily_pnl_pct",
                        label="Daily PnL ($)",
                        label_alt="Daily PnL (%)",
                        color="#38a169",
                    ),
                ],
            ),
            columns=[],
            default_page_size=5000,
        ),
        WidgetConfig(
            widget_id="top_sectors",
            title="Top Sectors",
            endpoint=f"/api/entities/portfolio/{safe_name}/top-sectors",
            widget_type="chart",
            chart_config=ChartConfig(
                chart_type="bar",
                x_key="sector",
                y_key="long_exposure_dollars",
                x_label="Sector",
                y_label="Exposure ($)",
                y_format="currency",
                y_label_alt="Exposure (%)",
                y_format_alt="percent",
                color_key="sector",
                bars=[
                    BarConfig(y_key="long_exposure_dollars", y_key_alt="long_exposure_pct", label="Long", color="#38a169"),
                    BarConfig(y_key="short_exposure_dollars", y_key_alt="short_exposure_pct", label="Short", color="#e53e3e"),
                ],
                stacked=True,
            ),
            columns=[],
        ),
        WidgetConfig(
            widget_id="top_positions",
            title="Top Positions",
            endpoint=f"/api/entities/portfolio/{safe_name}/top-positions",
            widget_type="top_positions",
            columns=[],
        ),
        WidgetConfig(
            widget_id="exposure_by_sector",
            title="Net Exposure by Sector",
            endpoint=f"/api/entities/portfolio/{safe_name}/exposure-by-sector",
            widget_type="chart",
            chart_config=ChartConfig(
                chart_type="bar",
                x_key="sector",
                y_key="net_exposure",
                x_label="Sector",
                y_label="Net Exposure ($)",
                y_format="currency",
            ),
            columns=[],
        ),
        WidgetConfig(
            widget_id="pnl_by_position",
            title="PnL by Position (Top 20)",
            endpoint=f"/api/entities/portfolio/{safe_name}/pnl-by-position",
            widget_type="chart",
            chart_config=ChartConfig(
                chart_type="bar",
                x_key="ticker",
                y_key="pnl",
                x_label="Ticker",
                y_label="PnL ($)",
                y_format="currency",
            ),
            columns=[],
        ),
        WidgetConfig(
            widget_id="pnl_by_sector",
            title="PnL by Sector",
            endpoint=f"/api/entities/portfolio/{safe_name}/pnl-by-sector",
            widget_type="chart",
            chart_config=ChartConfig(
                chart_type="bar",
                x_key="sector",
                y_key="pnl",
                x_label="Sector",
                y_label="PnL ($)",
                y_format="currency",
            ),
            columns=[],
        ),
        WidgetConfig(
            widget_id="positions",
            title="Positions",
            endpoint=f"/api/entities/portfolio/{safe_name}/positions",
            columns=[
                ColumnConfig(key="ticker", label="Ticker", entity_type="stock"),
                ColumnConfig(key="side", label="Side", format="titlecase"),
                ColumnConfig(key="shares", label="Shares", format="number"),
                ColumnConfig(key="cost_basis", label="Cost Basis", format="currency"),
                ColumnConfig(key="current_price", label="Current Price", format="currency"),
                ColumnConfig(key="exposure_dollars", label="Current Exposure ($)", format="number"),
                ColumnConfig(key="exposure_pct", label="Current Exposure %", format="text"),
                ColumnConfig(key="return_dollar", label="Return $", format="number"),
                ColumnConfig(key="return_pct", label="Return %", format="text"),
                ColumnConfig(key="pnl", label="PnL $", format="number"),
                ColumnConfig(key="pnl_pct", label="PnL %", format="text"),
                ColumnConfig(key="sector", label="Sector", entity_type="sector"),
                ColumnConfig(key="company_name", label="Company", visible=False, entity_type="stock", entity_id_field="ticker"),
                ColumnConfig(key="market_cap_b", label="Market Cap ($B)", format="number", visible=False),
                ColumnConfig(key="pe_ratio", label="P/E Ratio", format="number", visible=False),
                ColumnConfig(key="52w_high", label="52W High", format="currency", visible=False),
                ColumnConfig(key="52w_low", label="52W Low", format="currency", visible=False),
                ColumnConfig(key="dividend_yield", label="Dividend Yield", format="percent", visible=False),
                ColumnConfig(key="eps", label="EPS", format="currency", visible=False),
                ColumnConfig(key="revenue_b", label="Revenue ($B)", format="number", visible=False),
            ],
            default_page_size=100,
            filter_definitions=[
                FilterDefinition(
                    field="side",
                    label="Side",
                    options=[
                        FilterOption(value="long", label="Long"),
                        FilterOption(value="short", label="Short"),
                    ],
                ),
                FilterDefinition(
                    field="sector",
                    label="Sector",
                    options=_get_sector_options(),
                ),
            ],
            client_filterable_columns=["ticker"],
        ),
    ]

    return EntityDetail(
        entity_type="portfolio",
        entity_id=name,
        display_name=f"{name} Portfolio",
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

    # Filter people dataset by ticker (executives only)
    all_people = _get_all_people(provider)
    ticker_upper = ticker.upper()
    filtered = [
        p for p in all_people
        if ticker_upper in [t.strip() for t in p.get("tickers", "").split(";")]
        and p.get("type") == "executive"
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

@router.get("/stock/{ticker}/price-history")
async def get_stock_price_history(
    ticker: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5000, ge=1, le=10000),
) -> PaginatedResponse:
    provider = get_data_provider()
    stock = provider.get_record("stocks", ticker)
    if stock is None:
        raise NotFoundError(f"Stock '{ticker}' not found")

    from app.data_access.db import get_sync_conn
    conn = get_sync_conn()
    cur = conn.cursor()
    cur.execute(
        'SELECT date, close, eps_estimate, eps_actual FROM stock_history '
        'WHERE ticker = %s ORDER BY date',
        (ticker,),
    )
    rows: list[dict[str, Any]] = []
    for date, close, eps_est, eps_act in cur.fetchall():
        entry: dict[str, Any] = {"date": str(date), "close": str(close)}
        if eps_est:
            entry["eps_estimate"] = str(eps_est)
        if eps_act:
            entry["eps_actual"] = str(eps_act)
        rows.append(entry)
    cur.close()

    return _paginate(rows, page, page_size, None, "asc")


@router.get("/stock/{ticker}/peers")
async def get_stock_peers(ticker: str) -> PaginatedResponse:
    provider = get_data_provider()
    stock = provider.get_record("stocks", ticker)
    if stock is None:
        raise NotFoundError(f"Stock '{ticker}' not found")

    sector = stock.get("sector", "")
    all_stocks = provider.query("stocks", FilterParams(page=1, page_size=600)).data
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

    all_data = provider.query(ds_meta.name, FilterParams(page=1, page_size=600)).data
    counts: dict[str, int] = {}
    for row in all_data:
        val = str(row.get(group_by, "Unknown") or "Unknown")
        counts[val] = counts.get(val, 0) + 1

    data = [{group_by: k, "count": str(v)} for k, v in sorted(counts.items())]
    return _paginate(data, 1, 200, None, "asc")


# ---------------------------------------------------------------------------
# Portfolio data endpoints
# ---------------------------------------------------------------------------

@router.get("/portfolio/{name}/positions")
async def get_portfolio_positions(
    request: Request,
    name: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    sort_by: str | None = Query(default=None),
    sort_order: str = Query(default="asc", pattern="^(asc|desc)$"),
) -> PaginatedResponse:
    from app.data_access.db import get_sync_conn
    conn = get_sync_conn()
    cur = conn.cursor()

    # Get most recent date for this portfolio
    cur.execute("""
        SELECT date FROM daily_pnl
        WHERE portfolio = %s ORDER BY date DESC LIMIT 1
    """, (name,))
    date_row = cur.fetchone()
    if not date_row:
        raise NotFoundError(f"Portfolio '{name}' not found or has no positions")

    cur.execute("""
        SELECT ticker, side, shares_held, market_value, cost_basis,
               unrealized_pnl, realized_pnl, sector, industry
        FROM daily_pnl
        WHERE portfolio = %s AND date = %s
    """, (name, date_row[0]))
    position_rows = cur.fetchall()
    cur.close()

    if not position_rows:
        raise NotFoundError(f"Portfolio '{name}' not found or has no positions")

    # Build stock lookup for enrichment fields
    provider = get_data_provider()
    all_stocks = provider.query("stocks", FilterParams(page=1, page_size=600)).data
    stock_map: dict[str, dict[str, Any]] = {s["ticker"]: s for s in all_stocks}

    # Compute total portfolio market value for exposure %
    total_portfolio_value = sum(float(r[3]) for r in position_rows)

    rows: list[dict[str, Any]] = []
    for ticker, side, shares_held, mv, cb, unreal, real, sector, industry in position_rows:
        shares = float(shares_held)
        position_value = float(mv)
        cost_basis_total = float(cb)
        avg_cost = cost_basis_total / shares if shares > 0 else 0
        price = position_value / shares if shares > 0 else 0
        return_dollar = position_value - cost_basis_total
        return_pct = ((price / avg_cost) - 1) * 100 if avg_cost else 0.0
        pnl = float(unreal) + float(real)
        pnl_pct = (pnl / cost_basis_total * 100) if cost_basis_total else 0.0
        exposure_pct = (position_value / total_portfolio_value * 100) if total_portfolio_value else 0.0
        direction = 1.0 if side == "long" else -1.0

        row: dict[str, Any] = {
            "ticker": ticker,
            "side": side,
            "shares": str(round(shares)),
            "cost_basis": f"{avg_cost:.2f}",
            "current_price": f"{price:.2f}",
            "exposure_dollars": f"{position_value * direction:,.0f}",
            "exposure_pct": f"{exposure_pct * direction:.1f}%",
            "return_dollar": f"{return_dollar:,.0f}",
            "return_pct": f"{return_pct:.1f}%",
            "pnl": f"{pnl:,.0f}",
            "pnl_pct": f"{pnl_pct:.1f}%",
            "sector": sector,
            "industry": industry,
        }

        # Enrich with stock-level fields
        stock = stock_map.get(ticker, {})
        row["company_name"] = stock.get("company_name", "")
        row["market_cap_b"] = stock.get("market_cap_b", "")
        row["pe_ratio"] = stock.get("pe_ratio", "")
        row["52w_high"] = stock.get("52w_high", "")
        row["52w_low"] = stock.get("52w_low", "")
        row["dividend_yield"] = stock.get("dividend_yield", "")
        row["eps"] = stock.get("eps", "")
        row["revenue_b"] = stock.get("revenue_b", "")

        rows.append(row)

    return _paginate(rows, page, page_size, sort_by, sort_order, _extract_filters(request))


@router.get("/portfolio/{name}/exposure-by-sector")
async def get_portfolio_exposure_by_sector(name: str) -> PaginatedResponse:
    from app.data_access.db import get_sync_conn
    conn = get_sync_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT sector, side, SUM(market_value) AS mv
        FROM daily_pnl
        WHERE portfolio = %s
          AND date = (SELECT MAX(date) FROM daily_pnl WHERE portfolio = %s)
        GROUP BY sector, side
    """, (name, name))

    sector_exposure: dict[str, float] = {}
    for sector, side, mv in cur.fetchall():
        direction = 1.0 if side == "long" else -1.0
        s = sector or "Unknown"
        sector_exposure[s] = sector_exposure.get(s, 0.0) + float(mv) * direction
    cur.close()

    data = [
        {"sector": s, "net_exposure": str(round(v))}
        for s, v in sorted(sector_exposure.items())
    ]
    return _paginate(data, 1, 200, None, "asc")


@router.get("/portfolio/{name}/pnl-by-position")
async def get_portfolio_pnl_by_position(name: str) -> PaginatedResponse:
    from app.data_access.db import get_sync_conn
    conn = get_sync_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT ticker, SUM(unrealized_pnl + realized_pnl) AS pnl
        FROM daily_pnl
        WHERE portfolio = %s
          AND date = (SELECT MAX(date) FROM daily_pnl WHERE portfolio = %s)
        GROUP BY ticker
    """, (name, name))

    position_pnl = [{"ticker": r[0], "pnl": round(float(r[1]), 2)} for r in cur.fetchall()]
    cur.close()

    # Sort by absolute PnL descending, take top 20
    position_pnl.sort(key=lambda r: abs(r["pnl"]), reverse=True)
    top_20 = position_pnl[:20]
    # Format for chart (plain numbers for JS Number() parsing)
    data = [{"ticker": r["ticker"], "pnl": str(round(r["pnl"]))} for r in top_20]
    return _paginate(data, 1, 200, None, "asc")


@router.get("/portfolio/{name}/pnl-by-sector")
async def get_portfolio_pnl_by_sector(name: str) -> PaginatedResponse:
    from app.data_access.db import get_sync_conn
    conn = get_sync_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT sector, SUM(unrealized_pnl + realized_pnl) AS pnl
        FROM daily_pnl
        WHERE portfolio = %s
          AND date = (SELECT MAX(date) FROM daily_pnl WHERE portfolio = %s)
        GROUP BY sector
    """, (name, name))

    data = [
        {"sector": r[0] or "Unknown", "pnl": str(round(float(r[1])))}
        for r in cur.fetchall()
    ]
    cur.close()
    data.sort(key=lambda r: r["sector"])
    return _paginate(data, 1, 200, None, "asc")


@router.get("/portfolio/{name}/value-history")
async def get_portfolio_value_history(
    name: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5000, ge=1, le=10000),
) -> PaginatedResponse:
    from app.data_access.db import get_sync_conn
    conn = get_sync_conn()
    cur = conn.cursor()

    # Monthly snapshots: last trading day of each month
    cur.execute("""
        SELECT DISTINCT ON (date_trunc('month', date))
               date,
               SUM(market_value) AS market_value,
               SUM(unrealized_pnl + realized_pnl) AS cumulative_pnl
        FROM daily_pnl
        WHERE portfolio = %s
        GROUP BY date
        ORDER BY date_trunc('month', date) DESC, date DESC
    """, (name,))
    raw = cur.fetchall()
    cur.close()

    if not raw:
        return PaginatedResponse(
            data=[], page=1, page_size=page_size,
            total_records=0, total_pages=1, has_next=False, has_previous=False,
        )

    series = [
        {
            "date": str(r[0]),
            "market_value": str(round(float(r[1]))),
            "cumulative_pnl": str(round(float(r[2]))),
        }
        for r in sorted(raw, key=lambda r: r[0])
    ]
    return _paginate(series, page, page_size, None, "asc")


@router.get("/portfolio/{name}/daily-pnl")
async def get_portfolio_daily_pnl(
    name: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5000, ge=1, le=10000),
) -> PaginatedResponse:
    from app.data_access.db import get_sync_conn
    conn = get_sync_conn()
    cur = conn.cursor()

    # Portfolio-level daily aggregates from daily_pnl
    cur.execute("""
        SELECT date,
               SUM(market_value) AS market_value,
               SUM(cost_basis) AS total_cost_basis,
               SUM(unrealized_pnl + realized_pnl) AS total_pnl
        FROM daily_pnl
        WHERE portfolio = %s
        GROUP BY date
        ORDER BY date
    """, (name,))
    daily_rows = cur.fetchall()

    if not daily_rows:
        cur.close()
        return PaginatedResponse(
            data=[], page=1, page_size=page_size,
            total_records=0, total_pages=1, has_next=False, has_previous=False,
        )

    # Query-time fields: trade counts and amounts per date
    cur.execute("""
        SELECT date,
               COUNT(*),
               COUNT(*) FILTER (WHERE action = 'buy'),
               COUNT(*) FILTER (WHERE action = 'sell'),
               COALESCE(SUM(shares::numeric * price::numeric) FILTER (WHERE action = 'buy'), 0),
               COALESCE(SUM(shares::numeric * price::numeric) FILTER (WHERE action = 'sell'), 0)
        FROM portfolio_trades
        WHERE portfolio = %s
        GROUP BY date
    """, (name,))
    trade_stats: dict[str, tuple] = {}
    for row in cur.fetchall():
        trade_stats[str(row[0])] = (int(row[1]), int(row[2]), int(row[3]),
                                     float(row[4]), float(row[5]))
    cur.close()

    # Compute initial_capital and build series with cumulative PnL
    # portfolio_value = initial_capital + cumulative_pnl_dollar
    initial_capital = float(daily_rows[0][1])  # market_value on first date
    prev_pnl = 0.0
    series: list[dict[str, str]] = []

    for date_val, mv, tcb, total_pnl in daily_rows:
        date_str = str(date_val)
        market_value = float(mv)
        total_cost_basis = float(tcb)
        cumulative_pnl = float(total_pnl)
        daily_pnl_dollar = cumulative_pnl - prev_pnl

        portfolio_value = initial_capital + cumulative_pnl
        daily_pnl_pct = (daily_pnl_dollar / abs(market_value - daily_pnl_dollar) * 100) if (market_value - daily_pnl_dollar) else 0.0
        cumulative_pnl_pct = (cumulative_pnl / initial_capital * 100) if initial_capital else 0.0

        ts = trade_stats.get(date_str, (0, 0, 0, 0.0, 0.0))

        series.append({
            "date": date_str,
            "daily_pnl": str(round(daily_pnl_dollar)),
            "cumulative_pnl": str(round(cumulative_pnl)),
            "daily_pnl_pct": f"{daily_pnl_pct:.2f}",
            "cumulative_pnl_pct": f"{cumulative_pnl_pct:.2f}",
            "market_value": str(round(market_value)),
            "portfolio_value": str(round(portfolio_value)),
            "total_cost_basis": str(round(total_cost_basis)),
            "total_trades": str(ts[0]),
            "num_buys": str(ts[1]),
            "num_sells": str(ts[2]),
            "buy_amount": str(round(ts[3])),
            "sell_amount": str(round(ts[4])),
        })
        prev_pnl = cumulative_pnl

    return _paginate(series, page, page_size, None, "asc")


@router.get("/portfolio/{name}/top-positions")
async def get_portfolio_top_positions(name: str) -> PaginatedResponse:
    from app.data_access.db import get_sync_conn
    conn = get_sync_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT ticker, sector, side, market_value
        FROM daily_pnl
        WHERE portfolio = %s
          AND date = (SELECT MAX(date) FROM daily_pnl WHERE portfolio = %s)
    """, (name, name))
    raw = cur.fetchall()
    cur.close()

    if not raw:
        return PaginatedResponse(
            data=[], page=1, page_size=20,
            total_records=0, total_pages=1, has_next=False, has_previous=False,
        )

    total_portfolio_value = sum(float(r[3]) for r in raw)

    rows: list[dict[str, Any]] = []
    for ticker, sector, side, mv in raw:
        position_value = float(mv)
        exposure_pct = (position_value / total_portfolio_value * 100) if total_portfolio_value else 0.0
        rows.append({
            "ticker": ticker,
            "sector": sector,
            "side": side,
            "exposure_dollars": round(position_value, 2),
            "exposure_pct": round(exposure_pct, 1),
        })

    # Return all positions sorted by absolute exposure; frontend slices top N per side
    rows.sort(key=lambda r: abs(r["exposure_dollars"]), reverse=True)

    return _paginate(rows, 1, 500, None, "asc")


@router.get("/portfolio/{name}/top-sectors")
async def get_portfolio_top_sectors(name: str) -> PaginatedResponse:
    from app.data_access.db import get_sync_conn
    conn = get_sync_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT sector, side, SUM(market_value) AS mv
        FROM daily_pnl
        WHERE portfolio = %s
          AND date = (SELECT MAX(date) FROM daily_pnl WHERE portfolio = %s)
        GROUP BY sector, side
    """, (name, name))
    raw = cur.fetchall()
    cur.close()

    if not raw:
        return PaginatedResponse(
            data=[], page=1, page_size=20,
            total_records=0, total_pages=1, has_next=False, has_previous=False,
        )

    total_portfolio_value = sum(float(r[2]) for r in raw)
    sector_long: dict[str, float] = {}
    sector_short: dict[str, float] = {}
    for sector, side, mv in raw:
        s = sector or "Unknown"
        if side == "long":
            sector_long[s] = sector_long.get(s, 0.0) + float(mv)
        else:
            sector_short[s] = sector_short.get(s, 0.0) + float(mv)

    all_sectors = sorted(set(list(sector_long.keys()) + list(sector_short.keys())))
    rows: list[dict[str, Any]] = []
    for sector in all_sectors:
        long_val = sector_long.get(sector, 0.0)
        short_val = sector_short.get(sector, 0.0)
        long_pct = (long_val / total_portfolio_value * 100) if total_portfolio_value else 0.0
        short_pct = (short_val / total_portfolio_value * 100) if total_portfolio_value else 0.0
        rows.append({
            "sector": sector,
            "long_exposure_dollars": str(round(long_val)),
            "short_exposure_dollars": str(round(-short_val)),
            "long_exposure_pct": f"{long_pct:.1f}",
            "short_exposure_pct": f"{-short_pct:.1f}",
        })

    rows.sort(
        key=lambda r: abs(float(r["long_exposure_dollars"])) + abs(float(r["short_exposure_dollars"])),
        reverse=True,
    )
    return _paginate(rows, 1, 200, None, "asc")


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


_DATASET_ENTITY_COLUMNS: dict[str, dict[str, tuple[str, str | None]]] = {
    "stocks": {
        "ticker": ("stock", None),
        "company_name": ("stock", "ticker"),
        "sector": ("sector", None),
        "industry": ("industry", None),
    },
    "people": {
        "person_id": ("person", None),
        "name": ("person", "person_id"),
        "tickers": ("stock", None),
    },
    "portfolios": {
        "name": ("portfolio", None),
    },
    "portfolio_trades": {
        "ticker": ("stock", None),
        "portfolio": ("portfolio", None),
    },
    "sec_filings": {
        "symbol": ("stock", None),
    },
    "transcripts_list": {
        "symbol": ("stock", None),
    },
}


_DATASET_FORMAT_OVERRIDES: dict[str, dict[str, str]] = {
    "portfolio_trades": {"side": "titlecase", "action": "titlecase"},
}

_JOIN_EXCLUDE_COLUMNS = {"long_business_summary"}

_DATASET_JOINS: dict[str, list[tuple[str, str, str]]] = {
    # source_dataset: [(target_dataset, source_key, target_key), ...]
    "portfolio_trades": [
        ("stocks", "ticker", "ticker"),
        ("portfolios", "portfolio", "name"),
        ("stock_betas", "ticker", "ticker"),
    ],
    "sec_filings": [
        ("stocks", "symbol", "ticker"),
    ],
    "transcripts_list": [
        ("stocks", "symbol", "ticker"),
    ],
    "stocks": [
        ("stock_betas", "ticker", "ticker"),
    ],
}


def _annotate_entity_columns(dataset_name: str, columns: list[ColumnConfig]) -> None:
    mapping = _DATASET_ENTITY_COLUMNS.get(dataset_name, {})
    fmt_overrides = _DATASET_FORMAT_OVERRIDES.get(dataset_name, {})
    for col in columns:
        if col.key in mapping:
            entity_type, entity_id_field = mapping[col.key]
            col.entity_type = entity_type
            if entity_id_field:
                col.entity_id_field = entity_id_field
        if col.key in fmt_overrides:
            col.format = fmt_overrides[col.key]


def _get_all_people(provider: Any | None = None) -> list[dict[str, Any]]:
    """Load all people records across pages (page_size capped at 1000)."""
    if provider is None:
        provider = get_data_provider()
    all_rows: list[dict[str, Any]] = []
    page = 1
    while True:
        result = provider.query("people", FilterParams(page=page, page_size=1000))
        all_rows.extend(result.data)
        if not result.has_next:
            break
        page += 1
    return all_rows


def _get_sector_options() -> list[FilterOption]:
    provider = get_data_provider()
    stocks = provider.query("stocks", FilterParams(page=1, page_size=600)).data
    sectors = sorted({s.get("sector", "") for s in stocks if s.get("sector")})
    return [FilterOption(value=s, label=s) for s in sectors]


def _get_exchange_options() -> list[FilterOption]:
    provider = get_data_provider()
    stocks = provider.query("stocks", FilterParams(page=1, page_size=600)).data
    exchanges = sorted({s.get("exchange", "") for s in stocks if s.get("exchange")})
    return [FilterOption(value=e, label=e) for e in exchanges]


# ---------------------------------------------------------------------------
# Portfolio helpers
# ---------------------------------------------------------------------------

_price_index_cache: dict[str, tuple[list[str], list[float]]] | None = None


def _build_price_index() -> dict[str, tuple[list[str], list[float]]]:
    """Load stock_history once into {ticker: (sorted_dates, prices)} for fast lookups."""
    global _price_index_cache
    if _price_index_cache is not None:
        return _price_index_cache

    from app.data_access.db import get_sync_conn
    conn = get_sync_conn()
    cur = conn.cursor()
    cur.execute("SELECT ticker, date, close FROM stock_history ORDER BY ticker, date")

    raw: dict[str, list[tuple[str, float]]] = {}
    for ticker, date_val, close_val in cur.fetchall():
        if ticker not in raw:
            raw[ticker] = []
        raw[ticker].append((str(date_val), float(close_val)))
    cur.close()

    index: dict[str, tuple[list[str], list[float]]] = {}
    for ticker, entries in raw.items():
        index[ticker] = ([e[0] for e in entries], [e[1] for e in entries])

    _price_index_cache = index
    return _price_index_cache


def _price_on_date(ticker: str, date: str) -> float | None:
    """Binary-search the price index for the closest date <= target."""
    index = _build_price_index()
    entry = index.get(ticker)
    if not entry:
        return None
    dates, prices = entry
    idx = bisect.bisect_right(dates, date) - 1
    if idx < 0:
        return None
    return prices[idx]


def _get_latest_prices() -> dict[str, float]:
    """Return the most recent close price per ticker."""
    index = _build_price_index()
    return {ticker: prices[-1] for ticker, (_, prices) in index.items()}


def _load_portfolio_trades(portfolio_name: str) -> list[dict[str, str]]:
    """Load trades for a specific portfolio, sorted by date."""
    from app.data_access.db import get_sync_conn
    conn = get_sync_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, ticker, action, shares, price, portfolio, side "
        "FROM portfolio_trades WHERE portfolio = %s ORDER BY date",
        (portfolio_name,),
    )
    columns = [desc[0] for desc in cur.description]
    rows = [{col: str(val) if val is not None else "" for col, val in zip(columns, row)}
            for row in cur.fetchall()]
    cur.close()
    return rows


def _compute_portfolio_holdings(
    portfolio_name: str,
    as_of_date: str | None = None,
) -> list[dict[str, Any]]:
    """Replay trades to compute current holdings with cost basis."""
    trades = _load_portfolio_trades(portfolio_name)
    if not trades:
        return []

    provider = get_data_provider()
    stocks = provider.query("stocks", FilterParams(page=1, page_size=600)).data
    sector_map = {s["ticker"]: s.get("sector", "Unknown") for s in stocks}
    industry_map = {s["ticker"]: s.get("industry", "Unknown") for s in stocks}

    positions: dict[str, dict[str, Any]] = {}  # ticker -> {side, shares, total_cost}

    for trade in trades:
        if as_of_date and trade["date"] > as_of_date:
            break

        ticker = trade["ticker"]
        action = trade["action"]
        side = trade["side"]
        shares = float(trade["shares"])
        price = float(trade["price"])
        cost = shares * price

        # Opening: buy+long or sell+short
        if (action == "buy" and side == "long") or (action == "sell" and side == "short"):
            if ticker not in positions:
                positions[ticker] = {"side": side, "shares": 0.0, "total_cost": 0.0}
            positions[ticker]["shares"] += shares
            positions[ticker]["total_cost"] += cost
        # Closing: sell+long or buy+short
        elif (action == "sell" and side == "long") or (action == "buy" and side == "short"):
            if ticker in positions and positions[ticker]["shares"] > 0:
                pos = positions[ticker]
                ratio = min(shares / pos["shares"], 1.0)
                pos["total_cost"] *= 1 - ratio
                pos["shares"] -= shares
                if pos["shares"] <= 0.5:  # float tolerance
                    del positions[ticker]

    result: list[dict[str, Any]] = []
    for ticker, pos in positions.items():
        if pos["shares"] < 0.5:
            continue
        avg_cost = pos["total_cost"] / pos["shares"] if pos["shares"] > 0 else 0
        result.append({
            "ticker": ticker,
            "side": pos["side"],
            "shares": pos["shares"],
            "total_cost": round(pos["total_cost"], 2),
            "avg_cost": round(avg_cost, 2),
            "sector": sector_map.get(ticker, "Unknown"),
            "industry": industry_map.get(ticker, "Unknown"),
        })
    return result


_all_trading_dates_cache: list[str] | None = None


def _get_all_trading_dates() -> list[str]:
    """Return sorted list of every unique date in the price index."""
    global _all_trading_dates_cache
    if _all_trading_dates_cache is not None:
        return _all_trading_dates_cache
    index = _build_price_index()
    dates_set: set[str] = set()
    for dates, _ in index.values():
        dates_set.update(dates)
    _all_trading_dates_cache = sorted(dates_set)
    return _all_trading_dates_cache


def _compute_daily_pnl_series(portfolio_name: str) -> list[dict[str, str]]:
    """Replay trades against daily prices to produce per-day PnL series."""
    trades = _load_portfolio_trades(portfolio_name)
    if not trades:
        return []

    provider = get_data_provider()
    stocks = provider.query("stocks", FilterParams(page=1, page_size=600)).data
    sector_map = {s["ticker"]: s.get("sector", "Unknown") for s in stocks}

    # Group trades by date for O(1) lookup
    trades_by_date: dict[str, list[dict[str, str]]] = {}
    for t in trades:
        trades_by_date.setdefault(t["date"], []).append(t)

    all_dates = _get_all_trading_dates()
    # Start from first trade date
    first_trade_date = trades[0]["date"]
    start_idx = bisect.bisect_left(all_dates, first_trade_date)

    positions: dict[str, dict[str, Any]] = {}  # ticker -> {side, shares, total_cost}
    prev_signed_mv = 0.0
    cumulative_pnl = 0.0
    initial_capital = 0.0  # equity deployed on day 1, used as denominator for PnL%
    series: list[dict[str, str]] = []

    for i in range(start_idx, len(all_dates)):
        date = all_dates[i]
        num_buys = 0
        num_sells = 0
        buy_amount = 0.0
        sell_amount = 0.0

        # Apply trades for this date
        for trade in trades_by_date.get(date, []):
            ticker = trade["ticker"]
            action = trade["action"]
            side = trade["side"]
            shares = float(trade["shares"])
            price = float(trade["price"])
            cost = shares * price

            if action == "buy":
                num_buys += 1
                buy_amount += cost
            else:
                num_sells += 1
                sell_amount += cost

            # Opening: buy+long or sell+short
            if (action == "buy" and side == "long") or (action == "sell" and side == "short"):
                if ticker not in positions:
                    positions[ticker] = {"side": side, "shares": 0.0, "total_cost": 0.0}
                positions[ticker]["shares"] += shares
                positions[ticker]["total_cost"] += cost
            # Closing: sell+long or buy+short
            elif (action == "sell" and side == "long") or (action == "buy" and side == "short"):
                if ticker in positions and positions[ticker]["shares"] > 0:
                    pos = positions[ticker]
                    ratio = min(shares / pos["shares"], 1.0)
                    pos["total_cost"] *= 1 - ratio
                    pos["shares"] -= shares
                    if pos["shares"] <= 0.5:
                        del positions[ticker]

        # Compute gross market value (for backward compat) and signed market
        # value (longs positive, shorts negative — used for PnL).
        market_value = 0.0
        signed_mv = 0.0
        for ticker, pos in positions.items():
            pr = _price_on_date(ticker, date)
            if pr is None:
                pr = pos["total_cost"] / pos["shares"] if pos["shares"] > 0 else 0
            val = pos["shares"] * pr
            market_value += val
            signed_mv += val if pos["side"] == "long" else -val

        # Daily PnL uses signed MV so that opening a short (which adds to
        # gross MV but is a liability) doesn't count as profit.  The capital
        # flow adjustment removes the non-PnL effect of new buys/sells.
        net_capital_flow = buy_amount - sell_amount
        total_trades = num_buys + num_sells

        if i == start_idx:
            # Initial capital = gross market value on day 1 (total capital
            # deployed across both long and short positions).
            initial_capital = market_value
            # Day 1 PnL = intraday move from trade prices to EOD
            daily_pnl = (signed_mv - 0.0) - net_capital_flow
            cumulative_pnl = daily_pnl
        else:
            daily_pnl = (signed_mv - prev_signed_mv) - net_capital_flow
            cumulative_pnl += daily_pnl

        total_cost_basis = sum(p["total_cost"] for p in positions.values())
        portfolio_value = initial_capital + cumulative_pnl
        daily_pnl_pct = (daily_pnl / abs(prev_signed_mv) * 100) if prev_signed_mv and i > start_idx else 0.0
        cumulative_pnl_pct = (cumulative_pnl / initial_capital * 100) if initial_capital else 0.0

        series.append({
            "date": date,
            "daily_pnl": str(round(daily_pnl)),
            "cumulative_pnl": str(round(cumulative_pnl)),
            "daily_pnl_pct": f"{daily_pnl_pct:.2f}",
            "cumulative_pnl_pct": f"{cumulative_pnl_pct:.2f}",
            "market_value": str(round(market_value)),
            "portfolio_value": str(round(portfolio_value)),
            "total_cost_basis": str(round(total_cost_basis)),
            "total_trades": str(total_trades),
            "num_buys": str(num_buys),
            "num_sells": str(num_sells),
            "buy_amount": str(round(buy_amount)),
            "sell_amount": str(round(sell_amount)),
        })

        prev_signed_mv = signed_mv

    return series


def _compute_sp500_equal_weight_returns(start_date: str) -> dict[str, float]:
    """Compute equal-weight cumulative return from all stocks starting at *start_date*.

    Uses the cached price index so no extra file I/O is needed.
    """
    index = _build_price_index()
    all_dates = _get_all_trading_dates()
    start_idx = bisect.bisect_left(all_dates, start_date)
    if start_idx >= len(all_dates):
        return {}

    result: dict[str, float] = {}
    cum = 0.0  # cumulative return as a fraction (0.05 = 5%)
    prev_date: str | None = None

    for i in range(start_idx, len(all_dates)):
        date = all_dates[i]
        if prev_date is None:
            result[date] = 0.0
            prev_date = date
            continue

        # Compute average daily return across all stocks with prices on both days
        total_return = 0.0
        count = 0
        for ticker, (dates, prices) in index.items():
            # Find price for prev_date
            idx_prev = bisect.bisect_right(dates, prev_date) - 1
            if idx_prev < 0 or dates[idx_prev] != prev_date:
                continue
            # Find price for date
            idx_cur = bisect.bisect_right(dates, date) - 1
            if idx_cur < 0 or dates[idx_cur] != date:
                continue
            p_prev = prices[idx_prev]
            p_cur = prices[idx_cur]
            if p_prev > 0:
                total_return += (p_cur - p_prev) / p_prev
                count += 1

        avg_daily_return = total_return / count if count > 0 else 0.0
        cum = (1 + cum) * (1 + avg_daily_return) - 1
        result[date] = cum * 100  # store as percentage

        prev_date = date

    return result


_URL_COLUMN_NAMES = {"url", "link", "href", "website", "web_site", "homepage", "filing_url"}


def _infer_column_format(key: str, sample_value: Any) -> str:
    """Infer a column format from its name and a sample value."""
    key_lower = key.lower()
    if key_lower in _URL_COLUMN_NAMES:
        return "url"
    val = str(sample_value) if sample_value else ""
    if val.startswith(("http://", "https://")):
        return "url"
    return "text"


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
