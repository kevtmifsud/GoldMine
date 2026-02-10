import pytest


@pytest.mark.asyncio
async def test_list_datasets(authed_client):
    response = await authed_client.get("/api/data/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 10
    names = [d["name"] for d in data]
    assert "stocks" in names
    assert "people" in names


@pytest.mark.asyncio
async def test_query_stocks(authed_client):
    response = await authed_client.get("/api/data/stocks?page=1&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["page_size"] == 10
    assert len(data["data"]) == 10
    assert data["total_records"] > 0
    assert data["has_next"] is True


@pytest.mark.asyncio
async def test_query_stocks_page_size_enforced(authed_client):
    response = await authed_client.get("/api/data/stocks?page_size=9999")
    # page_size > 200 should be rejected by validation
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_query_stocks_max_page_size(authed_client):
    response = await authed_client.get("/api/data/stocks?page_size=200")
    assert response.status_code == 200
    data = response.json()
    assert data["page_size"] == 200


@pytest.mark.asyncio
async def test_query_stocks_search(authed_client):
    response = await authed_client.get("/api/data/stocks?search=Apple")
    assert response.status_code == 200
    data = response.json()
    assert data["total_records"] >= 1
    assert any("Apple" in r.get("company_name", "") for r in data["data"])


@pytest.mark.asyncio
async def test_query_stocks_sort(authed_client):
    response = await authed_client.get("/api/data/stocks?sort_by=ticker&sort_order=asc&page_size=5")
    assert response.status_code == 200
    data = response.json()
    tickers = [r["ticker"] for r in data["data"]]
    assert tickers == sorted(tickers)


@pytest.mark.asyncio
async def test_get_single_stock(authed_client):
    response = await authed_client.get("/api/data/stocks/AAPL")
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "AAPL"
    assert data["company_name"] == "Apple Inc."


@pytest.mark.asyncio
async def test_get_nonexistent_record(authed_client):
    response = await authed_client.get("/api/data/stocks/ZZZZ")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_query_nonexistent_dataset(authed_client):
    response = await authed_client.get("/api/data/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_query_people(authed_client):
    response = await authed_client.get("/api/data/people?page_size=5")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 5
    assert data["total_records"] == 40


@pytest.mark.asyncio
async def test_pagination_metadata(authed_client):
    response = await authed_client.get("/api/data/stocks?page=1&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert "total_pages" in data
    assert "has_next" in data
    assert "has_previous" in data
    assert data["has_previous"] is False
    assert data["total_pages"] > 1
