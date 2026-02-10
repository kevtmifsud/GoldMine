# GoldMine Phase 1 — Core Navigation, Entities & Global Pages

## Context

Phase 0 delivered the app skeleton, auth, data access, and object storage layers. Phase 1 builds the first user-visible research functionality: a chatbot-style search landing page, entity resolution, global entity pages for Stock/Person/Dataset, and read-only Smartlist table widgets backed by structured data.

The design anticipates future phases: widget configurability (Phase 2), saved views and Analyst Packs (Phase 3), LLM integration in the search bar (Phase 4), and charts (Phase 2). All entity page rendering is backend-driven so new entity types or widgets require zero frontend changes.

---

## New Files (13)

| File | Purpose |
|------|---------|
| `backend/app/api/entity_models.py` | Pydantic models: EntityResolution, EntityDetail, WidgetConfig, etc. |
| `backend/app/api/entities.py` | Entity resolution + detail + widget data endpoints |
| `backend/app/tests/test_entities.py` | Tests for all entity endpoints |
| `frontend/src/types/entities.ts` | TypeScript interfaces matching backend models |
| `frontend/src/components/SearchBar.tsx` | Chatbot-style search input with disambiguation |
| `frontend/src/components/EntityHeader.tsx` | Entity name/type/fields header card |
| `frontend/src/components/SmartlistWidget.tsx` | Paginated read-only data table widget |
| `frontend/src/components/Pagination.tsx` | Reusable prev/next pagination controls |
| `frontend/src/pages/EntityPage.tsx` | Entity page — fetches detail, renders header + widgets |
| `frontend/src/styles/search.css` | Search bar and disambiguation styles |
| `frontend/src/styles/entity.css` | Entity page and header styles |
| `frontend/src/styles/smartlist.css` | Table widget and pagination styles |

## Modified Files (4)

| File | Change |
|------|--------|
| `backend/app/main.py` | Register `entities_router` |
| `frontend/src/App.tsx` | Add `/entity/:entityType/:entityId` route |
| `frontend/src/pages/HomePage.tsx` | Replace static welcome with SearchBar |
| `frontend/src/components/Layout.tsx` | Make logo a link to `/` for navigation back to search |

---

## Stage 1: Backend Entity Models + Resolution Endpoint

### `backend/app/api/entity_models.py` — New Pydantic models

```python
EntityCandidate(entity_type, entity_id, display_name)
EntityResolution(resolved, entity_type, entity_id, display_name, message, candidates[])
EntityField(label, value, format)     # format: "currency", "percent", "number", "text"
ColumnConfig(key, label, format, sortable)
WidgetConfig(widget_id, title, endpoint, columns[], default_page_size)
EntityDetail(entity_type, entity_id, display_name, header_fields[], widgets[])
```

### `backend/app/api/entities.py` — Resolution endpoint

**`GET /api/entities/resolve?q=<input>`**

Resolution logic (ordered priority, short-circuits on first exact match):
1. Exact ticker match (case-insensitive) → stock entity
2. Exact person_id match (case-insensitive, e.g. "PER-001") → person entity
3. Exact dataset name match (case-insensitive, e.g. "stocks") → dataset entity
4. Fuzzy: company_name contains query → stock candidates
5. Fuzzy: person name contains query → person candidates
6. Fuzzy: dataset display_name contains query → dataset candidates
7. Single fuzzy match → resolved with that entity
8. Multiple fuzzy matches → resolved=false, candidates list returned
9. No matches → resolved=false, message="No results"

Uses existing `get_data_provider()` which caches CSVs in memory — resolution will be well under 300ms.

### Wire into `backend/app/main.py`

Add `from app.api.entities import router as entities_router` and `application.include_router(entities_router)`.

---

## Stage 2: Backend Entity Detail + Widget Data Endpoints

All in `backend/app/api/entities.py`:

### `GET /api/entities/{entity_type}/{entity_id}` — Entity detail

Returns `EntityDetail` with header_fields and widget configs. The widget configs tell the frontend which endpoints to call and what columns to display. This backend-driven approach means adding new widgets requires zero frontend changes.

