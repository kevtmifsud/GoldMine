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
# Chart endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stock_peers(authed_client):
    resp = await authed_client.get("/api/entities/stock/AAPL/peers")
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert data["total_records"] >= 1
    # AAPL is Technology — all peers should be Technology
    for row in data["data"]:
        assert row["sector"] == "Technology"


@pytest.mark.asyncio
async def test_stock_peers_not_found(authed_client):
    resp = await authed_client.get("/api/entities/stock/ZZZZ/peers")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_person_coverage_sectors(authed_client):
    person_id = await _get_real_person_id(authed_client)
    if not person_id:
        pytest.skip("No people in database")
    resp = await authed_client.get(f"/api/entities/person/{person_id}/coverage-sectors")
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert data["total_records"] >= 1
    # Each row should have sector and count
    for row in data["data"]:
        assert "sector" in row
        assert "count" in row


@pytest.mark.asyncio
async def test_person_coverage_sectors_not_found(authed_client):
    resp = await authed_client.get("/api/entities/person/PER-999/coverage-sectors")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_dataset_distribution(authed_client):
    resp = await authed_client.get(
        "/api/entities/dataset/stocks/distribution",
        params={"group_by": "sector"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert data["total_records"] >= 1
    for row in data["data"]:
        assert "sector" in row
        assert "count" in row


@pytest.mark.asyncio
async def test_dataset_distribution_not_found(authed_client):
    resp = await authed_client.get(
        "/api/entities/dataset/nonexistent/distribution",
        params={"group_by": "sector"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Server-side filter tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_data_filter_by_sector(authed_client):
    resp = await authed_client.get("/api/data/stocks", params={"sector": "Technology"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_records"] >= 1
    for row in data["data"]:
        assert row["sector"] == "Technology"


@pytest.mark.asyncio
async def test_stock_people_filter_by_type(authed_client):
    resp = await authed_client.get(
        "/api/entities/stock/AAPL/people",
        params={"type": "analyst"},
    )
    assert resp.status_code == 200
    data = resp.json()
    for row in data["data"]:
        assert row["type"] == "analyst"


@pytest.mark.asyncio
async def test_stock_people_filter_empty_result(authed_client):
    resp = await authed_client.get(
        "/api/entities/stock/AAPL/people",
        params={"type": "nonexistent_type"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_records"] == 0


# ---------------------------------------------------------------------------
# Widget config tests (chart configs present in detail)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stock_detail_has_chart_widget(authed_client):
    resp = await authed_client.get("/api/entities/stock/AAPL")
    assert resp.status_code == 200
    data = resp.json()
    widget_types = [w["widget_type"] for w in data["widgets"]]
    assert "chart" in widget_types
    chart_widget = next(w for w in data["widgets"] if w["widget_type"] == "chart")
    assert chart_widget["chart_config"] is not None
    # Accept any valid chart type — the first chart may be line or bar
    assert chart_widget["chart_config"]["chart_type"] in ("line", "bar")


@pytest.mark.asyncio
async def test_person_detail_has_chart_widget(authed_client):
    person_id = await _get_real_person_id(authed_client)
    if not person_id:
        pytest.skip("No people in database")
    resp = await authed_client.get(f"/api/entities/person/{person_id}")
    assert resp.status_code == 200
    data = resp.json()
    widget_types = [w["widget_type"] for w in data["widgets"]]
    assert "chart" in widget_types


@pytest.mark.asyncio
async def test_stock_detail_has_filterable_columns(authed_client):
    """Verify the related_people widget has client-filterable columns."""
    resp = await authed_client.get("/api/entities/stock/AAPL")
    assert resp.status_code == 200
    data = resp.json()
    people_widget = next(w for w in data["widgets"] if w["widget_id"] == "related_people")
    # client_filterable_columns should be present and non-empty
    assert len(people_widget["client_filterable_columns"]) > 0


@pytest.mark.asyncio
async def test_dataset_stocks_has_contents_widget(authed_client):
    """Verify the stocks dataset has a contents widget."""
    resp = await authed_client.get("/api/entities/dataset/stocks")
    assert resp.status_code == 200
    data = resp.json()
    widget_ids = [w["widget_id"] for w in data["widgets"]]
    assert "dataset_contents_stocks" in widget_ids
