"""MCP type definitions for tools, parameters, and results."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MCPToolParameter:
    name: str
    type: str  # "string" | "number" | "boolean" | "array"
    description: str
    required: bool = False
    default: Any = None
    enum: list[str] | None = None
    min_value: float | None = None
    max_value: float | None = None


@dataclass
class MCPTool:
    name: str
    namespace: str
    description: str
    parameters: list[MCPToolParameter]
    preferred_presentation: str = "table"
    # "table" | "chart" | "text"
    chart_config: dict | None = None
    # Only if preferred_presentation="chart"
    # {type, x_column, y_column, series_column}

    def to_anthropic_format(self) -> dict:
        """Convert to Anthropic tool definition format for Claude API."""
        properties: dict[str, Any] = {}
        required: list[str] = []

        for param in self.parameters:
            prop: dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            properties[param.name] = prop
            if param.required:
                required.append(param.name)

        result: dict[str, Any] = {
            "name": f"{self.namespace}__{self.name}",
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }
        return result

    @property
    def full_name(self) -> str:
        return f"{self.namespace}__{self.name}"


@dataclass
class MCPToolResult:
    tool_name: str
    namespace: str
    rows: list[dict]
    row_count: int
    columns: list[str]
    preferred_presentation: str
    chart_config: dict | None = None
    metadata: dict = field(default_factory=dict)
    error: str | None = None
    raw_json: str | None = None  # Original JSON string from legacy tools
    formatted_markdown: str | None = None  # Pre-formatted markdown from deterministic formatter

    def to_legacy_format(self) -> list[dict]:
        """Convert to the format the existing generator expects —
        list of dicts with _table key."""
        return [
            {**row, "_table": self.tool_name}
            for row in self.rows
        ]
