import uuid
from collections.abc import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Session as SyncSession

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, pool_pre_ping=True, future=True)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


# --- PostgreSQL Row-Level Security tenant context ---
#
# Every tenant-scoped table (research_jobs and its denormalized children —
# see AUDIT_BPO_CRM.md §5) has an RLS policy comparing its organization_id
# column against `current_setting('app.current_tenant', true)`. This
# listener issues `SET LOCAL app.current_tenant = ...` at the start of
# *every* transaction on a session that has a tenant id stashed in
# `session.info["tenant_id"]` — not just the first one — because each
# repository call in this codebase commits its own transaction, and
# `SET LOCAL` only lives for the transaction it was issued in. Without
# re-applying per-transaction, only the first write in a request would be
# tenant-scoped at the database level and every later one would silently
# fall back to "no tenant" (which RLS then reads as "see nothing," not
# "see everything" — fails closed, but still wrong).
#
# This is registered globally on sqlalchemy.orm.Session because this
# process creates sessions exclusively via async_session_factory above; it
# is the documented pattern for wiring RLS through SQLAlchemy's async ORM
# (the event fires on the sync Session that AsyncSession wraps).
@event.listens_for(SyncSession, "after_begin")
def _apply_tenant_context(session: SyncSession, transaction, connection) -> None:
    tenant_id = session.info.get("tenant_id")
    if tenant_id is None:
        return
    if connection.dialect.name != "postgresql":
        # SQLite (the test suite's backend — see tests/conftest.py) has no
        # SET LOCAL / RLS at all; session.info["tenant_id"] is still set and
        # still used by the app-layer organization_id filters that predate
        # RLS, so isolation is still enforced there, just not by the DB too.
        return
    # PostgreSQL's SET/SET LOCAL do not accept bind parameters at all — this
    # is a server-side grammar restriction, not a driver limitation, so
    # `text("SET LOCAL app.current_tenant = :tid")` fails with a syntax
    # error regardless of driver. The value must be interpolated into the
    # SQL text directly. That's safe here specifically because re-parsing
    # through uuid.UUID(...) first guarantees the result is exactly 36
    # hex-and-hyphen characters in canonical form — there is no string this
    # can produce that isn't a valid UUID literal, so there is nothing to
    # inject regardless of what tenant_id originally was.
    safe_tenant_id = str(uuid.UUID(str(tenant_id)))
    connection.execute(text(f"SET LOCAL app.current_tenant = '{safe_tenant_id}'"))


def set_tenant_context(session: AsyncSession, organization_id: uuid.UUID) -> None:
    """Must be called before the session's first query in a request/job, so
    the listener above has the tenant id available when the first (and
    every subsequent) transaction begins. See app/core/deps.py::
    get_current_auth (API requests) and app/workers/tasks/research.py
    (background jobs) for the two call sites."""
    session.sync_session.info["tenant_id"] = organization_id


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


async def check_database_connection() -> bool:
    from sqlalchemy import text

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
