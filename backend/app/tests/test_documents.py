import pytest


@pytest.mark.asyncio
async def test_list_documents_auto_indexes_existing(authed_client):
    response = await authed_client.get("/api/documents/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 14


@pytest.mark.asyncio
async def test_list_documents_filter_by_entity(authed_client):
    response = await authed_client.get("/api/documents/?entity_type=stock&entity_id=AAPL")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    for doc in data:
        entity_ids = [e["entity_id"] for e in doc["entities"]]
        assert "AAPL" in entity_ids


@pytest.mark.asyncio
async def test_search_documents(authed_client):
    # Trigger auto-index first
    await authed_client.get("/api/documents/")
    response = await authed_client.get("/api/documents/search?q=earnings")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    for result in data:
        assert "score" in result
        assert result["score"] > 0


@pytest.mark.asyncio
async def test_search_documents_filter_by_entity(authed_client):
    await authed_client.get("/api/documents/")
    response = await authed_client.get("/api/documents/search?q=earnings&entity_type=stock&entity_id=AAPL")
    assert response.status_code == 200
    data = response.json()
    for result in data:
        entity_ids = [e["entity_id"] for e in result["entities"]]
        assert "AAPL" in entity_ids


@pytest.mark.asyncio
async def test_search_no_results(authed_client):
    await authed_client.get("/api/documents/")
    response = await authed_client.get("/api/documents/search?q=xyzzyspoon123nonsense")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 0


@pytest.mark.asyncio
async def test_upload_document(authed_client):
    content = b"This is a test document about earnings and revenue for testing."
    response = await authed_client.post(
        "/api/documents/upload",
        files={"file": ("test_upload.txt", content, "text/plain")},
        data={
            "entity_type": "stock",
            "entity_id": "AAPL",
            "title": "Test Upload",
            "description": "A test document",
            "date": "2025-01-01",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["filename"] == "test_upload.txt"
    assert data["title"] == "Test Upload"
    assert data["chunk_count"] >= 1

    # Verify it appears in list
    list_resp = await authed_client.get("/api/documents/?entity_type=stock&entity_id=AAPL")
    assert list_resp.status_code == 200
    file_ids = [d["file_id"] for d in list_resp.json()]
    assert data["file_id"] in file_ids


@pytest.mark.asyncio
async def test_upload_empty_file(authed_client):
    response = await authed_client.post(
        "/api/documents/upload",
        files={"file": ("empty.txt", b"", "text/plain")},
        data={
            "entity_type": "stock",
            "entity_id": "AAPL",
            "title": "Empty",
            "description": "",
            "date": "",
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_upload_no_filename(authed_client):
    response = await authed_client.post(
        "/api/documents/upload",
        files={"file": ("", b"some content", "text/plain")},
        data={
            "entity_type": "stock",
            "entity_id": "AAPL",
            "title": "No name",
            "description": "",
            "date": "",
        },
    )
    assert response.status_code in (400, 422)


@pytest.mark.asyncio
async def test_search_keyword_mode(authed_client):
    await authed_client.get("/api/documents/")
    response = await authed_client.get("/api/documents/search?q=earnings&mode=keyword")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    for result in data:
        assert result["score"] > 0


@pytest.mark.asyncio
async def test_search_semantic_mode(authed_client):
    await authed_client.get("/api/documents/")
    response = await authed_client.get("/api/documents/search?q=earnings&mode=semantic")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_search_hybrid_mode(authed_client):
    await authed_client.get("/api/documents/")
    response = await authed_client.get("/api/documents/search?q=earnings&mode=hybrid")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_search_invalid_mode(authed_client):
    await authed_client.get("/api/documents/")
    response = await authed_client.get("/api/documents/search?q=earnings&mode=invalid")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_delete_document(authed_client):
    # Trigger auto-index first so it won't re-index after delete
    await authed_client.get("/api/documents/")

    # Upload a document
    content = b"This is a test document for deletion testing."
    upload_resp = await authed_client.post(
        "/api/documents/upload",
        files={"file": ("delete_test.txt", content, "text/plain")},
        data={
            "entity_type": "stock",
            "entity_id": "AAPL",
            "title": "Delete Test",
            "description": "Will be deleted",
            "date": "2025-01-01",
        },
    )
    assert upload_resp.status_code == 201
    file_id = upload_resp.json()["file_id"]

    # Delete it
    delete_resp = await authed_client.delete(f"/api/documents/{file_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["deleted"] is True

    # Verify it's gone from the list
    list_resp = await authed_client.get("/api/documents/")
    file_ids = [d["file_id"] for d in list_resp.json()]
    assert file_id not in file_ids


@pytest.mark.asyncio
async def test_delete_document_not_found(authed_client):
    response = await authed_client.delete("/api/documents/nonexistent-id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_documents_require_auth(client):
    response = await client.get("/api/documents/")
    assert response.status_code == 401
