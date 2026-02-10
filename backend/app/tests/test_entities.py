import pytest


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
    resp = await authed_client.get("/api/entities/resolve", params={"q": "PER-001"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["resolved"] is True
    assert data["entity_type"] == "person"
    assert data["entity_id"] == "PER-001"


@pytest.mark.asyncio
async def test_resolve_person_id_case_insensitive(authed_client):
    resp = await authed_client.get("/api/entities/resolve", params={"q": "per-001"})
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
    resp = await authed_client.get("/api/entities/resolve", params={"q": "Apple"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["resolved"] is True
    assert data["entity_type"] == "stock"
    assert data["entity_id"] == "AAPL"


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
    assert len(data["header_fields"]) > 0
    assert len(data["widgets"]) == 2
    # Check widget configs
    widget_ids = [w["widget_id"] for w in data["widgets"]]
    assert "related_people" in widget_ids
    assert "related_files" in widget_ids


@pytest.mark.asyncio
async def test_person_detail(authed_client):
    resp = await authed_client.get("/api/entities/person/PER-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_type"] == "person"
    assert data["entity_id"] == "PER-001"
    assert len(data["header_fields"]) > 0
    assert len(data["widgets"]) == 1
    assert data["widgets"][0]["widget_id"] == "covered_stocks"


@pytest.mark.asyncio
async def test_dataset_detail(authed_client):
    resp = await authed_client.get("/api/entities/dataset/stocks")
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_type"] == "dataset"
    assert data["entity_id"] == "stocks"
    assert data["display_name"] == "Stock Universe"
    assert len(data["widgets"]) == 1
    assert data["widgets"][0]["widget_id"] == "dataset_contents"
    # Columns should be derived from CSV headers
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
    # AAPL should have at least one person (PER-038 has AAPL)
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
    # AAPL has FILE-401 (audio)
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
    # PER-001 has tickers CRM;IBM;VZ
    resp = await authed_client.get("/api/entities/person/PER-001/stocks")
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert data["total_records"] >= 1
    tickers_returned = [s["ticker"] for s in data["data"]]
    assert "CRM" in tickers_returned or "IBM" in tickers_returned


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
