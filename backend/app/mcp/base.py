"""Base class for MCP servers."""
from __future__ import annotations

from abc import ABC, abstractmethod

from .types import MCPTool, MCPToolResult


class MCPServer(ABC):
    """Base class for all MCP servers.

    Each namespace (estimates, portfolio, altdata, financials, market)
    implements one MCPServer subclass.
    """

    namespace: str  # e.g. "estimates"
    display_name: str  # e.g. "Estimates"
    description: str

    @abstractmethod
    def list_tools(self) -> list[MCPTool]:
        """Return all tools this server provides."""
        ...

    @abstractmethod
    async def call_tool(
        self,
        tool_name: str,
        params: dict,
        **kwargs: object,
    ) -> MCPToolResult:
        """Execute a tool and return the result."""
        ...

    def get_tool(self, tool_name: str) -> MCPTool | None:
        """Find a tool by name."""
        return next(
            (t for t in self.list_tools() if t.name == tool_name),
            None,
        )
