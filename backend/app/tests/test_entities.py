from __future__ import annotations

from typing import Optional

import pytest


# ---------------------------------------------------------------------------
# Helper: get a real person_id from the database
# ---------------------------------------------------------------------------
async def _get_real_person_id(authed_client) -> Optional[str]:
    """Fetch the first available executive person_id from the people dataset."""
    resp = await authed_client.get("/api/data/people?page_size=50")
    if resp.status_code == 200:
        data = resp.json()
        for person in data["data"]:
            if person.get("type") == "executive":
                return person["person_id"]
        # Fallback: return first person if no executives
        if data["data"]:
            return data["data"][0]["person_id"]
    return None


# ---------------------------------------------------------------------------
# Resolution tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolve_exact_ticker(authed_client):
    resp = await authed_client.get("/api/entities/resolve", params={"q": "AAPL"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["resolved"] is True
    assert data["entity_type"] == "stock"
    assert data["entity_id"] == "AAPL"
    assert "Apple" in data["display_name"]


@pytest.mark.asyncio
async def test_resolve_ticker_case_insensitive(authed_client):
    resp = await authed_client.get("/api/entities/resolve", params={"q": "aapl"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["resolved"] is True
    assert data["entity_id"] == "AAPL"


@pytest.mark.asyncio
async def test_resolve_person_id(authed_client):
    person_id = await _get_real_person_id(authed_client)
    if not person_id:
        pytest.skip("No people in database")
    resp = await authed_client.get("/api/entities/resolve", params={"q": person_id})
    assert resp.status_code == 200
    data = resp.json()
    assert data["resolved"] is True
    assert data["entity_type"] == "person"
    assert data["entity_id"] == person_id


@pytest.mark.asyncio
async def test_resolve_person_id_case_insensitive(authed_client):
    person_id = await _get_real_person_id(authed_client)
    if not person_id:
        pytest.skip("No people in database")
    resp = await authed_client.get("/api/entities/resolve", params={"q": person_id.lower()})
    assert resp.status_code == 200
    data = resp.json()
    assert data["resolved"] is True
    assert data["entity_type"] == "person"


@pytest.mark.asyncio
async def test_resolve_dataset_name(authed_client):
    resp = await authed_client.get("/api/entities/resolve", params={"q": "stocks"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["resolved"] is True
    assert data["entity_type"] == "dataset"
    assert data["entity_id"] == "stocks"


@pytest.mark.asyncio
async def test_resolve_fuzzy_company_name(authed_client):
    # "Apple" matches AAPL stock and potentially people whose names contain "apple".
    # With the full database, this returns multiple candidates rather than resolving
    # to a single match. Assert it returns 200 with AAPL among the candidates.
    resp = await authed_client.get("/api/entities/resolve", params={"q": "Apple"})
    assert resp.status_code == 200
    data = resp.json()
    if data["resolved"]:
        # Single match — must be AAPL
        assert data["entity_type"] == "stock"
        assert data["entity_id"] == "AAPL"
    else:
        # Multiple candidates — AAPL must be among them
        ids = [c["entity_id"] for c in data["candidates"]]
        assert "AAPL" in ids


@pytest.mark.asyncio
async def test_resolve_ambiguous_query(authed_client):
    # "Mark" matches multiple people
    resp = await authed_client.get("/api/entities/resolve", params={"q": "Mark"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["resolved"] is False
    assert len(data["candidates"]) > 1


@pytest.mark.asyncio
async def test_resolve_no_match(authed_client):
    resp = await authed_client.get("/api/entities/resolve", params={"q": "ZZZZZZ"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["resolved"] is False
    assert data["message"] == "No results"
    assert data["candidates"] == []


# ---------------------------------------------------------------------------
# Entity detail tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stock_detail(authed_client):
    resp = await authed_client.get("/api/entities/stock/AAPL")
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_type"] == "stock"
    assert data["entity_id"] == "AAPL"
    assert "Apple" in data["display_name"]
    assert len(data["header_fields"]) >= 3
    assert len(data["widgets"]) >= 3
    # Check key widgets are present
    widget_ids = [w["widget_id"] for w in data["widgets"]]
    assert "related_people" in widget_ids
    assert "related_files" in widget_ids


@pytest.mark.asyncio
async def test_person_detail(authed_client):
    person_id = await _get_real_person_id(authed_client)
    if not person_id:
        pytest.skip("No people in database")
    resp = await authed_client.get(f"/api/entities/person/{person_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_type"] == "person"
    assert data["entity_id"] == person_id
    assert len(data["header_fields"]) > 0
    assert len(data["widgets"]) >= 1


@pytest.mark.asyncio
async def test_dataset_detail(authed_client):
    resp = await authed_client.get("/api/entities/dataset/stocks")
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_type"] == "dataset"
    assert data["entity_id"] == "stocks"
    assert data["display_name"] == "Stocks"
    assert len(data["widgets"]) >= 1
    # Columns should be derived from data
    assert len(data["widgets"][0]["columns"]) > 0


@pytest.mark.asyncio
async def test_entity_detail_invalid_type(authed_client):
    resp = await authed_client.get("/api/entities/unknown/foo")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_entity_detail_stock_not_found(authed_client):
    resp = await authed_client.get("/api/entities/stock/ZZZZ")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_entity_detail_person_not_found(authed_client):
    resp = await authed_client.get("/api/entities/person/PER-999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_entity_detail_dataset_not_found(authed_client):
    resp = await authed_client.get("/api/entities/dataset/nonexistent")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Widget data tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stock_people_widget(authed_client):
    # AAPL should have at least one person
    resp = await authed_client.get("/api/entities/stock/AAPL/people")
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert data["total_records"] >= 1
    # Each person record should have expected keys
    if data["data"]:
        assert "name" in data["data"][0]
        assert "title" in data["data"][0]


@pytest.mark.asyncio
async def test_stock_files_widget(authed_client):
    resp = await authed_client.get("/api/entities/stock/AAPL/files")
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert data["total_records"] >= 1


@pytest.mark.asyncio
async def test_stock_people_not_found(authed_client):
    resp = await authed_client.get("/api/entities/stock/ZZZZ/people")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_stock_files_not_found(authed_client):
    resp = await authed_client.get("/api/entities/stock/ZZZZ/files")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_person_stocks_widget(authed_client):
    person_id = await _get_real_person_id(authed_client)
    if not person_id:
        pytest.skip("No people in database")
    resp = await authed_client.get(f"/api/entities/person/{person_id}/stocks")
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert data["total_records"] >= 1


@pytest.mark.asyncio
async def test_person_stocks_not_found(authed_client):
    resp = await authed_client.get("/api/entities/person/PER-999/stocks")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_widget_pagination(authed_client):
    # Test pagination params on stock people
    resp = await authed_client.get(
        "/api/entities/stock/NVDA/people",
        params={"page": 1, "page_size": 1},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["page"] == 1
    assert data["page_size"] == 1
    assert len(data["data"]) <= 1
