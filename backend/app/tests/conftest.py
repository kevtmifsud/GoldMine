import os
import tempfile

# Set test environment before importing app
os.environ["GOLDMINE_ENV"] = "test"
os.environ["GOLDMINE_SECRET_KEY"] = "test-secret-key"
os.environ["GOLDMINE_DATA_DIR"] = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "structured")
os.environ["GOLDMINE_STORAGE_DIR"] = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "unstructured")

# Create a temp directory for views data during tests
_views_tmpdir = tempfile.mkdtemp(prefix="goldmine_views_test_")
os.environ["GOLDMINE_VIEWS_DIR"] = _views_tmpdir

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app

# Reset cached providers between test runs
import app.data_access.factory as daf
import app.object_storage.factory as osf
import app.views.factory as vf


@pytest.fixture(autouse=True)
def _reset_providers():
    daf._provider = None
    osf._provider = None
    vf._provider = None
    # Clean views files between tests
    import glob
    for f in glob.glob(os.path.join(_views_tmpdir, "*.json")):
        os.remove(f)
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
    """Client that's already logged in as analyst1."""
    await client.post("/auth/login", json={"username": "analyst1", "password": "analyst123"})
    yield client


@pytest.fixture
async def client_2(app):
    """A second independent client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def authed_client_2(client_2):
    """Client that's already logged in as analyst2."""
    await client_2.post("/auth/login", json={"username": "analyst2", "password": "analyst456"})
    yield client_2
