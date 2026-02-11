# GoldMine Phase 3 — Views, Overrides & Analyst Packs

## Context

Phase 2 delivered chart widgets, server/client-side filtering, and column visibility toggling. Phase 3 adds user personalization: saved views on entity pages, global vs personal filter overrides, and Analyst Packs (custom multi-entity dashboards). Persistence uses JSON flat files following the existing provider/factory pattern. No new npm dependencies.

**Key existing patterns to follow:**
- Backend: factory+provider singletons, Pydantic models, `request.state.user` for current user
- Frontend: functional components with hooks, `useAuth()` for user context, BEM CSS
- Auth: 3 users (analyst1/analyst2/pm1), JWT cookie-based
- Data: CSV files in `data/structured/`, storage in `data/unstructured/`

---

## New Files (16)

| File | Purpose |
|------|---------|
| `backend/app/views/__init__.py` | Package init |
| `backend/app/views/models.py` | Pydantic models: SavedView, AnalystPack, WidgetStateOverride, CRUD request models |
| `backend/app/views/interfaces.py` | Abstract ViewsProvider interface |
| `backend/app/views/json_provider.py` | JSON file-based implementation (reads/writes `data/views/`) |
| `backend/app/views/factory.py` | Singleton factory `get_views_provider()` |
| `backend/app/api/views.py` | REST router: CRUD for views + packs, pack resolution endpoint |
| `backend/app/tests/test_views.py` | View CRUD, access control, override merging tests |
| `backend/app/tests/test_packs.py` | Pack CRUD, access control, widget resolution tests |
| `frontend/src/config/viewsApi.ts` | Typed API service for views and packs |
| `frontend/src/components/ViewToolbar.tsx` | View selector dropdown, save/delete buttons |
| `frontend/src/components/SaveViewDialog.tsx` | Modal for naming and sharing a view |
| `frontend/src/pages/PacksListPage.tsx` | List user's packs + shared packs |
| `frontend/src/pages/PackPage.tsx` | Pack viewer: resolves and renders multi-entity widgets |
| `frontend/src/pages/PackBuilderPage.tsx` | Create/edit packs: entity search, widget picker, reordering |
| `frontend/src/styles/views.css` | View toolbar, save dialog, override indicator styles |
| `frontend/src/styles/packs.css` | Pack list, viewer, and builder styles |

## Modified Files (12)

| File | Change |
|------|--------|
| `backend/app/config/settings.py` | Add `VIEWS_DIR: str = "../data/views"` |
| `backend/app/main.py` | Register views router |
| `backend/app/api/entity_models.py` | Add `active_view_id`, `active_view_name` to EntityDetail; `has_overrides`, `initial_filters`, `initial_sort_by`, `initial_sort_order` to WidgetConfig |
| `backend/app/api/entities.py` | Add `view_id` query param to detail endpoint, `_apply_view_overrides()` merge helper |
| `backend/app/tests/conftest.py` | Reset views provider, add `authed_client_2` fixture, temp views dir |
| `frontend/src/types/entities.ts` | Add SavedView, AnalystPack, WidgetStateOverride, PackWidgetRef interfaces; extend WidgetConfig + EntityDetail |
| `frontend/src/pages/EntityPage.tsx` | View toolbar integration, widget state collection via refs |
| `frontend/src/components/SmartlistWidget.tsx` | `forwardRef` + `useImperativeHandle` to expose state; initialize from `initial_*` override fields |
| `frontend/src/components/WidgetContainer.tsx` | Forward ref to child widget |
| `frontend/src/App.tsx` | Add `/packs`, `/pack/new`, `/pack/:packId`, `/pack/:packId/edit` routes |
| `frontend/src/components/Layout.tsx` | Add "My Packs" nav link in header |
| `frontend/src/styles/layout.css` | Header nav link styles |

---

## Stage 1: Backend Persistence Layer

**New files:** `backend/app/views/__init__.py`, `models.py`, `interfaces.py`, `json_provider.py`, `factory.py`

