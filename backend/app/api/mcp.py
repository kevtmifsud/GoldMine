"""API endpoints for the MCP tool catalog and direct tool execution.

GET  /api/mcp/namespaces              — list registered namespaces
GET  /api/mcp/tools                   — list tools (optional ?namespace= filter)
GET  /api/mcp/tools/{full_tool_name}  — detail for one tool
POST /api/mcp/execute                 — execute a tool directly
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

import structlog

from app.mcp.registry import get_registry

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ExecuteToolRequest(BaseModel):
    tool: str = Field(..., description="Full tool name e.g. 'legacy__get_financial_metrics'")
    params: dict[str, Any] = Field(default_factory=dict)


class ToolParameterResponse(BaseModel):
    name: str
    type: str
    description: str
    required: bool
    default: Any = None
    enum: list[str] | None = None


class ToolResponse(BaseModel):
    name: str
    namespace: str
    full_name: str
    description: str
    parameters: list[ToolParameterResponse]
    preferred_presentation: str
    chart_config: dict | None = None


class NamespaceResponse(BaseModel):
    namespace: str
    display_name: str
    description: str
    tool_count: int


class ExecuteToolResponse(BaseModel):
    rows: list[dict[str, Any]]
    row_count: int
    columns: list[str]
    preferred_presentation: str
    chart_config: dict | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_user_id(request: Request) -> str:
    user = getattr(request.state, "user", None)
    if user and hasattr(user, "username"):
        return user.username
    return "anonymous"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/namespaces", response_model=list[NamespaceResponse])
async def list_namespaces() -> list[dict]:
    """List all registered MCP namespaces."""
    registry = get_registry()
    return registry.list_namespaces()


@router.get("/tools", response_model=list[ToolResponse])
async def list_tools(
    namespace: str | None = Query(None, description="Filter by namespace"),
) -> list[dict]:
    """List tools, optionally filtered by namespace."""
    registry = get_registry()
    tools = registry.list_tools(namespace)
    return [
        {
            "name": t.name,
            "namespace": t.namespace,
            "full_name": t.full_name,
            "description": t.description,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "description": p.description,
                    "required": p.required,
                    "default": p.default,
                    "enum": p.enum,
                }
                for p in t.parameters
            ],
            "preferred_presentation": t.preferred_presentation,
            "chart_config": t.chart_config,
        }
        for t in tools
    ]


@router.get("/tools/{full_tool_name}", response_model=ToolResponse)
async def get_tool_detail(full_tool_name: str) -> dict:
    """Return detail for one tool by full name (e.g. 'legacy__get_estimates')."""
    registry = get_registry()
    server, tool_name = registry.find_server(full_tool_name)
    if not server:
        raise HTTPException(status_code=404, detail=f"No server found for tool: {full_tool_name}")

    tool = server.get_tool(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool not found: {full_tool_name}")

    return {
        "name": tool.name,
        "namespace": tool.namespace,
        "full_name": tool.full_name,
        "description": tool.description,
        "parameters": [
            {
                "name": p.name,
                "type": p.type,
                "description": p.description,
                "required": p.required,
                "default": p.default,
                "enum": p.enum,
            }
            for p in tool.parameters
        ],
        "preferred_presentation": tool.preferred_presentation,
        "chart_config": tool.chart_config,
    }


@router.post("/execute", response_model=ExecuteToolResponse)
async def execute_tool(
    body: ExecuteToolRequest,
    request: Request,
) -> dict:
    """Execute a tool directly (for slash commands and module builder previews)."""
    user_id = _get_user_id(request)
    logger.info("mcp_execute", tool=body.tool, user_id=user_id)

    registry = get_registry()
    result = await registry.call_tool(body.tool, body.params)

    return {
        "rows": result.rows,
        "row_count": result.row_count,
        "columns": result.columns,
        "preferred_presentation": result.preferred_presentation,
        "chart_config": result.chart_config,
        "error": result.error,
    }
