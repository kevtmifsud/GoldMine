from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response

from app.api.entity_models import WidgetConfig
from app.api.entities import _build_stock_detail, _build_person_detail, _build_dataset_detail
from app.exceptions import GoldMineError, NotFoundError
from app.logging_config import get_logger
from app.views.factory import get_views_provider
from app.views.models import (
    AnalystPack,
    AnalystPackCreate,
    AnalystPackUpdate,
    SavedView,
    SavedViewCreate,
    SavedViewUpdate,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/views", tags=["views"])


# ---------------------------------------------------------------------------
# Saved Views — list & create (no path params, must come before /{view_id})
# ---------------------------------------------------------------------------

@router.get("/")
async def list_views(
    request: Request,
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
) -> list[SavedView]:
    user = request.state.user
    provider = get_views_provider()
    return provider.list_views(owner=user.username, entity_type=entity_type, entity_id=entity_id)


@router.post("/", status_code=201)
async def create_view(request: Request, body: SavedViewCreate) -> SavedView:
    user = request.state.user
    provider = get_views_provider()
    return provider.create_view(body, owner=user.username)


# ---------------------------------------------------------------------------
# Analyst Packs (must come before /{view_id} to avoid "packs" matching)
# ---------------------------------------------------------------------------

@router.get("/packs/")
async def list_packs(request: Request) -> list[AnalystPack]:
    user = request.state.user
    provider = get_views_provider()
    return provider.list_packs(owner=user.username)


@router.post("/packs/", status_code=201)
async def create_pack(request: Request, body: AnalystPackCreate) -> AnalystPack:
    user = request.state.user
    provider = get_views_provider()
    return provider.create_pack(body, owner=user.username)


@router.get("/packs/{pack_id}/resolved")
async def resolve_pack(request: Request, pack_id: str) -> list[WidgetConfig]:
    user = request.state.user
    provider = get_views_provider()
    pack = provider.get_pack(pack_id)
    if pack is None:
        raise NotFoundError(f"Pack '{pack_id}' not found")
    if pack.owner != user.username and not pack.is_shared:
        raise NotFoundError(f"Pack '{pack_id}' not found")

    resolved: list[WidgetConfig] = []
    for ref in pack.widgets:
        try:
            if ref.source_entity_type == "stock":
                detail = _build_stock_detail(ref.source_entity_id)
            elif ref.source_entity_type == "person":
                detail = _build_person_detail(ref.source_entity_id)
            elif ref.source_entity_type == "dataset":
                detail = _build_dataset_detail(ref.source_entity_id)
            else:
                continue
        except Exception:
            continue

        widget = None
        for w in detail.widgets:
            if w.widget_id == ref.widget_id:
                widget = w
                break
        if widget is None:
            continue

        if ref.title_override:
            widget.title = ref.title_override
        if ref.overrides:
            _apply_widget_override(widget, ref.overrides)

        resolved.append(widget)

    return resolved


@router.get("/packs/{pack_id}")
async def get_pack(request: Request, pack_id: str) -> AnalystPack:
    user = request.state.user
    provider = get_views_provider()
    pack = provider.get_pack(pack_id)
    if pack is None:
        raise NotFoundError(f"Pack '{pack_id}' not found")
    if pack.owner != user.username and not pack.is_shared:
        raise NotFoundError(f"Pack '{pack_id}' not found")
    return pack


@router.put("/packs/{pack_id}")
async def update_pack(request: Request, pack_id: str, body: AnalystPackUpdate) -> AnalystPack:
    user = request.state.user
    provider = get_views_provider()
    pack = provider.get_pack(pack_id)
    if pack is None:
        raise NotFoundError(f"Pack '{pack_id}' not found")
    if pack.owner != user.username:
        raise GoldMineError("Cannot modify another user's pack", status_code=403)
    updated = provider.update_pack(pack_id, body)
    if updated is None:
        raise NotFoundError(f"Pack '{pack_id}' not found")
    return updated


@router.delete("/packs/{pack_id}", status_code=204, response_class=Response)
async def delete_pack(request: Request, pack_id: str) -> Response:
    user = request.state.user
    provider = get_views_provider()
    pack = provider.get_pack(pack_id)
    if pack is None:
        raise NotFoundError(f"Pack '{pack_id}' not found")
    if pack.owner != user.username:
        raise GoldMineError("Cannot delete another user's pack", status_code=403)
    provider.delete_pack(pack_id)


# ---------------------------------------------------------------------------
# Saved Views — single-item ops (/{view_id} must come after /packs/)
# ---------------------------------------------------------------------------

@router.get("/{view_id}")
async def get_view(request: Request, view_id: str) -> SavedView:
    user = request.state.user
    provider = get_views_provider()
    view = provider.get_view(view_id)
    if view is None:
        raise NotFoundError(f"View '{view_id}' not found")
    if view.owner != user.username and not view.is_shared:
        raise NotFoundError(f"View '{view_id}' not found")
    return view


@router.put("/{view_id}")
async def update_view(request: Request, view_id: str, body: SavedViewUpdate) -> SavedView:
    user = request.state.user
    provider = get_views_provider()
    view = provider.get_view(view_id)
    if view is None:
        raise NotFoundError(f"View '{view_id}' not found")
    if view.owner != user.username:
        raise GoldMineError("Cannot modify another user's view", status_code=403)
    updated = provider.update_view(view_id, body)
    if updated is None:
        raise NotFoundError(f"View '{view_id}' not found")
    return updated


@router.delete("/{view_id}", status_code=204, response_class=Response)
async def delete_view(request: Request, view_id: str) -> Response:
    user = request.state.user
    provider = get_views_provider()
    view = provider.get_view(view_id)
    if view is None:
        raise NotFoundError(f"View '{view_id}' not found")
    if view.owner != user.username:
        raise GoldMineError("Cannot delete another user's view", status_code=403)
    provider.delete_view(view_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _apply_widget_override(widget: WidgetConfig, override: "WidgetStateOverride") -> None:
    from app.views.models import WidgetStateOverride

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
