"""The research pipeline job (master spec §102 vertical slice):

    SEARCH -> CRAWL (SSRF-guarded, concurrent) -> EXTRACT -> STORE

Runs inside the arq worker process, never inside a FastAPI request handler
(ARCHITECTURE.md §2 — FastAPI only ever enqueues this). Progress is written
to the DB (research_events, for anyone who reloads the page) and published on
Redis pub/sub (for anyone watching live via the WebSocket).

Every session this job opens after the initial job fetch calls
`set_tenant_context()` with the job's `organization_id` before any query, so
PostgreSQL RLS on research_events/sources/crawl_pages/research_results (see
AUDIT_BPO_CRM.md §5) is enforced for worker writes exactly as it is for API
requests — not a second, weaker code path.
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import database as database_module
from app.core.config import get_settings
from app.core.redis import get_redis_pool, publish_research_event
from app.engines.crawler.fetcher import FetchResult, PageFetcher
from app.engines.extraction.content import ExtractedContent, extract_content
from app.engines.search.duckduckgo import DuckDuckGoSearchProvider
from app.models.research import ResearchStatus
from app.repositories import research_repository
from app.services.confidence import basic_relevance_score

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _tenant_session(organization_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
    async with database_module.async_session_factory() as db:
        database_module.set_tenant_context(db, organization_id)
        yield db


async def _emit(
    organization_id: uuid.UUID, job_id: uuid.UUID, kind: str, payload: dict[str, Any]
) -> None:
    async with _tenant_session(organization_id) as db:
        await research_repository.add_event(
            db, organization_id=organization_id, job_id=job_id, kind=kind, payload=payload
        )
    redis = get_redis_pool()
    await publish_research_event(redis, str(job_id), {"kind": kind, "payload": payload})


async def _set_status(
    organization_id: uuid.UUID,
    job_id: uuid.UUID,
    status: ResearchStatus,
    *,
    error: str | None = None,
) -> None:
    # research_jobs itself is not yet RLS-protected (see AUDIT_BPO_CRM.md §5
    # / this module's docstring for why: the worker's very first read of a
    # job by id would otherwise have no organization_id to authenticate
    # with — a bootstrapping problem, not an oversight) — set_status stays
    # on the plain session, app-layer scoping on research_jobs is unchanged.
    async with database_module.async_session_factory() as db:
        await research_repository.set_status(db, job_id=job_id, status=status, error=error)
    await _emit(organization_id, job_id, "status.changed", {"status": status.value})


async def _fetch_one(fetcher: PageFetcher, semaphore: asyncio.Semaphore, url: str) -> FetchResult:
    async with semaphore:
        return await fetcher.fetch(url)


async def run_research_job(ctx: dict[str, Any], job_id_str: str) -> None:
    job_id = uuid.UUID(job_id_str)
    settings = get_settings()

    async with database_module.async_session_factory() as db:
        job = await research_repository.get_research_job_for_worker(db, job_id=job_id)
    if job is None:
        logger.error("research job %s not found — skipping", job_id)
        return

    organization_id = job.organization_id

    try:
        max_results = int(job.config.get("max_results", 6))

        # --- SEARCH ---
        await _set_status(organization_id, job_id, ResearchStatus.SEARCHING)
        hits = await DuckDuckGoSearchProvider().search(job.query, max_results=max_results)
        await _emit(organization_id, job_id, "search.completed", {"count": len(hits)})

        if not hits:
            await _set_status(organization_id, job_id, ResearchStatus.COMPLETED)
            await _emit(organization_id, job_id, "research.completed", {"result_count": 0})
            return

        # --- register sources ---
        source_ids: list[tuple[uuid.UUID, str]] = []
        async with _tenant_session(organization_id) as db:
            for hit in hits:
                domain = urlparse(hit.url).netloc or hit.url
                source = await research_repository.add_source(
                    db, organization_id=organization_id, job_id=job_id, url=hit.url, domain=domain
                )
                source_ids.append((source.id, hit.url))
        await _emit(organization_id, job_id, "sources.discovered", {"count": len(source_ids)})

        # --- CRAWL (concurrent, SSRF-guarded) ---
        await _set_status(organization_id, job_id, ResearchStatus.CRAWLING)
        fetcher = PageFetcher()
        semaphore = asyncio.Semaphore(settings.crawler_max_concurrency)
        fetch_results = await asyncio.gather(
            *[_fetch_one(fetcher, semaphore, url) for _, url in source_ids]
        )

        # --- EXTRACT + STORE ---
        await _set_status(organization_id, job_id, ResearchStatus.EXTRACTING)
        result_count = 0
        for (source_id, url), fetch_result in zip(source_ids, fetch_results, strict=True):
            if fetch_result.error or fetch_result.html is None:
                async with _tenant_session(organization_id) as db:
                    await research_repository.add_crawl_page(
                        db,
                        organization_id=organization_id,
                        source_id=source_id,
                        url=fetch_result.url,
                        http_status=fetch_result.http_status,
                        content_hash=None,
                        title=None,
                        extracted_text=None,
                        error=fetch_result.error or "Empty response",
                    )
                await _emit(
                    organization_id,
                    job_id,
                    "page.failed",
                    {"url": url, "error": fetch_result.error or "Empty response"},
                )
                continue

            content: ExtractedContent = extract_content(fetch_result.html, url=fetch_result.url)

            async with _tenant_session(organization_id) as db:
                is_duplicate = (
                    fetch_result.content_hash is not None
                    and await research_repository.content_hash_already_used(
                        db, job_id=job_id, content_hash=fetch_result.content_hash
                    )
                )
                page = await research_repository.add_crawl_page(
                    db,
                    organization_id=organization_id,
                    source_id=source_id,
                    url=fetch_result.url,
                    http_status=fetch_result.http_status,
                    content_hash=fetch_result.content_hash,
                    title=content.title,
                    extracted_text=content.text,
                    error=None,
                )
                if not is_duplicate:
                    confidence = basic_relevance_score(
                        http_status=fetch_result.http_status, extracted_text=content.text
                    )
                    snippet = (content.text or "")[:400] or None
                    await research_repository.add_result(
                        db,
                        organization_id=organization_id,
                        job_id=job_id,
                        crawl_page_id=page.id,
                        title=content.title,
                        url=fetch_result.url,
                        snippet=snippet,
                        confidence=confidence,
                    )
                    result_count += 1

            await _emit(
                organization_id,
                job_id,
                "page.completed",
                {"url": url, "title": content.title, "duplicate": is_duplicate},
            )

        await _set_status(organization_id, job_id, ResearchStatus.COMPLETED)
        await _emit(organization_id, job_id, "research.completed", {"result_count": result_count})

    except Exception as exc:  # top-level job guard: never leave a job stuck mid-status
        logger.exception("research job %s failed", job_id)
        await _set_status(organization_id, job_id, ResearchStatus.FAILED, error=str(exc))
        await _emit(organization_id, job_id, "research.failed", {"error": str(exc)})
