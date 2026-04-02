from __future__ import annotations

import json

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel

from app.api.entity_models import WidgetConfig
from app.api.entities import _build_stock_detail, _build_person_detail, _build_dataset_detail
from app.auth.users import USERS
from app.exceptions import GoldMineError, NotFoundError
from app.logging_config import get_logger
from app.views.factory import get_views_provider
from app.views.models import (
    AnalystPack,
    AnalystPackCreate,
    AnalystPackUpdate,
    MCPTileRef,
    SavedView,
    SavedViewCreate,
    SavedViewUpdate,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/views", tags=["views"])


def _enrich_pack(pack: AnalystPack) -> AnalystPack:
    """Fill in owner_display_name from the USERS registry."""
    user_data = USERS.get(pack.owner)
    if user_data:
        pack.owner_display_name = user_data["display_name"]
    else:
        pack.owner_display_name = pack.owner
    return pack


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
    return [_enrich_pack(p) for p in provider.list_packs(owner=user.username)]


@router.post("/packs/", status_code=201)
async def create_pack(request: Request, body: AnalystPackCreate) -> AnalystPack:
    user = request.state.user
    provider = get_views_provider()
    return _enrich_pack(provider.create_pack(body, owner=user.username))


@router.get("/packs/entity/{entity_type}/{entity_id}")
async def get_entity_pack(request: Request, entity_type: str, entity_id: str) -> AnalystPack:
    user = request.state.user
    provider = get_views_provider()
    pack = provider.get_entity_pack(entity_type, entity_id)
    if pack is None:
        create_body = AnalystPackCreate(
            name=f"{entity_id} Pack",
            widgets=[],
            entity_type=entity_type,
            entity_id=entity_id,
        )
        pack = provider.create_pack(create_body, owner=user.username)
    return _enrich_pack(pack)


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
    return _enrich_pack(pack)


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
    return _enrich_pack(updated)


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
# MCP Tile execution
# ---------------------------------------------------------------------------

@router.post("/packs/{pack_id}/tiles/{tile_id}/execute")
async def execute_tile(request: Request, pack_id: str, tile_id: str) -> dict:
    """Execute an MCP tool call for a specific tile and return the result."""
    user = request.state.user
    provider = get_views_provider()
    pack = provider.get_pack(pack_id)
    if pack is None:
        raise NotFoundError(f"Pack '{pack_id}' not found")
    if pack.owner != user.username and not pack.is_shared:
        raise NotFoundError(f"Pack '{pack_id}' not found")

    tile = next((t for t in pack.mcp_tiles if t.tile_id == tile_id), None)
    if tile is None:
        raise NotFoundError(f"Tile '{tile_id}' not found")

    params = dict(tile.params)
    if tile.is_template and pack.ticker_context:
        params = _substitute_ticker(params, pack.ticker_context)

    from app.mcp.registry import get_registry
    registry = get_registry()
    result = await registry.call_tool(tile.tool, params)

    if result.error:
        return {"error": result.error, "rows": [], "columns": []}

    # Add source_label for estimates (for chart grouping)
    if tile.tool == "get_estimates":
        for row in result.rows:
            source = row.get("source", "")
            firm = row.get("firm") or ""
            if firm:
                row["source_label"] = firm
            else:
                row["source_label"] = source.title() if source else ""

    return {
        "rows": result.rows,
        "row_count": result.row_count,
        "columns": result.columns,
        "preferred_presentation": result.preferred_presentation,
        "chart_config": result.chart_config,
        "formatted_markdown": result.formatted_markdown,
        "tile_id": tile_id,
        "tool": tile.tool,
        "display_type": tile.display_type,
    }


@router.patch("/packs/{pack_id}/tiles/{tile_id}/state")
async def update_tile_state(request: Request, pack_id: str, tile_id: str) -> dict:
    """Update a tile's state_override (grid customizations)."""
    user = request.state.user
    provider = get_views_provider()
    pack = provider.get_pack(pack_id)
    if pack is None:
        raise NotFoundError(f"Pack '{pack_id}' not found")
    if pack.owner != user.username:
        raise GoldMineError("Cannot modify another user's pack", status_code=403)

    body = await request.json()
    tile = next((t for t in pack.mcp_tiles if t.tile_id == tile_id), None)
    if tile is None:
        raise NotFoundError(f"Tile '{tile_id}' not found")

    tile.state_override = body

    from app.views.models import AnalystPackUpdate as _Update
    provider.update_pack(pack_id, _Update(mcp_tiles=pack.mcp_tiles))
    return {"status": "ok", "tile_id": tile_id}


# ---------------------------------------------------------------------------
# Pack generation from chat conversation
# ---------------------------------------------------------------------------

class PackGenerateRequest(BaseModel):
    session_id: str | None = None
    messages: list[dict]


@router.post("/packs/generate", status_code=201)
async def generate_pack(request: Request, body: PackGenerateRequest) -> dict:
    """Generate a pack from conversation tool calls."""
    from datetime import datetime as dt

    user = request.state.user

    tool_calls = _extract_tool_calls_from_messages(body.messages)
    if not tool_calls:
        return {"error": "No data queries found in conversation", "pack_id": None}

    tiles = _build_tiles_from_tool_calls(tool_calls)
    pack_name = _generate_pack_name(tool_calls)

    tickers = list(set(t for tc in tool_calls for t in tc.get("tickers", [])))
    ticker_context = tickers[0] if len(tickers) == 1 else None

    n_tiles = len(tiles)
    n_rows = (n_tiles + 1) // 2
    row_columns = [2 if i < n_rows - 1 or n_tiles % 2 == 0 else 1 for i in range(n_rows)]

    for i, tile in enumerate(tiles):
        tile.row = i // 2
        tile.col = i % 2

    provider = get_views_provider()
    pack = provider.create_pack(
        AnalystPackCreate(
            name=pack_name,
            description=f"Generated from chat on {dt.now().strftime('%b %d, %Y')}",
            mcp_tiles=tiles,
            row_columns=row_columns,
            ticker_context=ticker_context,
            source_conversation_id=body.session_id,
        ),
        owner=user.username,
    )

    return {
        "pack_id": pack.pack_id,
        "pack_name": pack.name,
        "tile_count": len(tiles),
        "redirect_url": f"/pack/{pack.pack_id}",
    }


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

    if override.column_filters:
        widget.initial_column_filters = override.column_filters
        widget.has_overrides = True


def _substitute_ticker(params: dict, ticker: str) -> dict:
    """Replace {{ticker}} placeholder in params with actual ticker value."""
    result = {}
    for key, value in params.items():
        if isinstance(value, list):
            result[key] = [ticker if v == "{{ticker}}" else v for v in value]
        elif isinstance(value, str) and "{{ticker}}" in value:
            result[key] = value.replace("{{ticker}}", ticker)
        else:
            result[key] = value
    return result


_SKIP_TOOLS = {"search_tools", "search_universe", "run_workflow", "model_edit", "search_documents"}


def _extract_tool_calls_from_messages(messages: list[dict]) -> list[dict]:
    """Extract MCP tool calls from conversation messages."""
    tool_calls: list[dict] = []
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        for call in msg.get("tool_calls", []):
            tool_name = call.get("name", "")
            if tool_name in _SKIP_TOOLS:
                continue
            tool_input = call.get("input", {})
            tickers = tool_input.get("tickers", [])
            if not tickers and tool_input.get("ticker"):
                tickers = [tool_input["ticker"]]
            tool_calls.append({"tool": tool_name, "params": tool_input, "tickers": tickers})

    # Deduplicate
    seen: set[str] = set()
    unique: list[dict] = []
    for tc in tool_calls:
        key = f"{tc['tool']}:{json.dumps(tc['params'], sort_keys=True, default=str)}"
        if key not in seen:
            seen.add(key)
            unique.append(tc)
    return unique


_TOOL_LABELS = {
    "get_estimates": "Estimates",
    "get_estimate_history": "Estimate Revisions",
    "get_alt_data": "Alt Data",
    "get_pnl_history": "P&L History",
    "get_daily_pnl": "P&L",
    "get_financial_metrics": "Financials",
    "get_stock_history": "Price History",
    "get_portfolio_concentration": "Concentration",
    "get_portfolio_risk": "Risk",
    "get_guidance": "Guidance",
    "get_trade_requests": "Trade Requests",
}

_CHART_TOOLS = {"get_alt_data", "get_pnl_history", "get_estimate_history", "get_stock_history"}


def _build_tiles_from_tool_calls(tool_calls: list[dict]) -> list[MCPTileRef]:
    """Convert extracted tool calls into MCPTileRef tile configs."""
    from app.mcp.registry import get_registry
    registry = get_registry()

    # Display type overrides for pack visualization
    PACK_DISPLAY_OVERRIDES: dict[str, str] = {
        "get_estimates": "plotly_bar",
        "get_estimate_history": "plotly_line",
        "get_alt_data": "plotly_line",
        "get_pnl_history": "plotly_line",
        "get_stock_history": "plotly_line",
        "get_price_history": "plotly_line",
    }

    tiles: list[MCPTileRef] = []
    for tc in tool_calls:
        tool = tc["tool"]
        params = tc["params"]

        server, _ = registry.find_server(tool)
        mcp_tool = server.get_tool(tool) if server else None

        # Use override if available, then check MCP preferred_presentation
        if tool in PACK_DISPLAY_OVERRIDES:
            display_type = PACK_DISPLAY_OVERRIDES[tool]
        elif tool in _CHART_TOOLS or (mcp_tool and mcp_tool.preferred_presentation == "chart"):
            display_type = "plotly_line"
        else:
            display_type = "ag_grid"

        # Build chart_config
        if tool == "get_estimates":
            chart_config = {
                "x_column": "period",
                "y_column": "value",
                "series_column": "source_label",
                "y_label": "Estimate",
                "title": _generate_tile_title(tool, params),
                "formatters": {"value": "currency"},
                "barmode": "group",
            }
        elif mcp_tool and mcp_tool.chart_config:
            chart_config = mcp_tool.chart_config
        else:
            chart_config = None

        title = _generate_tile_title(tool, params)
        tiles.append(MCPTileRef(
            title=title,
            tool=tool,
            params=params,
            display_type=display_type,
            chart_config=chart_config,
        ))
    return tiles


def _generate_tile_title(tool: str, params: dict) -> str:
    """Generate a human-readable title for a tile."""
    tickers = params.get("tickers") or ([params["ticker"]] if params.get("ticker") else [])
    ticker_str = ", ".join(tickers[:3])
    if len(tickers) > 3:
        ticker_str += f" +{len(tickers) - 3}"

    label = _TOOL_LABELS.get(tool, tool.replace("_", " ").title())

    metrics = params.get("metrics") or ([params["metric"]] if params.get("metric") else [])
    metric_str = ""
    if metrics:
        metric_str = " — " + ", ".join(m.replace("_", " ").title() for m in metrics[:2])

    return f"{ticker_str} {label}{metric_str}" if ticker_str else f"{label}{metric_str}"


def _generate_pack_name(tool_calls: list[dict]) -> str:
    """Generate a pack name from the tool calls."""
    from datetime import datetime as dt

    tickers = list(set(t for tc in tool_calls for t in tc.get("tickers", [])))
    if len(tickers) == 1:
        return f"{tickers[0]} Research Pack"
    elif len(tickers) <= 3:
        return f"{', '.join(tickers)} Pack"
    return f"Research Pack — {dt.now().strftime('%b %d')}"