**Stock page** (e.g. `/api/entities/stock/AAPL`):
- Header: ticker, company_name, sector, industry, price (currency), market_cap_b (number), pe_ratio, dividend_yield (percent), 52w_high/low (currency), eps (currency), exchange
- Widget 1: "Related People" → endpoint `/api/entities/stock/AAPL/people`, columns: name, title, organization, type
- Widget 2: "Related Files" → endpoint `/api/entities/stock/AAPL/files`, columns: filename, type, date, description

**Person page** (e.g. `/api/entities/person/PER-001`):
- Header: person_id, name, title, organization, type
- Widget 1: "Covered Stocks" → endpoint `/api/entities/person/PER-001/stocks`, columns: ticker, company_name, sector, price, market_cap_b, pe_ratio

**Dataset page** (e.g. `/api/entities/dataset/stocks`):
- Header: dataset_id, display_name, description, record_count (number), category
- Widget 1: "{display_name} Contents" → endpoint `/api/data/stocks` (reuses existing), columns: dynamically derived from CSV headers

### Widget data endpoints (return `PaginatedResponse`)

- `GET /api/entities/stock/{ticker}/people?page=1&page_size=10` — Filters people.csv: includes only people whose semicolon-separated `tickers` field contains the given ticker
- `GET /api/entities/stock/{ticker}/files?page=1&page_size=10` — Filters file manifest: includes only files whose `tickers` array contains the given ticker
- `GET /api/entities/person/{person_id}/stocks?page=1&page_size=10` — Looks up person's `tickers` field, fetches each stock record, returns as paginated list

### `backend/app/tests/test_entities.py`

Tests: resolve exact ticker, case-insensitive, person_id, dataset name, fuzzy company name, ambiguous query, no match, entity detail for each type, widget data endpoints (stock/people, stock/files, person/stocks), 404 for invalid entities.

---

## Stage 3: Frontend Types + SmartlistWidget

### `frontend/src/types/entities.ts`

TypeScript interfaces matching all backend models: `EntityResolution`, `EntityCandidate`, `EntityField`, `ColumnConfig`, `WidgetConfig`, `EntityDetail`, `PaginatedResponse<T>`.

### `frontend/src/components/SmartlistWidget.tsx`

The core reusable widget component. Receives `WidgetConfig` as props.

Behavior:
- On mount, fetches `endpoint?page=1&page_size=defaultPageSize` via axios
- Shows loading spinner while fetching (each widget independent)
- Renders table with column headers from `columns` config
- Formats values per column.format (currency→$, percent→%, number→locale)
- Pagination controls at bottom (Previous/Next, "Page X of Y", total count)
- Clickable sortable column headers toggle `sort_by`/`sort_order` params
- Error state: inline message with retry button
- Empty state: "No records found" message
- Manages its own state (loading, error, data, page) independently

### `frontend/src/components/Pagination.tsx`

Extracted pagination controls: Previous/Next buttons (disabled at boundaries), page info text, total records.

### `frontend/src/styles/smartlist.css`

Table styling using existing CSS variables. Classes: `.smartlist`, `.smartlist__title`, `.smartlist__table`, `.smartlist__th` (sortable indicator), `.smartlist__td`, `.smartlist__loading`, `.smartlist__error`, `.smartlist__empty`, `.smartlist__pagination`.

---

## Stage 4: Frontend Entity Page + Header

### `frontend/src/pages/EntityPage.tsx`

Uses `useParams()` to read `entityType` and `entityId`. On mount:
1. Fetches `GET /api/entities/{entityType}/{entityId}`
2. Renders `EntityHeader` with the response's header_fields
3. Maps `widgets[]` → renders one `SmartlistWidget` per entry
4. Shows loading spinner during fetch, error message on failure
5. "Back to Search" link at top

### `frontend/src/components/EntityHeader.tsx`

Renders entity display_name as heading, entity_type badge, and a grid of formatted key-value fields from `header_fields[]`.

