import os

# Set test environment before importing app
os.environ["GOLDMINE_ENV"] = "test"
os.environ["GOLDMINE_SECRET_KEY"] = "test-secret-key"
os.environ["GOLDMINE_DATA_DIR"] = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "structured")
os.environ["GOLDMINE_STORAGE_DIR"] = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "unstructured")

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app

# Reset cached providers between test runs
import app.data_access.factory as daf
import app.object_storage.factory as osf


@pytest.fixture(autouse=True)
def _reset_providers():
    daf._provider = None
    osf._provider = None
    yield


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def authed_client(client):
    """Client that's already logged in."""
    await client.post("/auth/login", json={"username": "analyst1", "password": "analyst123"})
    yield client
