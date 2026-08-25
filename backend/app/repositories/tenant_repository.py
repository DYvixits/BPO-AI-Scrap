import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import TenantQuota, TenantTier
from app.services.tenant_quotas import build_default_quota


async def get_quota(db: AsyncSession, *, organization_id: uuid.UUID) -> TenantQuota | None:
    return await db.scalar(
        select(TenantQuota).where(TenantQuota.organization_id == organization_id)
    )


async def create_default_quota(
    db: AsyncSession, *, organization_id: uuid.UUID, tier: TenantTier
) -> TenantQuota:
    quota = build_default_quota(organization_id, tier)
    db.add(quota)
    await db.flush()
    return quota
