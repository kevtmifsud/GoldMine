import pytest


@pytest.mark.asyncio
async def test_create_pack(authed_client):
    resp = await authed_client.post("/api/views/packs/", json={
        "name": "My Research Pack",
        "description": "AAPL and PER-001 overview",
        "widgets": [
            {
                "source_entity_type": "stock",
                "source_entity_id": "AAPL",
                "widget_id": "related_people",
            },
            {
                "source_entity_type": "person",
                "source_entity_id": "PER-001",
                "widget_id": "covered_stocks",
            },
        ],
        "is_shared": False,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Research Pack"
    assert data["owner"] == "analyst1"
    assert len(data["widgets"]) == 2
    assert data["pack_id"]


@pytest.mark.asyncio
async def test_list_packs(authed_client):
    await authed_client.post("/api/views/packs/", json={
        "name": "Pack A",
        "widgets": [],
    })
    await authed_client.post("/api/views/packs/", json={
        "name": "Pack B",
        "widgets": [],
    })
    resp = await authed_client.get("/api/views/packs/")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_get_pack(authed_client):
    create_resp = await authed_client.post("/api/views/packs/", json={
        "name": "Test Pack",
        "widgets": [],
    })
    pack_id = create_resp.json()["pack_id"]

    resp = await authed_client.get(f"/api/views/packs/{pack_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Test Pack"


@pytest.mark.asyncio
async def test_update_pack(authed_client):
    create_resp = await authed_client.post("/api/views/packs/", json={
        "name": "Old Pack",
        "widgets": [],
    })
    pack_id = create_resp.json()["pack_id"]

    resp = await authed_client.put(f"/api/views/packs/{pack_id}", json={
        "name": "Updated Pack",
        "description": "New description",
    })
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Pack"
    assert resp.json()["description"] == "New description"


@pytest.mark.asyncio
async def test_delete_pack(authed_client):
    create_resp = await authed_client.post("/api/views/packs/", json={
        "name": "Delete Me",
        "widgets": [],
    })
    pack_id = create_resp.json()["pack_id"]

    resp = await authed_client.delete(f"/api/views/packs/{pack_id}")
    assert resp.status_code == 204

    resp = await authed_client.get(f"/api/views/packs/{pack_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_pack_access_control_private(authed_client, authed_client_2):
    create_resp = await authed_client.post("/api/views/packs/", json={
        "name": "Private Pack",
        "widgets": [],
        "is_shared": False,
    })
    pack_id = create_resp.json()["pack_id"]

    resp = await authed_client_2.get(f"/api/views/packs/{pack_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_pack_access_control_shared(authed_client, authed_client_2):
    create_resp = await authed_client.post("/api/views/packs/", json={
        "name": "Shared Pack",
        "widgets": [],
        "is_shared": True,
    })
    pack_id = create_resp.json()["pack_id"]

    resp = await authed_client_2.get(f"/api/views/packs/{pack_id}")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_cannot_update_others_pack(authed_client, authed_client_2):
    create_resp = await authed_client.post("/api/views/packs/", json={
        "name": "My Pack",
        "widgets": [],
        "is_shared": True,
    })
    pack_id = create_resp.json()["pack_id"]

    resp = await authed_client_2.put(f"/api/views/packs/{pack_id}", json={"name": "Hijacked"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cannot_delete_others_pack(authed_client, authed_client_2):
    create_resp = await authed_client.post("/api/views/packs/", json={
        "name": "My Pack",
        "widgets": [],
        "is_shared": True,
    })
    pack_id = create_resp.json()["pack_id"]

    resp = await authed_client_2.delete(f"/api/views/packs/{pack_id}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_pack_resolution(authed_client):
    create_resp = await authed_client.post("/api/views/packs/", json={
        "name": "Research Pack",
        "widgets": [
            {
                "source_entity_type": "stock",
                "source_entity_id": "AAPL",
                "widget_id": "related_people",
            },
            {
                "source_entity_type": "person",
                "source_entity_id": "PER-001",
                "widget_id": "covered_stocks",
            },
        ],
    })
    pack_id = create_resp.json()["pack_id"]

    resp = await authed_client.get(f"/api/views/packs/{pack_id}/resolved")
    assert resp.status_code == 200
    widgets = resp.json()
    assert len(widgets) == 2
    assert widgets[0]["widget_id"] == "related_people"
    assert widgets[1]["widget_id"] == "covered_stocks"
    # Each should have endpoint, columns, etc.
    assert widgets[0]["endpoint"]
    assert len(widgets[1]["columns"]) > 0


@pytest.mark.asyncio
async def test_pack_resolution_with_title_override(authed_client):
    create_resp = await authed_client.post("/api/views/packs/", json={
        "name": "Custom Titles Pack",
        "widgets": [
            {
                "source_entity_type": "stock",
                "source_entity_id": "AAPL",
                "widget_id": "related_people",
                "title_override": "AAPL Contacts",
            },
        ],
    })
    pack_id = create_resp.json()["pack_id"]

    resp = await authed_client.get(f"/api/views/packs/{pack_id}/resolved")
    assert resp.status_code == 200
    widgets = resp.json()
    assert widgets[0]["title"] == "AAPL Contacts"


@pytest.mark.asyncio
async def test_pack_resolution_invalid_entity_skipped(authed_client):
    create_resp = await authed_client.post("/api/views/packs/", json={
        "name": "Pack with bad ref",
        "widgets": [
            {
                "source_entity_type": "stock",
                "source_entity_id": "NONEXISTENT",
                "widget_id": "related_people",
            },
            {
                "source_entity_type": "stock",
                "source_entity_id": "AAPL",
                "widget_id": "related_people",
            },
        ],
    })
    pack_id = create_resp.json()["pack_id"]

    resp = await authed_client.get(f"/api/views/packs/{pack_id}/resolved")
    assert resp.status_code == 200
    widgets = resp.json()
    # Invalid ref should be skipped, only AAPL widget returned
    assert len(widgets) == 1
    assert widgets[0]["widget_id"] == "related_people"
