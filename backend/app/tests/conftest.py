import os
import tempfile

# Set test environment before importing app
os.environ["GOLDMINE_ENV"] = "test"
os.environ["GOLDMINE_SECRET_KEY"] = "test-secret-key"
os.environ["GOLDMINE_DATA_DIR"] = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "structured")
os.environ["GOLDMINE_STORAGE_DIR"] = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "unstructured")

# Create temp directories for views and documents data during tests
_views_tmpdir = tempfile.mkdtemp(prefix="goldmine_views_test_")
os.environ["GOLDMINE_VIEWS_DIR"] = _views_tmpdir

_docs_tmpdir = tempfile.mkdtemp(prefix="goldmine_docs_test_")
os.environ["GOLDMINE_DOCUMENTS_DIR"] = _docs_tmpdir

_schedules_tmpdir = tempfile.mkdtemp(prefix="goldmine_schedules_test_")
os.environ["GOLDMINE_SCHEDULES_DIR"] = _schedules_tmpdir

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app

# Reset cached providers between test runs
import app.data_access.factory as daf
import app.object_storage.factory as osf
import app.views.factory as vf
import app.documents.factory as docf
import app.llm.factory as llmf
import app.email.factory as emf
import app.api.documents as docs_api


@pytest.fixture(autouse=True)
def _reset_providers():
    daf._provider = None
    osf._provider = None
    vf._provider = None
    docf._provider = None
    llmf._provider = None
    emf._email_provider = None
    emf._schedule_provider = None
    docs_api._indexed_existing = False
    # Clean views files between tests
    import glob
    for f in glob.glob(os.path.join(_views_tmpdir, "*.json")):
        os.remove(f)
    # Clean documents index between tests
    for f in glob.glob(os.path.join(_docs_tmpdir, "*.json")):
        os.remove(f)
    # Clean schedules data between tests
    for f in glob.glob(os.path.join(_schedules_tmpdir, "*.json")):
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
