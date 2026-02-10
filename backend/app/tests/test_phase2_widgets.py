import pytest


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
    # PER-001 covers CRM, IBM, VZ
    resp = await authed_client.get("/api/entities/person/PER-001/coverage-sectors")
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
    assert chart_widget["chart_config"]["chart_type"] == "bar"


@pytest.mark.asyncio
async def test_person_detail_has_chart_widget(authed_client):
    resp = await authed_client.get("/api/entities/person/PER-001")
    assert resp.status_code == 200
    data = resp.json()
    widget_types = [w["widget_type"] for w in data["widgets"]]
    assert "chart" in widget_types


@pytest.mark.asyncio
async def test_stock_detail_has_filter_definitions(authed_client):
    resp = await authed_client.get("/api/entities/stock/AAPL")
    assert resp.status_code == 200
    data = resp.json()
    people_widget = next(w for w in data["widgets"] if w["widget_id"] == "related_people")
    assert len(people_widget["filter_definitions"]) > 0
    assert people_widget["filter_definitions"][0]["field"] == "type"
    assert len(people_widget["client_filterable_columns"]) > 0


@pytest.mark.asyncio
async def test_dataset_stocks_has_distribution_chart(authed_client):
    resp = await authed_client.get("/api/entities/dataset/stocks")
    assert resp.status_code == 200
    data = resp.json()
    widget_ids = [w["widget_id"] for w in data["widgets"]]
    assert "sector_distribution" in widget_ids
