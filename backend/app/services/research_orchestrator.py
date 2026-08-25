import uuid
from typing import Any

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.research import ResearchJob, ResearchMode, ResearchStatus
from app.repositories import research_repository

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


async def create_and_enqueue(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    created_by: uuid.UUID,
    query: str,
    mode: ResearchMode,
    config_overrides: dict[str, Any],
) -> ResearchJob:
    config = resolve_config(mode, config_overrides)
    job = await research_repository.create_research_job(
        db,
        organization_id=organization_id,
        created_by=created_by,
        query=query,
        mode=mode,
        config=config,
    )
    await enqueue_job(job.id)
    await research_repository.set_status(db, job_id=job.id, status=ResearchStatus.QUEUED)
    job.status = ResearchStatus.QUEUED
    return job
