"""API endpoints for analyst pages (dashboard/module builder).

GET    /api/pages                           — list user's + shared pages
POST   /api/pages                           — create a new page
GET    /api/pages/{page_id}                 — get full page with tiles
PATCH  /api/pages/{page_id}                 — update page (owner only)
POST   /api/pages/{page_id}/tiles           — add a tile
DELETE /api/pages/{page_id}/tiles/{tile_id} — remove a tile
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

import structlog

from app.mode2.db import get_conn

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/pages", tags=["pages"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class CreatePageRequest(BaseModel):
    title: str
    description: str | None = None
    tiles: list[dict[str, Any]] = Field(default_factory=list)


class UpdatePageRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    tiles: list[dict[str, Any]] | None = None
    is_shared: bool | None = None


class AddTileRequest(BaseModel):
    title: str
    tool: str
    params: dict[str, Any] = Field(default_factory=dict)
    chart: dict[str, Any] | None = None
    position: dict[str, Any] = Field(
        default_factory=lambda: {"row": 0, "col": 0, "width": 2, "height": 1}
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_user_id(request: Request) -> str:
    user = getattr(request.state, "user", None)
    if user and hasattr(user, "username"):
        return user.username
    return "anonymous"


def _serialize_row(row: Any) -> dict:
    """Convert an asyncpg Record to a JSON-safe dict."""
    import json as _json
    from datetime import date, datetime
    from decimal import Decimal

    d = dict(row)
    for k, v in d.items():
        if isinstance(v, uuid.UUID):
            d[k] = str(v)
        elif isinstance(v, (datetime, date)):
            d[k] = v.isoformat()
        elif isinstance(v, Decimal):
            d[k] = float(v)
        elif isinstance(v, str) and k == "tiles":
            # JSONB columns come back as strings from asyncpg — parse them
            try:
                d[k] = _json.loads(v)
            except (ValueError, TypeError):
                pass
    return d


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def list_pages(request: Request) -> list[dict]:
    """List user's own pages plus all shared pages."""
    user_id = _get_user_id(request)

    async with get_conn() as conn:
        rows = await conn.fetch(
            """SELECT id, user_id, title, description, is_shared,
                      jsonb_array_length(tiles) as tile_count,
                      created_at, updated_at
               FROM pages
               WHERE user_id = $1 OR is_shared = true
               ORDER BY updated_at DESC
               LIMIT 100""",
            user_id,
        )

    return [_serialize_row(r) for r in rows]


@router.post("")
async def create_page(body: CreatePageRequest, request: Request) -> dict:
    """Create a new page."""
    user_id = _get_user_id(request)
    import json

    async with get_conn() as conn:
        row = await conn.fetchrow(
            """INSERT INTO pages (user_id, title, description, tiles)
               VALUES ($1, $2, $3, $4::jsonb)
               RETURNING *""",
            user_id, body.title, body.description, json.dumps(body.tiles),
        )

    return _serialize_row(row)


@router.get("/{page_id}")
async def get_page(page_id: str, request: Request) -> dict:
    """Get full page with tiles."""
    user_id = _get_user_id(request)

    async with get_conn() as conn:
        row = await conn.fetchrow(
            """SELECT *
               FROM pages
               WHERE id = $1::uuid
               AND (user_id = $2 OR is_shared = true)""",
            uuid.UUID(page_id), user_id,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Page not found")

    return _serialize_row(row)


@router.patch("/{page_id}")
async def update_page(
    page_id: str,
    body: UpdatePageRequest,
    request: Request,
) -> dict:
    """Update a page. Owner only."""
    user_id = _get_user_id(request)
    import json

    # Build dynamic SET clause
    sets: list[str] = ["updated_at = NOW()"]
    params: list[Any] = []
    idx = 1

    if body.title is not None:
        sets.append(f"title = ${idx}")
        params.append(body.title)
        idx += 1
    if body.description is not None:
        sets.append(f"description = ${idx}")
        params.append(body.description)
        idx += 1
    if body.tiles is not None:
        sets.append(f"tiles = ${idx}::jsonb")
        params.append(json.dumps(body.tiles))
        idx += 1
    if body.is_shared is not None:
        sets.append(f"is_shared = ${idx}")
        params.append(body.is_shared)
        idx += 1

    params.append(uuid.UUID(page_id))
    params.append(user_id)

    async with get_conn() as conn:
        row = await conn.fetchrow(
            f"""UPDATE pages SET {', '.join(sets)}
                WHERE id = ${idx}::uuid AND user_id = ${idx + 1}
                RETURNING *""",
            *params,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Page not found or not owner")

    return _serialize_row(row)


@router.post("/{page_id}/tiles")
async def add_tile(
    page_id: str,
    body: AddTileRequest,
    request: Request,
) -> dict:
    """Add a tile to a page."""
    user_id = _get_user_id(request)
    import json

    tile = {
        "id": str(uuid.uuid4()),
        "title": body.title,
        "tool": body.tool,
        "params": body.params,
        "chart": body.chart,
        "position": body.position,
    }

    async with get_conn() as conn:
        row = await conn.fetchrow(
            """UPDATE pages SET
                 tiles = tiles || $1::jsonb,
                 updated_at = NOW()
               WHERE id = $2::uuid AND user_id = $3
               RETURNING *""",
            json.dumps([tile]), uuid.UUID(page_id), user_id,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Page not found or not owner")

    return _serialize_row(row)


@router.delete("/{page_id}/tiles/{tile_id}")
async def remove_tile(
    page_id: str,
    tile_id: str,
    request: Request,
) -> dict:
    """Remove a tile by its id."""
    user_id = _get_user_id(request)

    async with get_conn() as conn:
        row = await conn.fetchrow(
            """UPDATE pages SET
                 tiles = COALESCE(
                   (SELECT jsonb_agg(tile)
                    FROM jsonb_array_elements(tiles) AS tile
                    WHERE tile->>'id' != $1),
                   '[]'::jsonb
                 ),
                 updated_at = NOW()
               WHERE id = $2::uuid AND user_id = $3
               RETURNING *""",
            tile_id, uuid.UUID(page_id), user_id,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Page not found or not owner")

    return _serialize_row(row)