**`models.py`** — Core data models:
- `WidgetStateOverride(widget_id, server_filters={}, sort_by=None, sort_order=None, visible_columns=None, page_size=None)` — per-widget state snapshot
- `SavedView(view_id, name, owner, entity_type, entity_id, widget_overrides[], is_shared=False, created_at, updated_at)`
- `SavedViewCreate(name, entity_type, entity_id, widget_overrides[], is_shared)` / `SavedViewUpdate(name?, widget_overrides?, is_shared?)`
- `PackWidgetRef(source_entity_type, source_entity_id, widget_id, title_override=None, overrides=None)` — reference to a widget from any entity
- `AnalystPack(pack_id, name, owner, description, widgets: list[PackWidgetRef], is_shared, created_at, updated_at)`
- `AnalystPackCreate` / `AnalystPackUpdate` — request body models

**`interfaces.py`** — Abstract `ViewsProvider` with: `list_views()`, `get_view()`, `create_view()`, `update_view()`, `delete_view()`, `list_packs()`, `get_pack()`, `create_pack()`, `update_pack()`, `delete_pack()`

**`json_provider.py`** — `JsonViewsProvider` reads/writes `data/views/views.json` and `data/views/packs.json`. Creates directory on init. Full-file read/write per operation (acceptable for demo scale).

**`factory.py`** — Singleton `get_views_provider()` using `settings.VIEWS_DIR`.

**Modify:** `backend/app/config/settings.py` — Add `VIEWS_DIR: str = "../data/views"`

**Verify:** `PYTHONPATH=. .venv/bin/python -c "from app.views.factory import get_views_provider; p = get_views_provider(); print(p.list_views())"` returns `[]`.

---

## Stage 2: Backend Views/Packs API Router

**New file:** `backend/app/api/views.py`

Router prefix: `/api/views`, tags: `["views"]`

**Saved Views endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/views/` | List views (own + shared), filterable by `entity_type`, `entity_id` |
| `GET` | `/api/views/{view_id}` | Get single view (own or shared) |
| `POST` | `/api/views/` | Create view (owner = `request.state.user.username`, view_id = UUID) |
| `PUT` | `/api/views/{view_id}` | Update view (owner-only, 403 otherwise) |
| `DELETE` | `/api/views/{view_id}` | Delete view (owner-only, 204) |

**Analyst Packs endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/views/packs/` | List packs (own + shared) |
| `GET` | `/api/views/packs/{pack_id}` | Get single pack |
| `POST` | `/api/views/packs/` | Create pack |
| `PUT` | `/api/views/packs/{pack_id}` | Update pack (owner-only) |
| `DELETE` | `/api/views/packs/{pack_id}` | Delete pack (owner-only) |
| `GET` | `/api/views/packs/{pack_id}/resolved` | Returns pack with widget refs resolved to full `WidgetConfig[]` |

**Pack resolution logic:** For each `PackWidgetRef`, call the internal `_build_*_detail()` builder for the source entity, find the matching widget by `widget_id`, apply title override and `WidgetStateOverride` if present, return resolved list.

**Modify:** `backend/app/main.py` — Import and register `views_router`.

**Verify:** Start server, `POST /api/views/` creates a view, `GET /api/views/` lists it. Different user cannot `PUT`/`DELETE` it (403).

---

## Stage 3: Entity Detail View Merging

**Modify:** `backend/app/api/entity_models.py`
- `EntityDetail` gains: `active_view_id: str | None = None`, `active_view_name: str | None = None`
- `WidgetConfig` gains: `has_overrides: bool = False`, `initial_filters: dict[str, str] = {}`, `initial_sort_by: str | None = None`, `initial_sort_order: str | None = None`

**Modify:** `backend/app/api/entities.py`
- `get_entity_detail()` accepts optional `view_id: str | None = Query(default=None)` and `request: Request`
- After building base `EntityDetail`, if `view_id` provided:
  1. Fetch view, validate it belongs to the correct entity, check access (owner or shared)
  2. Call `_apply_view_overrides(detail, view)` which:
     - For each `WidgetStateOverride`, finds matching widget by `widget_id`
     - Sets `visible` on `ColumnConfig` based on `visible_columns`
     - Sets `default_page_size` from `page_size`
     - Sets `initial_filters`, `initial_sort_by`, `initial_sort_order` from override
     - Sets `has_overrides = True` on modified widgets
  3. Sets `active_view_id` and `active_view_name` on the detail

**Verify:** `GET /api/entities/stock/AAPL?view_id=<id>` returns merged detail with `active_view_id` set. Without `view_id`, unchanged. Invalid `view_id` returns 404.

---

## Stage 4: Backend Tests

