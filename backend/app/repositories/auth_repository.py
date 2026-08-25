import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization, OrganizationMember, Role
from app.models.user import User

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
    base_slug = slugify(organization_name)
    slug = base_slug
    suffix = 1
    while await db.scalar(select(Organization).where(Organization.slug == slug)):
        suffix += 1
        slug = f"{base_slug}-{suffix}"

    organization = Organization(name=organization_name, slug=slug)
    user = User(email=email, hashed_password=hashed_password, full_name=full_name)
    db.add_all([organization, user])
    await db.flush()

    membership = OrganizationMember(
        organization_id=organization.id, user_id=user.id, role=Role.ADMIN
    )
    db.add(membership)
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
