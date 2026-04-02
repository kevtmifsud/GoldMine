"""Tests for agentic tool dispatch logic (tools.py + retrieval functions).

After MCP migration, many tools are now served by real MCP servers and no
longer pass through execute_tool(). These tests cover:
1. GOLDMINE_TOOLS definitions (tools still defined in tools.py)
2. execute_tool() dispatch for tools that still route through it
3. MCP registry routing for migrated tools
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure SUPABASE_DATABASE_URL is set before import (db.py reads it at module level)
os.environ.setdefault("SUPABASE_DATABASE_URL", "postgresql://test:test@localhost:5432/test")

from app.mode2.models import ClassifiedQuery, ChunkResult, ResolvedUniverse
from app.mode2.tools import GOLDMINE_TOOLS, execute_tool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_classified(**overrides) -> ClassifiedQuery:
    defaults = dict(
        query_type="single_ticker_qualitative",
        tickers=["AAPL"],
        fiscal_periods=[],
        topic="revenue",
    )
    defaults.update(overrides)
    return ClassifiedQuery(**defaults)


def _fake_chunk(ticker: str = "AAPL", doc_type: str = "earnings_transcript") -> ChunkResult:
    return ChunkResult(
        chunk_id="c1",
        document_id="d1",
        ticker=ticker,
        document_type=doc_type,
        fiscal_period="Q4 2024",
        section_name="CFO Remarks",
        section_type="discussion",
        chunk_text="Sample text",
        word_count=10,
        similarity=0.92,
    )


DUMMY_EMBEDDING = [0.1] * 1536


# ---------------------------------------------------------------------------
# Tool definition tests
# ---------------------------------------------------------------------------

class TestToolDefinitions:
    """Verify GOLDMINE_TOOLS covers all expected data sources.

    Note: Many tools have been migrated to real MCP servers (estimates,
    portfolio, financials, search, altdata, workflows). GOLDMINE_TOOLS
    retains the definitions so the generator can include them in Claude's
    tool list via get_always_loaded_tools() and get_tool_definitions().
    """

    def test_all_tools_present(self):
        names = {t["name"] for t in GOLDMINE_TOOLS}
        # These are all tools defined in tools.py (including those now
        # served by MCP servers — the definitions remain for Claude's tool list)
        expected = {
            "search_tools",
            "search_documents",
            "get_financial_metrics",
            "get_estimates",
            "get_daily_pnl",
            "get_pnl_history",
            "get_portfolio_concentration",
            "get_portfolio_risk",
            "get_trade_requests",
            "get_stock_history",
            "get_guidance",
            "get_alt_data",
            "get_model_outputs",
            "get_workflow_registry",
            "run_workflow",
            "get_workflow_output",
            "model_edit",
        }
        assert names == expected

    def test_all_tools_have_required_fields(self):
        for tool in GOLDMINE_TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            assert tool["input_schema"]["type"] == "object"

    def test_alt_data_has_ticker_required(self):
        alt_tool = next(t for t in GOLDMINE_TOOLS if t["name"] == "get_alt_data")
        assert "ticker" in alt_tool["input_schema"]["required"]

    def test_estimates_tool_exists(self):
        """get_estimates is the unified estimates tool."""
        estimate_tools = [t for t in GOLDMINE_TOOLS if t["name"] == "get_estimates"]
        assert len(estimate_tools) == 1
        assert "tickers" in estimate_tools[0]["input_schema"]["required"]

    def test_search_documents_requires_doc_types(self):
        search_tool = next(t for t in GOLDMINE_TOOLS if t["name"] == "search_documents")
        assert "doc_types" in search_tool["input_schema"]["required"]


# ---------------------------------------------------------------------------
# Tool dispatch tests (mocked DB) — for tools still in execute_tool()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestToolDispatch:
    """Test that execute_tool routes to the correct retrieval functions.

    Only tests tools that still route through execute_tool().
    Migrated tools (estimates, pnl, financials, stock_history, guidance)
    now route through MCP servers directly.
    """

    @patch("app.mode2.retrieval._vector_search", new_callable=AsyncMock)
    async def test_search_documents_calls_vector_search(self, mock_vs):
        mock_vs.return_value = [_fake_chunk()]

        result = await execute_tool(
            "search_documents",
            {"tickers": ["AAPL"], "doc_types": ["earnings_transcript"]},
            _make_classified(),
            DUMMY_EMBEDDING,
        )

        mock_vs.assert_called_once()
        data = json.loads(result)
        assert len(data) == 1
        assert data[0]["ticker"] == "AAPL"

    @patch("app.mode2.retrieval._query_trade_requests", new_callable=AsyncMock)
    async def test_get_trade_requests_calls_query(self, mock_tr):
        mock_tr.return_value = [{"_table": "trade_requests", "ticker": "AAPL"}]

        result = await execute_tool(
            "get_trade_requests",
            {"tickers": ["AAPL"]},
            _make_classified(),
            DUMMY_EMBEDDING,
        )

        mock_tr.assert_called_once()
        data = json.loads(result)
        assert data[0]["_table"] == "trade_requests"

    @patch("app.mode2.retrieval._query_alt_data", new_callable=AsyncMock)
    async def test_get_alt_data_calls_query(self, mock_alt):
        mock_alt.return_value = [{"_table": "alt_data", "data_type": "credit_card"}]

        classified = _make_classified(query_type="alt_data", alt_data_types=["web_traffic"])
        result = await execute_tool(
            "get_alt_data",
            {"tickers": ["SBUX"], "data_types": ["credit_card"]},
            classified,
            DUMMY_EMBEDDING,
        )

        mock_alt.assert_called_once()

    async def test_unknown_tool_returns_error(self):
        result = await execute_tool(
            "nonexistent_tool",
            {},
            _make_classified(),
            DUMMY_EMBEDDING,
        )
        data = json.loads(result)
        assert "error" in data

    @patch("app.mode2.retrieval._query_workflow_registry", new_callable=AsyncMock)
    async def test_get_workflow_registry(self, mock_wr):
        mock_wr.return_value = [{"_table": "workflow_registry", "workflow_name": "earnings_preview"}]

        classified = _make_classified(query_type="workflow", workflow_name=None)
        result = await execute_tool(
            "get_workflow_registry",
            {"workflow_name": "earnings_preview"},
            classified,
            DUMMY_EMBEDDING,
        )

        mock_wr.assert_called_once()


# ---------------------------------------------------------------------------
# MCP registry routing tests
# ---------------------------------------------------------------------------

class TestMCPRouting:
    """Verify tools route to the correct MCP server."""

    def test_estimates_routes_to_estimates_server(self):
        from app.mcp.registry import get_registry
        registry = get_registry()
        server, tool_name = registry.find_server("get_estimates")
        assert server is not None
        assert server.namespace == "estimates"
        assert tool_name == "get_estimates"

    def test_alt_data_routes_to_altdata_server(self):
        from app.mcp.registry import get_registry
        registry = get_registry()
        server, tool_name = registry.find_server("get_alt_data")
        assert server is not None
        assert server.namespace == "altdata"

    def test_daily_pnl_routes_to_portfolio_server(self):
        from app.mcp.registry import get_registry
        registry = get_registry()
        server, tool_name = registry.find_server("get_daily_pnl")
        assert server is not None
        assert server.namespace == "portfolio"

    def test_financial_metrics_routes_to_financials_server(self):
        from app.mcp.registry import get_registry
        registry = get_registry()
        server, tool_name = registry.find_server("get_financial_metrics")
        assert server is not None
        assert server.namespace == "financials"

    def test_search_documents_routes_to_search_server(self):
        from app.mcp.registry import get_registry
        registry = get_registry()
        server, tool_name = registry.find_server("search_documents")
        assert server is not None
        assert server.namespace == "search"

    def test_namespaced_tool_name_routes_correctly(self):
        from app.mcp.registry import get_registry
        registry = get_registry()
        server, tool_name = registry.find_server("estimates__get_estimates")
        assert server is not None
        assert server.namespace == "estimates"
        assert tool_name == "get_estimates"

    def test_total_tool_count(self):
        from app.mcp.registry import get_registry
        registry = get_registry()
        all_tools = registry.list_tools()
        assert len(all_tools) >= 19
