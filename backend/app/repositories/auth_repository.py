import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import set_tenant_context
from app.models.organization import Organization, OrganizationMember, Role
from app.models.tenant import TenantTier
from app.models.user import User
from app.repositories.tenant_repository import create_default_quota

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    slug = _SLUG_RE.sub("-", name.lower()).strip("-")
    return slug or "org"


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    return await db.scalar(select(User).where(User.email == email))


async def create_user_and_organization(
    db: AsyncSession, *, email: str, hashed_password: str, full_name: str, organization_name: str
) -> tuple[User, Organization, Role]:
    """New signups get a fresh organization and become its admin.

    Joining an existing organization by invitation is a Phase 11 feature
    (teams/invites) — out of scope for the Phase 1-3 slice.
    """
    # A brand-new organization has no existing tenant context to authenticate
    # a signup request with — the same bootstrapping situation documented for
    # the worker's first read of a job in app/workers/tasks/research.py.
    # The fix here is different because, unlike a job id, we mint the
    # organization's id ourselves: generating it up front lets us set the
    # tenant context before this session's first RLS-protected insert
    # (tenant_quotas, below), rather than after — there is no window where
    # an RLS-protected row for this org is written without it.
    organization_id = uuid.uuid4()
    set_tenant_context(db, organization_id)
    # The RLS after_begin listener (app/core/database.py) only fires when a
    # transaction *begins* — and by this point one is already open on `db`
    # from the caller's earlier get_user_by_email() check, so it fired
    # without a tenant id. Nothing has been written yet (that check was a
    # plain read), so committing here is a no-op except closing that
    # transaction — the next statement then begins a fresh one, this time
    # with the tenant id already in session.info.
    await db.commit()

    base_slug = slugify(organization_name)
    slug = base_slug
    suffix = 1
    while await db.scalar(select(Organization).where(Organization.slug == slug)):
        suffix += 1
        slug = f"{base_slug}-{suffix}"

    organization = Organization(
        id=organization_id, name=organization_name, slug=slug, tier=TenantTier.STANDARD
    )
    user = User(email=email, hashed_password=hashed_password, full_name=full_name)
    db.add_all([organization, user])
    await db.flush()

    membership = OrganizationMember(
        organization_id=organization.id, user_id=user.id, role=Role.ADMIN
    )
    db.add(membership)
    await create_default_quota(db, organization_id=organization.id, tier=TenantTier.STANDARD)
    await db.commit()
    await db.refresh(user)
    await db.refresh(organization)
    return user, organization, Role.ADMIN


async def get_primary_membership(db: AsyncSession, user_id: uuid.UUID) -> OrganizationMember | None:
    return await db.scalar(
        select(OrganizationMember)
        .where(OrganizationMember.user_id == user_id)
        .order_by(OrganizationMember.created_at)
        .limit(1)
    )
