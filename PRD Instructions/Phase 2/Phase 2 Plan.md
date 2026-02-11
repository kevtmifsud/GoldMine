# GoldMine Phase 2 — Widget Engine & Filtering Model

## Context

Phase 1 delivered entity resolution, entity pages, and read-only SmartlistWidget tables. Phase 2 adds interactive filtering (server-side and client-side), chart widgets (bar/line via Recharts), column visibility toggling, and a generic WidgetContainer dispatcher. The backend-driven philosophy continues: adding new widget types or filters is a backend-only change.

---

## New Files (4)

| File | Purpose |
|------|---------|
| `frontend/src/components/WidgetContainer.tsx` | Dispatches to SmartlistWidget or ChartWidget based on `widget_type` |
| `frontend/src/components/ChartWidget.tsx` | Recharts bar/line chart renderer |
| `frontend/src/styles/chart.css` | Chart widget styles |
| `backend/app/tests/test_phase2_widgets.py` | Tests for chart endpoints, server-side filtering, distribution |

## Modified Files (8)

| File | Changes |
|------|---------|
| `backend/app/api/entity_models.py` | Add FilterOption, FilterDefinition, ChartConfig; extend WidgetConfig + ColumnConfig |
| `backend/app/api/entities.py` | Add 3 chart data endpoints, wire chart/filter configs into detail builders, update `_paginate` for filters |
| `backend/app/api/data.py` | Extract unknown query params as filters |
| `backend/app/tests/test_entities.py` | Update widget count assertions for new chart widgets |
| `frontend/src/types/entities.ts` | Add FilterOption, FilterDefinition, ChartConfig; extend WidgetConfig + ColumnConfig |
| `frontend/src/components/SmartlistWidget.tsx` | Add server-side filter controls, client-side quick filter, column visibility toggle |
| `frontend/src/styles/smartlist.css` | Add filter, quick-filter, column-picker styles |
| `frontend/src/pages/EntityPage.tsx` | Replace SmartlistWidget with WidgetContainer |

---

## Stage 1: Backend Model Extensions

**File: `backend/app/api/entity_models.py`**

Add new models (all new WidgetConfig fields have defaults so Phase 1 configs remain valid):

- `FilterOption(value, label)` — single option in a dropdown
- `FilterDefinition(field, label, filter_type="select", options[])` — tells frontend what filter UI to render
- `ChartConfig(chart_type, x_key, y_key, x_label, y_label, color="#2a4a7f")` — chart rendering config

Extend existing:
- `WidgetConfig` gains: `widget_type="table"`, `chart_config=None`, `filter_definitions=[]`, `client_filterable_columns=[]`
- `ColumnConfig` gains: `visible=True`

**Verify:** `pytest -v` — all 50 existing tests pass (defaults preserve behavior).

---

## Stage 2: Backend Filter Plumbing

**File: `backend/app/api/data.py`**
- Import `Request`, extract unknown query params (not in `{page, page_size, sort_by, sort_order, search}`) as filters dict, pass to `FilterParams`

**File: `backend/app/api/entities.py`**
- Update `_paginate()` to accept optional `filters` dict, apply exact-match filtering before sort/paginate
- Update widget data endpoints (`stock/{ticker}/people`, `stock/{ticker}/files`, `person/{id}/stocks`) to accept `Request`, extract filters, pass to `_paginate`

**Verify:** `GET /api/data/stocks?sector=Technology` returns only Technology stocks. `GET /api/entities/stock/AAPL/people?type=analyst` returns only analysts.

---

## Stage 3: Backend Chart Data Endpoints

**File: `backend/app/api/entities.py`** — 3 new endpoints:

1. `GET /api/entities/stock/{ticker}/peers` — Returns stocks in same sector, sorted by market_cap_b desc
2. `GET /api/entities/person/{person_id}/coverage-sectors` — Aggregates covered stocks by sector, returns `{sector, count}` rows
3. `GET /api/entities/dataset/{dataset_name}/distribution?group_by=sector` — Groups dataset rows by field, returns `{field, count}` rows

Helper functions:
- `_get_sector_options()` — extracts unique sectors for filter dropdown options
- `_get_exchange_options()` — extracts unique exchanges for filter dropdown options
- `_get_dataset_filter_definitions(dataset_name)` — returns appropriate filter definitions per dataset

**Verify:** New tests in `test_phase2_widgets.py` cover all 3 endpoints + 404 cases.

---

## Stage 4: Wire Chart/Filter Configs into Entity Detail

**File: `backend/app/api/entities.py`** — Update detail builders:

**Stock page** (3 widgets, was 2):
- NEW: "Price vs Sector Peers" bar chart → `/api/entities/stock/{ticker}/peers`
- "Related People" table + filter_definitions: `[{field: "type", options: executive/analyst}]`, client_filterable: `["name", "organization"]`
- "Related Files" table + filter_definitions: `[{field: "type", options: transcript/report/data_export/audio}]`

**Person page** (2 widgets, was 1):
- NEW: "Coverage by Sector" bar chart → `/api/entities/person/{id}/coverage-sectors`
- "Covered Stocks" table + filter_definitions: `[{field: "sector", options: dynamic}]`, client_filterable: `["ticker", "company_name"]`

