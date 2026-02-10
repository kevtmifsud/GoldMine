import pytest


@pytest.mark.asyncio
async def test_health_endpoint(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "goldmine"


@pytest.mark.asyncio
async def test_health_no_auth_required(client):
    """Health endpoint should be accessible without authentication."""
    response = await client.get("/api/health")
    assert response.status_code == 200
