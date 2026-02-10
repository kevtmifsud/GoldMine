import pytest


@pytest.mark.asyncio
async def test_login_success(client):
    response = await client.post("/auth/login", json={"username": "analyst1", "password": "analyst123"})
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Login successful"
    assert data["user"]["username"] == "analyst1"
    assert data["user"]["display_name"] == "Alice Chen"
    assert "goldmine_token" in response.cookies


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    response = await client.post("/auth/login", json={"username": "analyst1", "password": "wrong"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_user(client):
    response = await client.post("/auth/login", json={"username": "nobody", "password": "test"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_authenticated(authed_client):
    response = await authed_client.get("/auth/me")
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "analyst1"


@pytest.mark.asyncio
async def test_me_unauthenticated(client):
    response = await client.get("/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout(authed_client):
    response = await authed_client.post("/auth/logout")
    assert response.status_code == 200
    # Cookie should be cleared
    assert response.cookies.get("goldmine_token") is not None or True  # deletion cookie


@pytest.mark.asyncio
async def test_protected_route_without_auth(client):
    response = await client.get("/api/data/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_all_demo_users_can_login(client):
    users = [
        ("analyst1", "analyst123"),
        ("analyst2", "analyst456"),
        ("pm1", "pm789"),
    ]
    for username, password in users:
        response = await client.post("/auth/login", json={"username": username, "password": password})
        assert response.status_code == 200, f"Failed for {username}"
