"""Tests for agentic tool dispatch logic (tools.py + retrieval functions)."""
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
    """Verify GOLDMINE_TOOLS cover all expected data sources."""

    def test_all_tools_present(self):
        names = {t["name"] for t in GOLDMINE_TOOLS}
        expected = {
            "search_documents",
            "get_financial_metrics",
            "get_all_estimates",
            "get_daily_pnl",
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

    def test_alt_data_requires_data_types(self):
        alt_tool = next(t for t in GOLDMINE_TOOLS if t["name"] == "get_alt_data")
        assert "data_types" in alt_tool["input_schema"]["required"]

    def test_estimates_tool_is_combined(self):
        """There should be a single get_all_estimates tool, not four separate ones."""
        estimate_tools = [t for t in GOLDMINE_TOOLS if "estimate" in t["name"].lower()]
        assert len(estimate_tools) == 1
        assert estimate_tools[0]["name"] == "get_all_estimates"

    def test_search_documents_requires_doc_types(self):
        search_tool = next(t for t in GOLDMINE_TOOLS if t["name"] == "search_documents")
        assert "doc_types" in search_tool["input_schema"]["required"]


# ---------------------------------------------------------------------------
# Tool dispatch tests (mocked DB)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestToolDispatch:
    """Test that execute_tool routes to the correct retrieval functions."""

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

    @patch("app.mode2.retrieval._structured_query", new_callable=AsyncMock)
    async def test_get_financial_metrics_calls_structured_query(self, mock_sq):
        mock_sq.return_value = [{"metric_name": "total_revenue", "value": 100}]

        result = await execute_tool(
            "get_financial_metrics",
            {"tickers": ["AAPL"], "topic": "revenue"},
            _make_classified(),
            DUMMY_EMBEDDING,
        )

        mock_sq.assert_called_once()
        data = json.loads(result)
        assert len(data) == 1

    @patch("app.mode2.retrieval._query_estimates", new_callable=AsyncMock)
    async def test_get_all_estimates_calls_query_estimates(self, mock_est):
        mock_est.return_value = [
            {"_table": "internal_estimates", "ticker": "AAPL", "metric": "eps"},
        ]

        result = await execute_tool(
            "get_all_estimates",
            {"tickers": ["AAPL"]},
            _make_classified(query_type="estimates"),
            DUMMY_EMBEDDING,
        )

        mock_est.assert_called_once()
        data = json.loads(result)
        assert len(data) == 1

    @patch("app.mode2.retrieval._query_daily_pnl", new_callable=AsyncMock)
    async def test_get_daily_pnl_calls_query(self, mock_pnl):
        mock_pnl.return_value = [{"_table": "daily_pnl", "ticker": "AAPL"}]

        result = await execute_tool(
            "get_daily_pnl",
            {"tickers": ["AAPL"]},
            _make_classified(query_type="portfolio"),
            DUMMY_EMBEDDING,
        )

        mock_pnl.assert_called_once()
        data = json.loads(result)
        assert data[0]["_table"] == "daily_pnl"

    @patch("app.mode2.retrieval._query_alt_data", new_callable=AsyncMock)
    async def test_get_alt_data_sets_types(self, mock_alt):
        mock_alt.return_value = [{"_table": "alt_data", "data_type": "credit_card"}]

        classified = _make_classified(query_type="alt_data", alt_data_types=["web_traffic"])
        result = await execute_tool(
            "get_alt_data",
            {"tickers": ["SBUX"], "data_types": ["credit_card"]},
            classified,
            DUMMY_EMBEDDING,
        )

        mock_alt.assert_called_once()
        # Verify the classified's alt_data_types was temporarily overridden
        # but restored after the call
        assert classified.alt_data_types == ["web_traffic"]

    async def test_unknown_tool_returns_error(self):
        result = await execute_tool(
            "nonexistent_tool",
            {},
            _make_classified(),
            DUMMY_EMBEDDING,
        )
        data = json.loads(result)
        assert "error" in data

    @patch("app.mode2.retrieval._query_stock_history", new_callable=AsyncMock)
    async def test_get_stock_history_calls_query(self, mock_sh):
        mock_sh.return_value = [{"_table": "stock_history", "ticker": "AAPL", "close": 150.0}]

        result = await execute_tool(
            "get_stock_history",
            {"tickers": ["AAPL"]},
            _make_classified(),
            DUMMY_EMBEDDING,
        )

        mock_sh.assert_called_once()
        data = json.loads(result)
        assert data[0]["_table"] == "stock_history"

    @patch("app.mode2.retrieval._query_guidance", new_callable=AsyncMock)
    async def test_get_guidance_overrides_periods(self, mock_g):
        mock_g.return_value = [{"_table": "guidance", "ticker": "AAPL"}]

        classified = _make_classified(fiscal_periods=["Q3_2024"])
        result = await execute_tool(
            "get_guidance",
            {"tickers": ["AAPL"], "fiscal_periods": ["Q4_2024"]},
            classified,
            DUMMY_EMBEDDING,
        )

        mock_g.assert_called_once()
        # Verify fiscal_periods was restored
        assert classified.fiscal_periods == ["Q3_2024"]

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
        # Verify workflow_name was restored
        assert classified.workflow_name is None