**Dataset page** (2 widgets for stocks, was 1):
- Existing contents table + filter_definitions (sector/exchange for stocks; type for people)
- NEW (stocks only): "Sector Distribution" bar chart → `/api/entities/dataset/{name}/distribution`

**File: `backend/app/tests/test_entities.py`** — Update assertions: stock=3 widgets, person=2, dataset/stocks=2.

**Verify:** `pytest -v` — all tests pass with updated counts.

---

## Stage 5: Frontend Types + ChartWidget + WidgetContainer

1. `npm install recharts` in frontend/
2. **`frontend/src/types/entities.ts`** — Add `FilterOption`, `FilterDefinition`, `ChartConfig` interfaces; extend `WidgetConfig` and `ColumnConfig`
3. **`frontend/src/components/ChartWidget.tsx`** — New component:
   - Fetches data from `config.endpoint` (same pattern as SmartlistWidget)
   - Reads `chart_config` for chart_type (bar/line), x_key, y_key, labels, color
   - Renders Recharts `BarChart`/`LineChart` inside `ResponsiveContainer` (height 300px)
   - Loading/error/empty states matching SmartlistWidget pattern
4. **`frontend/src/styles/chart.css`** — Card styling matching smartlist pattern
5. **`frontend/src/components/WidgetContainer.tsx`** — Thin dispatcher: `widget_type === "chart"` → ChartWidget, default → SmartlistWidget
6. **`frontend/src/pages/EntityPage.tsx`** — Import WidgetContainer, replace `<SmartlistWidget>` with `<WidgetContainer>`

**Verify:** Entity pages show charts above tables. Existing tables still work. `npx tsc -b` passes.

---

## Stage 6: Frontend Server-Side + Client-Side Filtering

**File: `frontend/src/components/SmartlistWidget.tsx`**

Server-side filters:
- New state: `serverFilters: Record<string, string>`
- Render dropdowns/inputs from `config.filter_definitions[]` above the table
- Include filter values as query params in `fetchData`
- Changing a filter resets page to 1

Client-side quick filter:
- New state: `clientFilterText: string`
- When `config.client_filterable_columns` is non-empty, render a quick-filter text input
- Filter `data` array locally (no re-fetch): check if any `client_filterable_columns` values contain the text
- Use filtered `displayData` for table rendering

**File: `frontend/src/styles/smartlist.css`** — Add `.smartlist__filters`, `.smartlist__filter-select`, `.smartlist__quick-filter` styles.

**Verify:** Dropdown filters trigger re-fetch. Quick filter is instant (< 1s). No cross-widget effects.

---

## Stage 7: Frontend Column Visibility

**File: `frontend/src/components/SmartlistWidget.tsx`**

- New state: `visibleColumns: Set<string>` (initialized from columns where `visible !== false`)
- New state: `showColumnPicker: boolean`
- Restructure title area into `.smartlist__header` with title + "Columns" button
- "Columns" button opens dropdown with checkboxes for each column
- Prevent unchecking last column (minimum 1 visible)
- Click-outside handler to close picker

**File: `frontend/src/styles/smartlist.css`** — Add `.smartlist__header`, `.smartlist__column-toggle`, `.smartlist__column-picker` styles.

**Verify:** Columns button appears. Toggling hides/shows columns instantly. No re-fetch. Minimum 1 column visible.

---

## Stage 8: Tests + Polish

- Write `test_phase2_widgets.py`: chart endpoints, filter params, distribution, 404s
- Update `test_entities.py` widget count assertions
- Run `pytest -v` — all tests pass
- Run `npx tsc -b` — TypeScript builds clean
- Save plan to `PRD Instructions/Phase 2/`

---

## Key Design Decisions

1. **`widget_type` default `"table"`** — All existing configs work with zero changes. WidgetContainer dispatches on this field.
2. **Backend-driven filter definitions** — Backend sends `filter_definitions[]` telling frontend what controls to render. Adding a filter is a backend-only change.
3. **Charts use PaginatedResponse** — Same data format as tables. ChartWidget ignores pagination, reads `data[]` array. Any endpoint can back a chart.
4. **Two-tier filtering** — Server-side filters are query params (trigger re-fetch, affect totals). Client-side quick filter is local JS on current page (instant, no re-fetch).
5. **Recharts** — Only new npm dependency. Lightweight, React-native, good TypeScript support.
6. **Column visibility is ephemeral state** — Ready for Phase 3 saved views to persist it.

---

## Verification Checklist

| Criteria | How to verify |
|---|---|
| Stock page shows "Price vs Peers" bar chart | Navigate to AAPL, see bar chart with sector peers |
| Person page shows "Coverage by Sector" chart | Navigate to PER-026, see sector distribution chart |
| Dataset page shows "Sector Distribution" chart | Navigate to stocks dataset, see sector bar chart |
| Server-side filter works | On stock people widget, filter by Type=Analyst, table re-fetches |
| Client-side quick filter works | Type in quick filter, rows filter instantly without re-fetch |
| Column visibility toggle works | Click Columns button, uncheck a column, column disappears |
| Filter on /api/data/stocks?sector=Technology works | Direct API call returns filtered data |
| All backend tests pass | `pytest -v` — 63 passed |
| TypeScript builds | `npx tsc -b` — clean |
| Charts render correctly | Visual check on all entity pages |
| Widget isolation | Filtering one widget doesn't affect others |
| Performance: client interactions < 1s | DevTools check |