**New file:** `backend/app/tests/test_views.py`
- Views CRUD lifecycle (create, list, get, update, delete)
- Access control: private view hidden from other users
- Shared views visible to others but not editable
- Filtering by entity_type/entity_id
- Entity detail with view_id merging
- Invalid/mismatched view_id returns error

**New file:** `backend/app/tests/test_packs.py`
- Packs CRUD lifecycle
- Access control (same as views)
- Pack resolution endpoint returns resolved WidgetConfigs
- Pack with invalid entity ref gracefully skips

**Modify:** `backend/app/tests/conftest.py`
- Add `GOLDMINE_VIEWS_DIR` env var pointing to temp directory (auto-cleanup)
- Reset `vf._provider = None` in `_reset_providers`
- Add `client_2` / `authed_client_2` fixtures (separate AsyncClient as analyst2) for cross-user tests

**Verify:** `pytest -v` — all existing 63 tests + new tests pass.

---

## Stage 5: Frontend Types + API Service

**Modify:** `frontend/src/types/entities.ts`
- Add interfaces: `WidgetStateOverride`, `SavedView`, `SavedViewCreate`, `SavedViewUpdate`, `PackWidgetRef`, `AnalystPack`, `AnalystPackCreate`, `AnalystPackUpdate`
- Extend `WidgetConfig`: add `has_overrides`, `initial_filters`, `initial_sort_by`, `initial_sort_order`
- Extend `EntityDetail`: add `active_view_id`, `active_view_name`

**New file:** `frontend/src/config/viewsApi.ts`
- Typed functions wrapping axios calls for all view/pack CRUD + resolution endpoints

**Verify:** `npx tsc -b` passes with no errors.

---

## Stage 6: Frontend View Save/Load on EntityPage

**Modify:** `frontend/src/components/SmartlistWidget.tsx`
- Wrap in `forwardRef`, expose `getState(): WidgetStateOverride` via `useImperativeHandle`
- Initialize `serverFilters` from `config.initial_filters` when present
- Initialize `sortBy`/`sortOrder` from `config.initial_sort_by`/`config.initial_sort_order` when present
- Show small override indicator badge in header when `config.has_overrides` is true
- Add `onStateChange` callback to notify parent of widget state modifications

