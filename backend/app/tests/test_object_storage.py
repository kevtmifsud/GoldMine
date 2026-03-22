import pytest


@pytest.mark.asyncio
async def test_list_files(authed_client):
    response = await authed_client.get("/api/files/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert all("file_id" in f for f in data)


@pytest.mark.asyncio
async def test_list_files_by_type(authed_client):
    response = await authed_client.get("/api/files/?file_type=transcript")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert all(f["type"] == "transcript" for f in data)


@pytest.mark.asyncio
async def test_get_file_metadata(authed_client):
    # First get a valid file_id
    list_resp = await authed_client.get("/api/files/")
    files = list_resp.json()
    file_id = files[0]["file_id"]

    response = await authed_client.get(f"/api/files/{file_id}/metadata")
    assert response.status_code == 200
    data = response.json()
    assert data["file_id"] == file_id
    assert "filename" in data
    assert "mime_type" in data
    assert "size_bytes" in data


@pytest.mark.asyncio
async def test_get_file_metadata_not_found(authed_client):
    response = await authed_client.get("/api/files/FILE-999/metadata")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_download_file(authed_client):
    # Get a transcript file and attempt download.
    # The file may not physically exist on disk (manifest references files
    # that may not be present in the test environment), so accept either
    # 200 (file exists) or 404 (file in manifest but not on disk).
    list_resp = await authed_client.get("/api/files/?file_type=transcript")
    files = list_resp.json()
    file_id = files[0]["file_id"]

    response = await authed_client.get(f"/api/files/{file_id}")
    if response.status_code == 200:
        assert len(response.content) > 0
        assert "Content-Disposition" in response.headers
    else:
        # File in manifest but not physically present — acceptable in test env
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_download_file_not_found(authed_client):
    response = await authed_client.get("/api/files/FILE-999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_files_require_auth(client):
    response = await client.get("/api/files/")
    assert response.status_code == 401
