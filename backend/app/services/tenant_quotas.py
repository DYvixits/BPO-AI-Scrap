"""Default quota values per tenant tier (master spec §37).

These are only the *defaults* applied when an organization is created — the
resulting `TenantQuota` row is then an ordinary editable row (Configuration
Engine pattern, §56), not a hardcoded limit. An admin (Phase 11 admin
console) can raise or lower any individual tenant's quota without touching
this table.
"""

import uuid

from app.models.tenant import TenantQuota, TenantTier

_DEFAULTS: dict[TenantTier, dict[str, int]] = {
    TenantTier.STANDARD: {
        "crawl_concurrency": 4,
        "max_concurrent_research_jobs": 2,
        "ai_budget_cents": 0,
        "storage_mb_limit": 500,
        "worker_priority": 1,
    },
    TenantTier.PRO: {
        "crawl_concurrency": 8,
        "max_concurrent_research_jobs": 5,
        "ai_budget_cents": 5_000,
        "storage_mb_limit": 5_000,
        "worker_priority": 5,
    },
    TenantTier.BUSINESS: {
        "crawl_concurrency": 16,
        "max_concurrent_research_jobs": 15,
        "ai_budget_cents": 25_000,
        "storage_mb_limit": 50_000,
        "worker_priority": 10,
    },
    TenantTier.ENTERPRISE: {
        "crawl_concurrency": 32,
        "max_concurrent_research_jobs": 50,
        "ai_budget_cents": 100_000,
        "storage_mb_limit": 500_000,
        "worker_priority": 20,
    },
}


def default_quotas_for_tier(tier: TenantTier) -> dict[str, int]:
    return dict(_DEFAULTS[tier])


def build_default_quota(organization_id: uuid.UUID, tier: TenantTier) -> TenantQuota:
    return TenantQuota(organization_id=organization_id, **default_quotas_for_tier(tier))
