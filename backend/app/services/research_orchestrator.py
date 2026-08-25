import uuid
from typing import Any

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.engines.query_intelligence.parser import parse_query, parse_result_limit
from app.models.research import ResearchJob, ResearchMode, ResearchStatus
from app.models.tenant import TenantTier
from app.repositories import research_repository, tenant_repository

# Mode presets (master spec §30/§76): the user picks a mode, the platform
# picks the parameters. `config_overrides` from the request layered on top
# lets an "advanced" caller override any of these without changing the mode.
MODE_DEFAULTS: dict[ResearchMode, dict[str, Any]] = {
    ResearchMode.QUICK: {"max_results": 3},
    ResearchMode.BALANCED: {"max_results": 6},
    ResearchMode.DEEP: {"max_results": 12},
    ResearchMode.VERIFIED: {"max_results": 6, "min_sources": 3},
    ResearchMode.INVESTIGATION: {"max_results": 15, "min_sources": 3},
    ResearchMode.CUSTOM: {"max_results": 6},
}

_ARQ_JOB_NAME = "run_research_job"
_redis_pool: ArqRedis | None = None

# A number mentioned in the query text (e.g. "find 500 companies") overrides
# the mode's max_results, but is still bounded — Phase 1-3's crawler fetches
# every discovered URL in one bounded-concurrency batch per job (no
# pagination/streaming yet), so an unbounded override would let a single
# request ask for an unreasonable amount of crawl work. Revisit once
# goal-driven prioritization (Phase 3) makes "more results" a budget
# decision rather than "crawl everything now."
_MAX_RESULT_LIMIT_OVERRIDE = 50


class QuotaExceededError(Exception):
    """Raised when creating this job would exceed
    TenantQuota.max_concurrent_research_jobs (master spec §38 — fair
    resource scheduling: no tenant monopolizes workers). Caught in
    app/api/v1/research.py and turned into an HTTP 429."""

    def __init__(self, *, limit: int, active: int) -> None:
        self.limit = limit
        self.active = active
        super().__init__(f"Concurrent research job limit reached ({active}/{limit})")


def resolve_config(mode: ResearchMode, overrides: dict[str, Any]) -> dict[str, Any]:
    resolved = dict(MODE_DEFAULTS.get(mode, MODE_DEFAULTS[ResearchMode.BALANCED]))
    resolved.update({k: v for k, v in overrides.items() if v is not None})
    return resolved


async def _get_pool() -> ArqRedis:
    global _redis_pool
    if _redis_pool is None:
        settings = get_settings()
        _redis_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _redis_pool


async def enqueue_job(job_id: uuid.UUID) -> None:
    pool = await _get_pool()
    await pool.enqueue_job(_ARQ_JOB_NAME, str(job_id))


async def _max_concurrent_jobs_for(db: AsyncSession, organization_id: uuid.UUID) -> int:
    quota = await tenant_repository.get_quota(db, organization_id=organization_id)
    if quota is not None:
        return quota.max_concurrent_research_jobs
    # Organizations created before this phase have no quota row yet — fall
    # back to the standard tier's default rather than leaving them
    # unlimited, and self-heal by creating the row so this fallback only
    # fires once per pre-existing organization.
    quota = await tenant_repository.create_default_quota(
        db, organization_id=organization_id, tier=TenantTier.STANDARD
    )
    await db.commit()
    return quota.max_concurrent_research_jobs


async def create_and_enqueue(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    created_by: uuid.UUID,
    query: str,
    mode: ResearchMode,
    config_overrides: dict[str, Any],
) -> ResearchJob:
    limit = await _max_concurrent_jobs_for(db, organization_id)
    active = await research_repository.count_active_research_jobs(
        db, organization_id=organization_id
    )
    if active >= limit:
        raise QuotaExceededError(limit=limit, active=active)

    objective = parse_query(query)
    config = resolve_config(mode, config_overrides)
    if (result_limit := parse_result_limit(query)) is not None:
        config["max_results"] = min(result_limit, _MAX_RESULT_LIMIT_OVERRIDE)

    job = await research_repository.create_research_job(
        db,
        organization_id=organization_id,
        created_by=created_by,
        query=query,
        mode=mode,
        config=config,
        objective=objective.model_dump(),
    )
    await enqueue_job(job.id)
    await research_repository.set_status(db, job_id=job.id, status=ResearchStatus.QUEUED)
    job.status = ResearchStatus.QUEUED
    return job
