"""Central MCP registry — single entry point for tool listing, routing, and dispatch."""
from __future__ import annotations

import structlog

from .base import MCPServer
from .types import MCPTool, MCPToolResult

logger = structlog.get_logger(__name__)


class MCPRegistry:
    """Central registry of all MCP servers.

    This is the single entry point for:
    - Listing available tools
    - Routing tool calls to the right server
    - Converting between MCP and legacy formats
    """

    def __init__(self) -> None:
        self._servers: dict[str, MCPServer] = {}

    def register(self, server: MCPServer) -> None:
        """Register an MCP server."""
        self._servers[server.namespace] = server
        logger.info(
            "mcp_server_registered",
            namespace=server.namespace,
            tool_count=len(server.list_tools()),
        )

    def list_namespaces(self) -> list[dict]:
        """List all registered namespaces."""
        return [
            {
                "namespace": s.namespace,
                "display_name": s.display_name,
                "description": s.description,
                "tool_count": len(s.list_tools()),
            }
            for s in self._servers.values()
        ]

    def list_tools(
        self,
        namespace: str | None = None,
    ) -> list[MCPTool]:
        """List tools, optionally filtered by namespace."""
        if namespace:
            server = self._servers.get(namespace)
            if not server:
                return []
            return server.list_tools()

        all_tools: list[MCPTool] = []
        for server in self._servers.values():
            all_tools.extend(server.list_tools())
        return all_tools

    def list_tools_anthropic_format(
        self,
        namespace: str | None = None,
    ) -> list[dict]:
        """Return tools in Anthropic API format for passing to Claude."""
        return [
            tool.to_anthropic_format()
            for tool in self.list_tools(namespace)
        ]

    def find_server(self, full_tool_name: str) -> tuple[MCPServer | None, str]:
        """Find the server that owns a tool and return (server, tool_name).

        Supports two formats:
        - Namespaced: "namespace__tool_name" → look up by namespace
        - Legacy (no __): search all servers for a matching tool name
        """
        if "__" in full_tool_name:
            namespace, tool_name = full_tool_name.split("__", 1)
            return self._servers.get(namespace), tool_name

        # Find the first server that has this tool
        for server in self._servers.values():
            if server.get_tool(full_tool_name):
                return server, full_tool_name
        return None, full_tool_name

    async def call_tool(
        self,
        full_tool_name: str,
        params: dict,
        **kwargs: object,
    ) -> MCPToolResult:
        """Route a tool call to the right server."""
        server, tool_name = self.find_server(full_tool_name)
        if not server:
            return MCPToolResult(
                tool_name=full_tool_name,
                namespace="unknown",
                rows=[],
                row_count=0,
                columns=[],
                preferred_presentation="table",
                error=f"No server found for tool: {full_tool_name}",
            )

        try:
            result = await server.call_tool(tool_name, params, **kwargs)

            # Apply deterministic formatter for table tools
            if result.rows and not result.error:
                from .formatters import format_tool_result
                formatted = format_tool_result(tool_name, result.rows, params)
                if formatted:
                    result.formatted_markdown = formatted

            logger.info(
                "mcp_tool_called",
                tool=full_tool_name,
                row_count=result.row_count,
            )
            return result
        except Exception as e:
            logger.error(
                "mcp_tool_error",
                tool=full_tool_name,
                error=str(e),
            )
            return MCPToolResult(
                tool_name=full_tool_name,
                namespace=server.namespace,
                rows=[],
                row_count=0,
                columns=[],
                preferred_presentation="table",
                error=str(e),
            )


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------
_registry: MCPRegistry | None = None


def get_registry() -> MCPRegistry:
    global _registry
    if _registry is None:
        _registry = MCPRegistry()
        _setup_registry(_registry)
    return _registry


def _setup_registry(registry: MCPRegistry) -> None:
    """Register all MCP servers.

    This is where you add new servers as they are built.
    """
    from .servers.altdata import AltDataServer
    from .servers.estimates import EstimatesServer
    from .servers.portfolio import PortfolioServer
    from .servers.financials import FinancialsServer
    from .servers.workflows import WorkflowsServer
    from .servers.search import SearchServer

    registry.register(AltDataServer())
    registry.register(EstimatesServer())
    registry.register(PortfolioServer())
    registry.register(FinancialsServer())
    registry.register(WorkflowsServer())
    registry.register(SearchServer())