### `frontend/src/styles/entity.css`

Entity page layout, header card, field grid, back link, type badge. Uses existing CSS variables.

### `frontend/src/App.tsx` — Add route

```tsx
<Route path="/entity/:entityType/:entityId" element={<AuthGuard><EntityPage /></AuthGuard>} />
```

---

## Stage 5: Frontend Search + Updated HomePage

### `frontend/src/components/SearchBar.tsx`

Chatbot-style search input (anticipates Phase 4 LLM integration):
- Text input with placeholder "Search by ticker, name, or dataset..."
- Submit on Enter or button click (not typeahead — Phase 2 enhancement)
- Loading spinner while resolving
- On single resolve: navigates to `/entity/{type}/{id}`
- On multiple candidates: renders clickable disambiguation list below
- On no match: shows "No entity found. LLM-powered answers coming soon."

### `frontend/src/pages/HomePage.tsx` — Transform

Replace static welcome content with centered SearchBar. Keep Layout wrapper.

### `frontend/src/components/Layout.tsx` — Minor update

Make the "GoldMine" logo text a `<Link to="/">` so users can navigate back to search from any entity page.

### `frontend/src/styles/search.css`

Centered search container, styled input matching existing form inputs, disambiguation list, placeholder message.

---

## Stage 6: Tests + Polish

- Run `pytest -v` — all tests pass (existing 28 + new entity tests)
- Full end-to-end flow: login → search "AAPL" → stock page with people/files widgets → back → search "PER-001" → person page with stocks widget → search "stocks" → dataset page with contents table
- Verify entity resolution < 300ms, page load ≤ 3s
- Verify 404 handling for invalid entity types/IDs
- TypeScript builds cleanly (`npx tsc -b`)
- Commit

---

## Key Design Decisions

1. **Backend-driven entity pages**: The `EntityDetail` response includes header fields AND widget configs (endpoint, columns, title). The frontend renders generically — adding a new entity type or widget is a backend-only change. This anticipates Phase 2 widget configurability and Phase 3 Analyst Packs.

2. **Dedicated widget data endpoints** under `/api/entities/`: Rather than overloading the generic `/api/data/` with relationship filters, specific endpoints like `/api/entities/stock/{ticker}/people` handle cross-reference queries (splitting semicolon-separated tickers fields). Keeps the generic API clean.

3. **Single `EntityPage` component for all types**: Because the backend drives layout, no `StockPage`/`PersonPage`/`DatasetPage` needed. Extensible for the Phase 3 Analyst Pack entity type with zero frontend changes.

4. **Submit-on-Enter search**: Avoids debounce complexity for Phase 1. The input is styled chatbot-style to anticipate Phase 4 LLM integration — the same input will later route to LLM when no entity resolves.

5. **No new npm dependencies**: SmartlistWidget, pagination, search built with plain HTML + CSS, consistent with existing approach.

---

## Verification Checklist

| Criteria | How to verify |
|---|---|
| Search resolves "AAPL" to stock page | Type "AAPL" on landing page, redirected to stock entity page |
| Search resolves "PER-001" to person page | Type "PER-001", redirected to person entity page |
| Search resolves "stocks" to dataset page | Type "stocks", redirected to dataset entity page |
| Fuzzy search works | Type "Apple", resolves to Apple Inc. stock |
| Ambiguous search shows candidates | Type a name matching multiple entities, see disambiguation list |
| Unresolvable input shows message | Type "ZZZZ", see placeholder message |
| Entity pages show correct header | Stock page shows ticker, price, sector, etc. |
| Smartlist widgets load independently | Each widget has its own loading spinner |
| Pagination works in widgets | Click Next/Previous, data updates |
| Sort works in widgets | Click column header, data re-sorts |
| Entity resolution < 300ms | Check DevTools Network tab |
| Entity page load ≤ 3s | Check DevTools |
| Back navigation works | Click "GoldMine" logo or back link, returns to search |
| All backend tests pass | `pytest -v` |
| TypeScript builds | `npx tsc -b` |