**Modify:** `frontend/src/components/WidgetContainer.tsx`
- Forward ref and `onStateChange` to SmartlistWidget (ChartWidget doesn't need state capture)

**New file:** `frontend/src/components/ViewToolbar.tsx`
- Props: entityType, entityId, activeViewId, activeViewName, views[], dirty, onViewSelect, onOverwriteView, onSaveNewView, onDeleteView, currentUser
- Renders: view selector dropdown ("Default View" + saved views)
- When dirty + on owned saved view: "Overwrite View" (primary) + "Save New View"
- When dirty + default/other's view: "Save New View"
- When not dirty: "Save View"
- Delete button for owned views

**New file:** `frontend/src/components/SaveViewDialog.tsx`
- Modal with: name input, "Share with team" checkbox, Save/Cancel buttons
- Calls `viewsApi.createView()` on save

**Modify:** `frontend/src/pages/EntityPage.tsx`
- Read `view_id` from URL search params (`useSearchParams`)
- Pass `?view_id=` to entity detail API call when present
- Fetch available views via `viewsApi.listViews(entityType, entityId)`
- Render `ViewToolbar` above widgets with dirty state tracking
- Maintain `Map<string, RefObject>` of widget refs keyed by widget_id
- On save new: collect state from all widget refs → `WidgetStateOverride[]` → create view via API
- On overwrite: collect state → update existing view via API → re-fetch detail
- On view select: update URL search param → triggers re-fetch
- Reset dirty flag on view load and after overwrite

**New file:** `frontend/src/styles/views.css`

**Verify:** Save a view on AAPL page, see it in dropdown, select it → overrides applied, switch to "Default View" → back to base config.

---

## Stage 7: Frontend Analyst Packs

**New file:** `frontend/src/pages/PacksListPage.tsx` (route: `/packs`)
- Fetches packs via `viewsApi.listPacks()`
- Card grid: pack name, description, owner, widget count, created_at
- "Create New Pack" button → navigates to `/pack/new`
- Click pack → navigates to `/pack/:packId`

**New file:** `frontend/src/pages/PackPage.tsx` (route: `/pack/:packId`)
- Fetches resolved pack via `viewsApi.getPack(packId)` then `/api/views/packs/{packId}/resolved`
- Renders header with pack metadata (name, owner, description, timestamps)
- Renders resolved widgets using `WidgetContainer`
- "Edit" button → `/pack/:packId/edit`, "Delete" button with confirmation

**New file:** `frontend/src/pages/PackBuilderPage.tsx` (routes: `/pack/new`, `/pack/:packId/edit`)
- Top: name input, description textarea, shared toggle
- Widget picker: text input to search entities via `/api/entities/resolve`, shows available widgets for selected entity with "Add" buttons
- Selected widgets list: reorder with up/down buttons, remove button, optional title override
- Save button → `viewsApi.createPack()` or `updatePack()` → navigate to pack page

**Modify:** `frontend/src/App.tsx`
- Add routes: `/packs`, `/pack/new`, `/pack/:packId`, `/pack/:packId/edit`, `/datasets` (all AuthGuard-wrapped)

**Modify:** `frontend/src/components/Layout.tsx`
- Add "My Packs" nav link in header

**Modify:** `frontend/src/styles/layout.css` — header nav styles, browse card styles

**New file:** `frontend/src/styles/packs.css`

**New file:** `frontend/src/pages/DatasetsPage.tsx` — lists all datasets with links to entity pages

**Modify:** `frontend/src/pages/HomePage.tsx` — browse cards for Stocks, People, Datasets below search

**Verify:** Full flow: create pack with widgets from AAPL + PER-001, view it, edit it, delete it. Shared packs visible to other users.

---

## Stage 8: Tests + Polish

- Run `pytest -v` — all tests pass (existing 63 + new view/pack tests = 90 total)
- Run `npx tsc -b` — TypeScript builds clean
- Edge cases: pack references deleted entity → shows "Widget unavailable" placeholder; empty pack → helpful empty state; name validation → prevent empty names

---

## Key Design Decisions

1. **Backend-driven view merging** — Frontend passes `?view_id=` to entity detail endpoint, receives pre-merged `EntityDetail`. No override logic in TypeScript. Adding view features is a backend-only change.
2. **JSON flat-file storage** — `data/views/views.json` and `packs.json` with `owner` field for filtering. Simple, no database needed, persists across restarts.
3. **`useImperativeHandle` for state capture** — Widgets expose their state via refs rather than lifting state to EntityPage. Preserves the existing self-contained widget pattern.
4. **Pack resolution on backend** — `/api/views/packs/{id}/resolved` endpoint resolves widget refs to full `WidgetConfig[]`, avoiding N+1 entity detail fetches on frontend.
5. **Access control** — Owner-only for write operations (403 for others). Shared items are read-only for non-owners. Access checks in the API layer, not the persistence layer.
6. **No new npm dependencies** — Pack builder uses HTML inputs and button-based reordering.
7. **Overwrite vs Save New** — Dirty state tracking via `onStateChange` callbacks from SmartlistWidget. "Overwrite View" updates in-place (owner-only), "Save New View" creates a copy.

---

## Verification Checklist

| Criteria | How to verify |
|---|---|
| Save a view on entity page | Adjust filters on AAPL page, click Save View, enter name |
| Load a saved view | Select saved view from dropdown, page refreshes with overrides |
| Default view resets overrides | Switch to "Default View", all widgets show base config |
| Overwrite a saved view | Modify a saved view, click "Overwrite View" |
| Save modified view as new | Modify a saved view, click "Save New View" |
| Override indicators visible | Widgets modified by view show "modified" badge |
| Private views hidden from others | Log in as analyst2, analyst1's private views not listed |
| Shared views visible to others | Share a view, other user can see and load it |
| Cannot edit others' views | PUT/DELETE another user's view returns 403 |
| Create an analyst pack | Go to /packs, create pack with widgets from AAPL + PER-001 |
| Pack renders correctly | Open pack, see widgets from multiple entities |
| Edit/delete a pack | Edit pack, remove widget, save. Delete pack from list |
| Pack sharing works | Share a pack, other user can view it |
| Browse entity lists | Click Stocks/People/Datasets cards on homepage |
| All backend tests pass | `pytest -v` (90 tests) |
| TypeScript builds | `npx tsc -b` |
| Data persists across restarts | Restart backend, views and packs still available |
