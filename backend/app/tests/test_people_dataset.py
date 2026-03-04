import pytest
import json

@pytest.mark.asyncio
async def test_dataset_detail_people(authed_client):
    resp = await authed_client.get("/api/entities/dataset/people")
    print(f"Status code: {resp.status_code}")
    data = resp.json()
    print(f"Response keys: {data.keys()}")
    print(f"Widgets: {len(data['widgets'])}")
    if data['widgets']:
        print(f"First widget columns: {len(data['widgets'][0]['columns'])}")
    assert resp.status_code == 200
    assert data["entity_type"] == "dataset"
    assert data["entity_id"] == "people"
    assert len(data["widgets"]) > 0
    assert len(data["widgets"][0]["columns"]) > 0
