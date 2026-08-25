import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import database as database_module
from app.core.database import Base, get_db
from app.main import app
from app.services import research_orchestrator


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # `run_research_job` (worker code) opens its own sessions via the module-level
    # `async_session_factory`, so tests that exercise the pipeline directly
    # point that at the same in-memory engine as the API's overridden get_db.
    database_module.async_session_factory = session_factory

    async def _get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield session_factory
    finally:
        app.dependency_overrides.pop(get_db, None)
        await engine.dispose()


@pytest.fixture(autouse=True)
def no_real_redis(monkeypatch):
    """Unit/integration tests never require a live Redis or arq worker —
    only backend/tests/test_health.py's dedicated case exercises the real
    connection check, and even that tolerates a "degraded" result."""

    async def _fake_enqueue(job_id):
        return None

    monkeypatch.setattr(research_orchestrator, "enqueue_job", _fake_enqueue)


@pytest_asyncio.fixture
async def client(db_session):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def registered_user(client):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "researcher@example.com",
            "password": "correct horse battery staple",
            "full_name": "Ada Researcher",
            "organization_name": "Acme Research Co",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest_asyncio.fixture
async def auth_headers(registered_user):
    return {"Authorization": f"Bearer {registered_user['access_token']}"}
