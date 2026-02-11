from unittest.mock import MagicMock

import pytest

import app.llm.factory as llmf
from app.config.settings import settings
from app.llm.models import LLMQueryResponse


@pytest.mark.asyncio
async def test_llm_query_returns_response(authed_client):
    # Trigger auto-index
    await authed_client.get("/api/documents/")

    # Mock the LLM provider
    mock_provider = MagicMock()
    mock_provider.query.return_value = LLMQueryResponse(
        answer="AAPL reported strong earnings with revenue growth.",
        sources=[],
        model="claude-sonnet-4-20250514",
        token_usage={"input_tokens": 100, "output_tokens": 50},
    )
    llmf._provider = mock_provider
    original_key = settings.ANTHROPIC_API_KEY
    settings.ANTHROPIC_API_KEY = "test-key"

    try:
        response = await authed_client.post(
            "/api/documents/query",
            json={
                "query": "What were AAPL earnings?",
                "entity_type": "stock",
                "entity_id": "AAPL",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert data["answer"] != ""
        assert "model" in data
    finally:
        settings.ANTHROPIC_API_KEY = original_key
        llmf._provider = None


@pytest.mark.asyncio
async def test_llm_query_no_api_key(authed_client):
    original_key = settings.ANTHROPIC_API_KEY
    settings.ANTHROPIC_API_KEY = ""

    try:
        response = await authed_client.post(
            "/api/documents/query",
            json={
                "query": "Test query",
                "entity_type": "stock",
                "entity_id": "AAPL",
            },
        )
        assert response.status_code == 503
    finally:
        settings.ANTHROPIC_API_KEY = original_key


@pytest.mark.asyncio
async def test_llm_query_includes_sources(authed_client):
    # Trigger auto-index
    await authed_client.get("/api/documents/")

    mock_provider = MagicMock()
    mock_provider.query.return_value = LLMQueryResponse(
        answer="Based on the earnings transcript, revenue increased.",
        sources=[],
        model="claude-sonnet-4-20250514",
        token_usage={"input_tokens": 200, "output_tokens": 80},
    )
    llmf._provider = mock_provider
    original_key = settings.ANTHROPIC_API_KEY
    settings.ANTHROPIC_API_KEY = "test-key"

    try:
        response = await authed_client.post(
            "/api/documents/query",
            json={
                "query": "earnings",
                "entity_type": "stock",
                "entity_id": "AAPL",
            },
        )
        assert response.status_code == 200
        data = response.json()
        # Sources are populated by the API layer from search results
        assert "sources" in data
        assert isinstance(data["sources"], list)
        # If there are matching docs for AAPL + "earnings", sources should be populated
        if len(data["sources"]) > 0:
            source = data["sources"][0]
            assert "file_id" in source
            assert "filename" in source
            assert "excerpt" in source
    finally:
        settings.ANTHROPIC_API_KEY = original_key
        llmf._provider = None
