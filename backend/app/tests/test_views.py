import pytest


@pytest.mark.asyncio
async def test_create_view(authed_client):
    resp = await authed_client.post("/api/views/", json={
        "name": "My AAPL View",
        "entity_type": "stock",
        "entity_id": "AAPL",
        "widget_overrides": [
            {
                "widget_id": "related_people",
                "server_filters": {"type": "executive"},
                "sort_by": "name",
                "sort_order": "desc",
            }
        ],
        "is_shared": False,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My AAPL View"
    assert data["owner"] == "analyst1"
    assert data["entity_type"] == "stock"
    assert data["entity_id"] == "AAPL"
    assert len(data["widget_overrides"]) == 1
    assert data["view_id"]
    assert data["created_at"]


@pytest.mark.asyncio
async def test_list_views(authed_client):
    await authed_client.post("/api/views/", json={
        "name": "View A",
        "entity_type": "stock",
        "entity_id": "AAPL",
    })
    await authed_client.post("/api/views/", json={
        "name": "View B",
        "entity_type": "stock",
        "entity_id": "MSFT",
    })
    resp = await authed_client.get("/api/views/")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_list_views_filter_by_entity(authed_client):
    await authed_client.post("/api/views/", json={
        "name": "View A",
        "entity_type": "stock",
        "entity_id": "AAPL",
    })
    await authed_client.post("/api/views/", json={
        "name": "View B",
        "entity_type": "person",
        "entity_id": "PER-001",
    })
    resp = await authed_client.get("/api/views/?entity_type=stock")
    assert resp.status_code == 200
    views = resp.json()
    assert len(views) == 1
    assert views[0]["entity_type"] == "stock"

    resp = await authed_client.get("/api/views/?entity_type=stock&entity_id=AAPL")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_get_view(authed_client):
    create_resp = await authed_client.post("/api/views/", json={
        "name": "Test View",
        "entity_type": "stock",
        "entity_id": "AAPL",
    })
    view_id = create_resp.json()["view_id"]

    resp = await authed_client.get(f"/api/views/{view_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Test View"


@pytest.mark.asyncio
async def test_get_view_not_found(authed_client):
    resp = await authed_client.get("/api/views/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_view(authed_client):
    create_resp = await authed_client.post("/api/views/", json={
        "name": "Old Name",
        "entity_type": "stock",
        "entity_id": "AAPL",
    })
    view_id = create_resp.json()["view_id"]

    resp = await authed_client.put(f"/api/views/{view_id}", json={
        "name": "New Name",
        "is_shared": True,
    })
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"
    assert resp.json()["is_shared"] is True


@pytest.mark.asyncio
async def test_delete_view(authed_client):
    create_resp = await authed_client.post("/api/views/", json={
        "name": "Delete Me",
        "entity_type": "stock",
        "entity_id": "AAPL",
    })
    view_id = create_resp.json()["view_id"]

    resp = await authed_client.delete(f"/api/views/{view_id}")
    assert resp.status_code == 204

    resp = await authed_client.get(f"/api/views/{view_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_private_view_hidden_from_other_user(authed_client, authed_client_2):
    create_resp = await authed_client.post("/api/views/", json={
        "name": "Private View",
        "entity_type": "stock",
        "entity_id": "AAPL",
        "is_shared": False,
    })
    view_id = create_resp.json()["view_id"]

    # analyst2 cannot see it
    resp = await authed_client_2.get(f"/api/views/{view_id}")
    assert resp.status_code == 404

    # analyst2 list should not include it
    resp = await authed_client_2.get("/api/views/")
    assert resp.status_code == 200
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_shared_view_visible_to_others(authed_client, authed_client_2):
    create_resp = await authed_client.post("/api/views/", json={
        "name": "Shared View",
        "entity_type": "stock",
        "entity_id": "AAPL",
        "is_shared": True,
    })
    view_id = create_resp.json()["view_id"]

    resp = await authed_client_2.get(f"/api/views/{view_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Shared View"


@pytest.mark.asyncio
async def test_cannot_update_others_view(authed_client, authed_client_2):
    create_resp = await authed_client.post("/api/views/", json={
        "name": "My View",
        "entity_type": "stock",
        "entity_id": "AAPL",
        "is_shared": True,
    })
    view_id = create_resp.json()["view_id"]

    resp = await authed_client_2.put(f"/api/views/{view_id}", json={"name": "Hijacked"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cannot_delete_others_view(authed_client, authed_client_2):
    create_resp = await authed_client.post("/api/views/", json={
        "name": "My View",
        "entity_type": "stock",
        "entity_id": "AAPL",
        "is_shared": True,
    })
    view_id = create_resp.json()["view_id"]

    resp = await authed_client_2.delete(f"/api/views/{view_id}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_entity_detail_with_view_id(authed_client):
    # Create a view with overrides
    create_resp = await authed_client.post("/api/views/", json={
        "name": "Filtered People",
        "entity_type": "stock",
        "entity_id": "AAPL",
        "widget_overrides": [
            {
                "widget_id": "related_people",
                "server_filters": {"type": "executive"},
                "sort_by": "name",
                "sort_order": "desc",
                "visible_columns": ["name", "title"],
                "page_size": 5,
            }
        ],
    })
    view_id = create_resp.json()["view_id"]

    # Fetch entity detail with view
    resp = await authed_client.get(f"/api/entities/stock/AAPL?view_id={view_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["active_view_id"] == view_id
    assert data["active_view_name"] == "Filtered People"

    # Find the related_people widget
    people_widget = None
    for w in data["widgets"]:
        if w["widget_id"] == "related_people":
            people_widget = w
            break
    assert people_widget is not None
    assert people_widget["has_overrides"] is True
    assert people_widget["initial_filters"] == {"type": "executive"}
    assert people_widget["initial_sort_by"] == "name"
    assert people_widget["initial_sort_order"] == "desc"
    assert people_widget["default_page_size"] == 5

    # Check visible columns
    visible_cols = [c for c in people_widget["columns"] if c["visible"]]
    visible_keys = {c["key"] for c in visible_cols}
    assert visible_keys == {"name", "title"}


@pytest.mark.asyncio
async def test_entity_detail_without_view_id(authed_client):
    resp = await authed_client.get("/api/entities/stock/AAPL")
    assert resp.status_code == 200
    data = resp.json()
    assert data["active_view_id"] is None
    assert data["active_view_name"] is None


@pytest.mark.asyncio
async def test_entity_detail_invalid_view_id(authed_client):
    resp = await authed_client.get("/api/entities/stock/AAPL?view_id=nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_entity_detail_mismatched_view(authed_client):
    # Create a view for MSFT
    create_resp = await authed_client.post("/api/views/", json={
        "name": "MSFT View",
        "entity_type": "stock",
        "entity_id": "MSFT",
    })
    view_id = create_resp.json()["view_id"]

    # Try to use it on AAPL
    resp = await authed_client.get(f"/api/entities/stock/AAPL?view_id={view_id}")
    assert resp.status_code == 404
