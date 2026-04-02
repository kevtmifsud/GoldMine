"""Workflows MCP server — run workflows, retrieve outputs, edit models.

Wraps the existing execute_tool() logic for workflow-related tools.
Unlike other MCP servers that query the DB directly, this server
delegates to execute_tool() because the workflow tools have complex
multi-step logic (workflow registry lookups, model regeneration, etc.).
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog

from ..base import MCPServer
from ..types import MCPTool, MCPToolParameter, MCPToolResult

logger = structlog.get_logger(__name__)


def _serialize_value(v: Any) -> Any:
    """Convert DB types to JSON-safe values."""
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, UUID):
        return str(v)
    return v


class WorkflowsServer(MCPServer):
    """Run and retrieve results from GoldMine workflows."""

    namespace = "workflows"
    display_name = "Workflows"
    description = (
        "Run and retrieve results from GoldMine workflows — earnings "
        "previews, financial model generation, and documentation sync. "
        "Also provides access to model outputs and the workflow registry."
    )

    def list_tools(self) -> list[MCPTool]:
        return [
            MCPTool(
                name="run_workflow",
                namespace=self.namespace,
                description=(
                    "Execute a registered workflow.\n\n"
                    "Available workflows:\n"
                    "  earnings_preview — pre-earnings briefing for a ticker\n"
                    "  financial_model_generation — generate/update a financial model\n"
                    "  docs_sync — check documentation consistency\n\n"
                    "Only call when the user explicitly requests running a workflow."
                ),
                parameters=[
                    MCPToolParameter(
                        name="workflow_name",
                        type="string",
                        description="Workflow to run.",
                        required=True,
                    ),
                    MCPToolParameter(
                        name="inputs",
                        type="object",
                        description=(
                            "Workflow inputs. For earnings_preview: "
                            "{ticker, reporting_period, forward_period}. "
                            "For financial_model_generation: {ticker, key_kpis}. "
                            "For docs_sync: {} (no inputs)."
                        ),
                        required=True,
                    ),
                ],
                preferred_presentation="text",
            ),
            MCPTool(
                name="get_workflow_output",
                namespace=self.namespace,
                description=(
                    "Retrieve the most recent output for a completed workflow.\n\n"
                    "For ticker-specific workflows, provide the ticker. "
                    "For tickerless workflows (docs_sync), omit ticker."
                ),
                parameters=[
                    MCPToolParameter(
                        name="workflow_name",
                        type="string",
                        description="Workflow name e.g. 'earnings_preview', 'docs_sync'.",
                        required=True,
                    ),
                    MCPToolParameter(
                        name="ticker",
                        type="string",
                        description="Ticker for ticker-specific workflows. Omit for docs_sync.",
                        required=False,
                    ),
                ],
                preferred_presentation="text",
            ),
            MCPTool(
                name="get_workflow_registry",
                namespace=self.namespace,
                description="List all registered workflows with status and trigger type.",
                parameters=[
                    MCPToolParameter(
                        name="workflow_name",
                        type="string",
                        description="Filter by name. Omit to list all.",
                        required=False,
                    ),
                ],
                preferred_presentation="table",
            ),
            MCPTool(
                name="get_model_outputs",
                namespace=self.namespace,
                description=(
                    "Retrieve financial model outputs (assumptions, scenarios, KPIs) "
                    "for a ticker. Returns the most recent model version."
                ),
                parameters=[
                    MCPToolParameter(
                        name="tickers",
                        type="array",
                        description="Ticker symbols.",
                        required=True,
                    ),
                ],
                preferred_presentation="table",
            ),
            MCPTool(
                name="model_edit",
                namespace=self.namespace,
                description=(
                    "Edit a financial model assumption and regenerate the model.\n\n"
                    "Reads current assumptions, applies the edit, triggers full "
                    "model regeneration. Returns new version confirmation."
                ),
                parameters=[
                    MCPToolParameter(
                        name="ticker",
                        type="string",
                        description="Ticker symbol.",
                        required=True,
                    ),
                    MCPToolParameter(
                        name="assumption_key",
                        type="string",
                        description=(
                            "Assumption row name e.g. 'Revenue Growth Rate (%)', "
                            "'Gross Margin (%)', 'WACC (%)'."
                        ),
                        required=True,
                    ),
                    MCPToolParameter(
                        name="scenario",
                        type="string",
                        description="Which scenario: base, bull, or bear.",
                        required=True,
                        enum=["base", "bull", "bear"],
                    ),
                    MCPToolParameter(
                        name="new_value",
                        type="number",
                        description="New value (e.g. 0.15 for 15%).",
                        required=True,
                    ),
                    MCPToolParameter(
                        name="period",
                        type="string",
                        description="Period to apply edit to (e.g. 'FY2027E'). Omit for all forward periods.",
                        required=False,
                    ),
                ],
                preferred_presentation="text",
            ),
        ]

    async def call_tool(
        self,
        tool_name: str,
        params: dict,
        **kwargs: object,
    ) -> MCPToolResult:
        steps = kwargs.get("steps")

        if tool_name == "get_workflow_registry":
            return await self._get_workflow_registry(params, steps)

        # For complex tools, delegate to existing execute_tool()
        if tool_name in ("run_workflow", "get_workflow_output",
                         "get_model_outputs", "model_edit"):
            return await self._delegate_to_execute_tool(
                tool_name, params, kwargs,
            )

        return MCPToolResult(
            tool_name=tool_name,
            namespace=self.namespace,
            rows=[], row_count=0, columns=[],
            preferred_presentation="text",
            error=f"Unknown tool: {tool_name}",
        )

    async def _delegate_to_execute_tool(
        self,
        tool_name: str,
        params: dict,
        kwargs: dict,
    ) -> MCPToolResult:
        """Delegate to execute_tool() in tools.py and parse the JSON result."""
        from app.mode2.tools import execute_tool
        from app.mode2.models import ClassifiedQuery

        classified = kwargs.get("classified") or ClassifiedQuery(
            query_type="workflow",
        )
        query_embedding = kwargs.get("query_embedding") or []
        steps = kwargs.get("steps")

        result_str = await execute_tool(
            tool_name=tool_name,
            tool_input=params,
            classified=classified,  # type: ignore[arg-type]
            query_embedding=query_embedding,  # type: ignore[arg-type]
            steps=steps,  # type: ignore[arg-type]
        )

        # Parse JSON result
        rows: list[dict] = []
        error: str | None = None
        try:
            parsed = json.loads(result_str)
            if isinstance(parsed, list):
                rows = parsed
            elif isinstance(parsed, dict):
                if parsed.get("error") is True or (
                    isinstance(parsed.get("error"), str)
                ):
                    error = parsed.get("user_message") or parsed.get("error") or str(parsed)
                else:
                    rows = [parsed]
        except (json.JSONDecodeError, TypeError):
            error = "Failed to parse tool result"

        columns: list[str] = []
        if rows:
            columns = [c for c in rows[0].keys() if not c.startswith("_")]

        return MCPToolResult(
            tool_name=tool_name,
            namespace=self.namespace,
            rows=rows,
            row_count=len(rows),
            columns=columns,
            preferred_presentation="text" if tool_name in (
                "run_workflow", "model_edit", "get_workflow_output",
            ) else "table",
            error=error,
            raw_json=result_str,
        )

    async def _get_workflow_registry(
        self,
        params: dict,
        steps: Any | None = None,
    ) -> MCPToolResult:
        """Query workflow_registry table directly."""
        from app.mode2.db import get_conn

        t0 = time.time()
        workflow_name = params.get("workflow_name")

        async with get_conn() as conn:
            if workflow_name:
                rows = await conn.fetch(
                    """SELECT workflow_name, display_name, description,
                              required_inputs, output_table, trigger_type,
                              schedule_rule, is_active
                       FROM workflow_registry
                       WHERE workflow_name = $1
                       ORDER BY workflow_name""",
                    workflow_name,
                )
            else:
                rows = await conn.fetch(
                    """SELECT workflow_name, display_name, description,
                              required_inputs, output_table, trigger_type,
                              schedule_rule, is_active
                       FROM workflow_registry
                       ORDER BY workflow_name""",
                )

        results = [
            {k: _serialize_value(v) for k, v in dict(r).items()}
            for r in rows
        ]
        duration_ms = int((time.time() - t0) * 1000)

        if steps:
            steps.add(
                label="Fetching workflow registry",
                detail=f"workflow_registry: {len(results)} workflows",
                source="supabase",
                duration_ms=duration_ms,
                result_summary=f"{len(results)} workflows",
            )

        return MCPToolResult(
            tool_name="get_workflow_registry",
            namespace=self.namespace,
            rows=results,
            row_count=len(results),
            columns=[
                "workflow_name", "display_name", "description",
                "trigger_type", "is_active", "output_table",
            ],
            preferred_presentation="table",
        )
