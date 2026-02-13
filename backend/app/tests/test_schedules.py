from __future__ import annotations

from datetime import datetime

import pytest


SCHEDULE_BODY = {
    "name": "Daily AAPL Report",
    "entity_type": "stock",
    "entity_id": "AAPL",
    "recipients": ["analyst@example.com"],
    "time_of_day": "09:00",
    "days_of_week": [0, 1, 2, 3, 4],
    "widget_overrides": [],
}


@pytest.mark.asyncio
async def test_create_schedule(authed_client):
    resp = await authed_client.post("/api/schedules/", json=SCHEDULE_BODY)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Daily AAPL Report"
    assert data["entity_type"] == "stock"
    assert data["entity_id"] == "AAPL"
    assert data["owner"] == "analyst1"
    assert data["status"] == "active"
    assert data["next_run_at"] != ""
    assert data["schedule_id"]
    assert data["time_of_day"] == "09:00"
    assert data["days_of_week"] == [0, 1, 2, 3, 4]


@pytest.mark.asyncio
async def test_create_schedule_bursts_immediately(authed_client):
    resp = await authed_client.post("/api/schedules/", json=SCHEDULE_BODY)
    assert resp.status_code == 201
    schedule_id = resp.json()["schedule_id"]

    # Burst send should have created a log
    logs_resp = await authed_client.get(f"/api/schedules/{schedule_id}/logs")
    assert logs_resp.status_code == 200
    logs = logs_resp.json()
    assert len(logs) == 1
    assert logs[0]["status"] == "sent"

    # last_run_at should be set
    schedule_resp = await authed_client.get(f"/api/schedules/{schedule_id}")
    assert schedule_resp.json()["last_run_at"] != ""


@pytest.mark.asyncio
async def test_create_schedule_next_run_respects_days(authed_client):
    body = {**SCHEDULE_BODY, "days_of_week": [0]}  # Monday only
    resp = await authed_client.post("/api/schedules/", json=body)
    assert resp.status_code == 201
    next_run_at = resp.json()["next_run_at"]
    next_run_dt = datetime.fromisoformat(next_run_at)
    assert next_run_dt.weekday() == 0  # Monday


@pytest.mark.asyncio
async def test_list_schedules(authed_client):
    await authed_client.post("/api/schedules/", json=SCHEDULE_BODY)
    await authed_client.post("/api/schedules/", json={**SCHEDULE_BODY, "name": "Second Report"})
    resp = await authed_client.get("/api/schedules/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_list_schedules_filter_by_entity(authed_client):
    await authed_client.post("/api/schedules/", json=SCHEDULE_BODY)
    await authed_client.post("/api/schedules/", json={
        **SCHEDULE_BODY, "name": "MSFT Report", "entity_id": "MSFT",
    })

    resp = await authed_client.get("/api/schedules/", params={"entity_type": "stock", "entity_id": "AAPL"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["entity_id"] == "AAPL"


@pytest.mark.asyncio
async def test_get_schedule(authed_client):
    create_resp = await authed_client.post("/api/schedules/", json=SCHEDULE_BODY)
    schedule_id = create_resp.json()["schedule_id"]

    resp = await authed_client.get(f"/api/schedules/{schedule_id}")
    assert resp.status_code == 200
    assert resp.json()["schedule_id"] == schedule_id


@pytest.mark.asyncio
async def test_update_schedule(authed_client):
    create_resp = await authed_client.post("/api/schedules/", json=SCHEDULE_BODY)
    schedule_id = create_resp.json()["schedule_id"]
    original_next_run = create_resp.json()["next_run_at"]

    resp = await authed_client.put(f"/api/schedules/{schedule_id}", json={"days_of_week": [5, 6]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["days_of_week"] == [5, 6]
    assert data["next_run_at"] != original_next_run


@pytest.mark.asyncio
async def test_delete_schedule(authed_client):
    create_resp = await authed_client.post("/api/schedules/", json=SCHEDULE_BODY)
    schedule_id = create_resp.json()["schedule_id"]

    resp = await authed_client.delete(f"/api/schedules/{schedule_id}")
    assert resp.status_code == 204

    resp = await authed_client.get(f"/api/schedules/{schedule_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_schedule_owner_only_update(authed_client, authed_client_2):
    create_resp = await authed_client.post("/api/schedules/", json=SCHEDULE_BODY)
    schedule_id = create_resp.json()["schedule_id"]

    resp = await authed_client_2.put(f"/api/schedules/{schedule_id}", json={"name": "Hacked"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_schedule_owner_only_delete(authed_client, authed_client_2):
    create_resp = await authed_client.post("/api/schedules/", json=SCHEDULE_BODY)
    schedule_id = create_resp.json()["schedule_id"]

    resp = await authed_client_2.delete(f"/api/schedules/{schedule_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_send_now(authed_client):
    create_resp = await authed_client.post("/api/schedules/", json=SCHEDULE_BODY)
    schedule_id = create_resp.json()["schedule_id"]

    resp = await authed_client.post(f"/api/schedules/{schedule_id}/send-now")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "sent"
    assert data["schedule_id"] == schedule_id

    # Verify log was created (burst log + send-now log = 2)
    logs_resp = await authed_client.get(f"/api/schedules/{schedule_id}/logs")
    assert logs_resp.status_code == 200
    logs = logs_resp.json()
    assert len(logs) == 2
    assert all(l["status"] == "sent" for l in logs)


@pytest.mark.asyncio
async def test_schedules_require_auth(client):
    resp = await client.get("/api/schedules/")
    assert resp.status_code == 401
