"""PostgreSQL Row-Level Security tests — the one thing tests/conftest.py's
SQLite-backed `db_session` fixture structurally cannot cover, since SQLite
has no RLS at all (see app/core/database.py's dialect check). These need a
real PostgreSQL reachable at TEST_DATABASE_URL (defaults to the same
database docker-compose/local dev uses); if it's not reachable, the whole
module is skipped rather than failing — local `pytest` without Postgres
running still passes, CI provides a postgres service container (see
.github/workflows/ci.yml) so these actually run there.

What's verified here is exactly what was manually verified against a real
local Postgres during development (see docs/phases/PHASE_PLAN.md's Session
2 verification report): inserting into an RLS-protected table with no
tenant context set is rejected (fail closed), inserting with the correct
context succeeds, inserting under the wrong tenant's context is rejected,
and a SELECT only ever returns the current tenant's rows.
"""

import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://bpo:bpo@localhost:5432/bpo_ai_scrap"
)


async def _postgres_reachable() -> bool:
    try:
        engine = create_async_engine(TEST_DATABASE_URL)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        await engine.dispose()
        return True
    except Exception:
        return False


@pytest_asyncio.fixture
async def pg_conn():
    if not await _postgres_reachable():
        pytest.skip(f"No PostgreSQL reachable at {TEST_DATABASE_URL} — set TEST_DATABASE_URL")

    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.connect() as conn:
        # Each test gets its own two fake orgs/job so tests can run in any
        # order without clashing, and everything is rolled back at the end —
        # this test suite never leaves data behind in a real database.
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        job_id = uuid.uuid4()
        user_id = uuid.uuid4()

        org_sql = text(
            "INSERT INTO organizations (id, name, slug, tier) "
            "VALUES (:id, :name, :slug, 'standard')"
        )
        trans = await conn.begin()
        await conn.execute(
            org_sql, {"id": org_a, "name": "RLS Test A", "slug": f"rls-test-a-{org_a}"}
        )
        await conn.execute(
            org_sql, {"id": org_b, "name": "RLS Test B", "slug": f"rls-test-b-{org_b}"}
        )
        await conn.execute(
            text(
                "INSERT INTO users (id, email, hashed_password, full_name) "
                "VALUES (:id, :email, 'x', 'RLS Tester')"
            ),
            {"id": user_id, "email": f"rls-{user_id}@example.com"},
        )
        await conn.execute(
            text(
                "INSERT INTO research_jobs "
                "(id, organization_id, created_by, query, status, mode, config) "
                "VALUES (:id, :org, :user, 'rls test query', 'created', 'quick', '{}')"
            ),
            {"id": job_id, "org": org_a, "user": user_id},
        )
        await trans.commit()

        yield conn, {"org_a": org_a, "org_b": org_b, "job_id": job_id}

        trans2 = await conn.begin()
        await conn.execute(
            text("DELETE FROM organizations WHERE id IN (:a, :b)"), {"a": org_a, "b": org_b}
        )
        await trans2.commit()

    await engine.dispose()


@pytest.mark.asyncio
async def test_insert_without_tenant_context_is_rejected(pg_conn):
    conn, ids = pg_conn
    trans = await conn.begin()
    with pytest.raises(Exception, match="row-level security"):
        await conn.execute(
            text(
                "INSERT INTO research_events (id, organization_id, research_job_id, kind, payload) "
                "VALUES (:id, :org, :job, 'test.no_context', '{}')"
            ),
            {"id": uuid.uuid4(), "org": ids["org_a"], "job": ids["job_id"]},
        )
    await trans.rollback()


@pytest.mark.asyncio
async def test_insert_with_correct_tenant_context_succeeds(pg_conn):
    conn, ids = pg_conn
    trans = await conn.begin()
    await conn.execute(text(f"SET LOCAL app.current_tenant = '{ids['org_a']}'"))
    await conn.execute(
        text(
            "INSERT INTO research_events (id, organization_id, research_job_id, kind, payload) "
            "VALUES (:id, :org, :job, 'test.correct_context', '{}')"
        ),
        {"id": uuid.uuid4(), "org": ids["org_a"], "job": ids["job_id"]},
    )
    await trans.commit()


@pytest.mark.asyncio
async def test_insert_under_wrong_tenant_context_is_rejected(pg_conn):
    conn, ids = pg_conn
    trans = await conn.begin()
    # context says org B, but the row claims to belong to org A
    await conn.execute(text(f"SET LOCAL app.current_tenant = '{ids['org_b']}'"))
    with pytest.raises(Exception, match="row-level security"):
        await conn.execute(
            text(
                "INSERT INTO research_events (id, organization_id, research_job_id, kind, payload) "
                "VALUES (:id, :org, :job, 'test.wrong_context', '{}')"
            ),
            {"id": uuid.uuid4(), "org": ids["org_a"], "job": ids["job_id"]},
        )
    await trans.rollback()


@pytest.mark.asyncio
async def test_select_only_returns_current_tenants_rows(pg_conn):
    conn, ids = pg_conn

    # Seed one event for org A under the correct context.
    trans = await conn.begin()
    await conn.execute(text(f"SET LOCAL app.current_tenant = '{ids['org_a']}'"))
    await conn.execute(
        text(
            "INSERT INTO research_events (id, organization_id, research_job_id, kind, payload) "
            "VALUES (:id, :org, :job, 'test.visibility', '{}')"
        ),
        {"id": uuid.uuid4(), "org": ids["org_a"], "job": ids["job_id"]},
    )
    await trans.commit()

    # Org A's own context sees it.
    trans = await conn.begin()
    await conn.execute(text(f"SET LOCAL app.current_tenant = '{ids['org_a']}'"))
    result = await conn.execute(
        text("SELECT count(*) FROM research_events WHERE kind = 'test.visibility'")
    )
    assert result.scalar() == 1
    await trans.commit()

    # Org B's context does not see org A's row.
    trans = await conn.begin()
    await conn.execute(text(f"SET LOCAL app.current_tenant = '{ids['org_b']}'"))
    result = await conn.execute(
        text("SELECT count(*) FROM research_events WHERE kind = 'test.visibility'")
    )
    assert result.scalar() == 0
    await trans.commit()

    # No tenant context at all sees nothing either (fail closed, not open).
    trans = await conn.begin()
    result = await conn.execute(
        text("SELECT count(*) FROM research_events WHERE kind = 'test.visibility'")
    )
    assert result.scalar() == 0
    await trans.commit()


@pytest.mark.asyncio
async def test_research_jobs_itself_has_no_rls(pg_conn):
    """Documents the deliberate scope boundary (see app/workers/tasks/
    research.py's module docstring and AUDIT_BPO_CRM.md §5): research_jobs
    is reachable without a tenant context because the worker's first read of
    a job by id has no tenant to authenticate with yet. Tenant isolation on
    this table is still enforced at the application layer (see
    tests/test_research.py::test_organizations_cannot_see_each_others_research)."""
    conn, ids = pg_conn
    trans = await conn.begin()
    result = await conn.execute(
        text("SELECT count(*) FROM research_jobs WHERE id = :job"), {"job": ids["job_id"]}
    )
    assert result.scalar() == 1
    await trans.commit()
