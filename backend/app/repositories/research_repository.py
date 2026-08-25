import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.research import (
    CrawlPage,
    ResearchEvent,
    ResearchJob,
    ResearchMode,
    ResearchResult,
    ResearchStatus,
    Source,
)


async def create_research_job(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    created_by: uuid.UUID,
    query: str,
    mode: ResearchMode,
    config: dict[str, Any],
) -> ResearchJob:
    job = ResearchJob(
        organization_id=organization_id,
        created_by=created_by,
        query=query,
        mode=mode,
        config=config,
        status=ResearchStatus.CREATED,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def list_research_jobs(db: AsyncSession, *, organization_id: uuid.UUID) -> list[ResearchJob]:
    result = await db.scalars(
        select(ResearchJob)
        .where(ResearchJob.organization_id == organization_id)
        .order_by(ResearchJob.created_at.desc())
    )
    return list(result.all())


async def get_research_job(
    db: AsyncSession, *, organization_id: uuid.UUID, job_id: uuid.UUID, with_events: bool = False
) -> ResearchJob | None:
    """Caller-facing lookup: always scoped to the caller's organization."""
    stmt = select(ResearchJob).where(
        ResearchJob.id == job_id, ResearchJob.organization_id == organization_id
    )
    if with_events:
        stmt = stmt.options(selectinload(ResearchJob.events))
    return await db.scalar(stmt)


async def list_research_results(
    db: AsyncSession, *, organization_id: uuid.UUID, job_id: uuid.UUID
) -> list[ResearchResult]:
    # organization_id is enforced by joining through research_jobs, never trusted
    # from the caller alone.
    job = await get_research_job(db, organization_id=organization_id, job_id=job_id)
    if job is None:
        return []
    result = await db.scalars(
        select(ResearchResult)
        .where(ResearchResult.research_job_id == job_id)
        .order_by(ResearchResult.confidence.desc())
    )
    return list(result.all())


# --- Worker-side helpers ---
#
# The worker operates by job_id only, with no organization_id in scope. This
# is safe: organization scoping already happened once, in create_research_job
# above, at the moment the job was created from an authenticated, org-scoped
# request. The worker never accepts a job_id from an untrusted caller — arq
# job IDs come only from `research_orchestrator.enqueue_job`, which is only
# ever called right after create_research_job. There is no path from a raw
# client request into these functions.


async def get_research_job_for_worker(db: AsyncSession, *, job_id: uuid.UUID) -> ResearchJob | None:
    return await db.get(ResearchJob, job_id)


async def set_status(
    db: AsyncSession, *, job_id: uuid.UUID, status: ResearchStatus, error: str | None = None
) -> None:
    job = await db.get(ResearchJob, job_id)
    if job is None:
        return
    job.status = status
    if error is not None:
        job.error = error
    await db.commit()


async def add_event(
    db: AsyncSession, *, job_id: uuid.UUID, kind: str, payload: dict[str, Any]
) -> ResearchEvent:
    event = ResearchEvent(research_job_id=job_id, kind=kind, payload=payload)
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def add_source(db: AsyncSession, *, job_id: uuid.UUID, url: str, domain: str) -> Source:
    source = Source(research_job_id=job_id, url=url, domain=domain)
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


async def add_crawl_page(
    db: AsyncSession,
    *,
    source_id: uuid.UUID,
    url: str,
    http_status: int | None,
    content_hash: str | None,
    title: str | None,
    extracted_text: str | None,
    error: str | None = None,
) -> CrawlPage:
    page = CrawlPage(
        source_id=source_id,
        url=url,
        http_status=http_status,
        content_hash=content_hash,
        title=title,
        extracted_text=extracted_text,
        error=error,
    )
    db.add(page)
    await db.commit()
    await db.refresh(page)
    return page


async def content_hash_already_used(
    db: AsyncSession, *, job_id: uuid.UUID, content_hash: str
) -> bool:
    """Cheap dedup check (master spec §26): has any result for this job
    already been built from a page with this exact content hash?"""
    existing = await db.scalar(
        select(CrawlPage.id)
        .join(Source, Source.id == CrawlPage.source_id)
        .join(ResearchResult, ResearchResult.crawl_page_id == CrawlPage.id)
        .where(Source.research_job_id == job_id, CrawlPage.content_hash == content_hash)
        .limit(1)
    )
    return existing is not None


async def add_result(
    db: AsyncSession,
    *,
    job_id: uuid.UUID,
    crawl_page_id: uuid.UUID | None,
    title: str | None,
    url: str,
    snippet: str | None,
    confidence: float,
) -> ResearchResult:
    res = ResearchResult(
        research_job_id=job_id,
        crawl_page_id=crawl_page_id,
        title=title,
        url=url,
        snippet=snippet,
        confidence=confidence,
    )
    db.add(res)
    await db.commit()
    await db.refresh(res)
    return res


async def list_crawl_pages_for_job(db: AsyncSession, *, job_id: uuid.UUID) -> list[CrawlPage]:
    result = await db.scalars(
        select(CrawlPage)
        .join(Source, Source.id == CrawlPage.source_id)
        .where(Source.research_job_id == job_id)
    )
    return list(result.all())
