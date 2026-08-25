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
import heapq
import itertools
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
from app.engines.crawler.links import extract_links
from app.engines.crawler.prioritization import (
    CrawlCandidate,
    InformationGainTracker,
    score_candidate,
)
from app.engines.extraction.content import ExtractedContent, extract_content
from app.engines.query_intelligence.objective import ResearchObjective
from app.engines.search.base import SearchHit
from app.engines.search.duckduckgo import DuckDuckGoSearchProvider
from app.engines.search_strategy.strategy import build_queries
from app.models.research import ResearchStatus
from app.repositories import research_repository
from app.services.confidence import basic_relevance_score

logger = logging.getLogger(__name__)

# Never stop early before at least this many pages, even with zero
# information gain — a couple of unlucky early picks shouldn't end a job
# that would have found what it needed three pages later.
_STALL_FLOOR = 3
# Consecutive pages that satisfied no new required attribute before the
# job gives up looking for more (only when the objective has any
# required_attributes at all — see InformationGainTracker.enabled).
_STALL_LIMIT = 2


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

        # --- SEARCH (multi-query — master spec §5: a single literal query
        # is never treated as sufficient) ---
        await _set_status(organization_id, job_id, ResearchStatus.SEARCHING)
        objective = ResearchObjective.model_validate(job.objective or {})
        queries = build_queries(job.query, objective)
        search_provider = DuckDuckGoSearchProvider()
        per_query_hits: list[list[SearchHit]] = await asyncio.gather(
            *[search_provider.search(q, max_results=max_results) for q in queries]
        )
        seen_urls: set[str] = set()
        hits: list[SearchHit] = []
        for query_hits in per_query_hits:
            for hit in query_hits:
                if hit.url not in seen_urls:
                    seen_urls.add(hit.url)
                    hits.append(hit)
        hits = hits[:max_results]
        await _emit(
            organization_id, job_id, "search.completed", {"count": len(hits), "queries": queries}
        )

        if not hits:
            await _set_status(organization_id, job_id, ResearchStatus.COMPLETED)
            await _emit(organization_id, job_id, "research.completed", {"result_count": 0})
            return

        await _emit(organization_id, job_id, "sources.discovered", {"count": len(hits)})

        # --- CRAWL + EXTRACT (goal-driven prioritization — AUDIT_BPO_CRM.md
        # Phase 3: a priority frontier scored by score_candidate(), expanded
        # with same-domain links discovered on each page (extract_links),
        # crawled wave-by-wave up to max_pages, stopping early once
        # InformationGainTracker sees the objective's required_attributes
        # are satisfied or a run of pages stops finding anything new. This
        # replaces Phase 1-3's flat "fetch every search hit in one batch" —
        # see research_orchestrator.py's _MAX_RESULT_LIMIT_OVERRIDE comment,
        # which foreshadowed exactly this change.) ---
        await _set_status(organization_id, job_id, ResearchStatus.CRAWLING)
        fetcher = PageFetcher()
        semaphore = asyncio.Semaphore(settings.crawler_max_concurrency)
        max_pages = int(job.config.get("max_pages", max_results))

        counter = itertools.count()
        frontier: list[tuple[float, int, CrawlCandidate]] = []
        for hit in hits:
            candidate = CrawlCandidate(url=hit.url, anchor_text=hit.title or "", depth=0)
            score = score_candidate(
                url=candidate.url, anchor_text=candidate.anchor_text, objective=objective, depth=0
            )
            heapq.heappush(frontier, (-score, next(counter), candidate))

        gain_tracker = InformationGainTracker(objective.required_attributes)
        visited: set[str] = set()
        result_count = 0
        pages_crawled = 0
        stall_streak = 0
        stop_reason: str | None = None

        # Crawl and extract now happen together per page (each wave fetches,
        # extracts, and stores before the next wave is scored), so there is
        # no longer a distinct "fetching done, now extracting" batch
        # boundary to report — status stays CRAWLING for the whole loop, and
        # moves to EXTRACTING only as a brief final step once it's done,
        # keeping the state machine frontend/ARCHITECTURE.md document
        # honest rather than claiming a phase that isn't real anymore.
        while frontier and pages_crawled < max_pages:
            wave: list[CrawlCandidate] = []
            while (
                frontier
                and len(wave) < settings.crawler_max_concurrency
                and pages_crawled + len(wave) < max_pages
            ):
                _neg_score, _seq, candidate = heapq.heappop(frontier)
                if candidate.url in visited:
                    continue
                visited.add(candidate.url)
                wave.append(candidate)

            if not wave:
                break

            async with _tenant_session(organization_id) as db:
                wave_source_ids: list[uuid.UUID] = []
                for candidate in wave:
                    domain = urlparse(candidate.url).netloc or candidate.url
                    source = await research_repository.add_source(
                        db,
                        organization_id=organization_id,
                        job_id=job_id,
                        url=candidate.url,
                        domain=domain,
                    )
                    wave_source_ids.append(source.id)

            fetch_results = await asyncio.gather(
                *[_fetch_one(fetcher, semaphore, c.url) for c in wave]
            )

            for candidate, source_id, fetch_result in zip(
                wave, wave_source_ids, fetch_results, strict=True
            ):
                pages_crawled += 1

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
                        {"url": candidate.url, "error": fetch_result.error or "Empty response"},
                    )
                    stall_streak += 1
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

                new_gain = gain_tracker.record_page(content.text)
                stall_streak = 0 if new_gain > 0 else stall_streak + 1

                await _emit(
                    organization_id,
                    job_id,
                    "page.completed",
                    {"url": candidate.url, "title": content.title, "duplicate": is_duplicate},
                )

                if pages_crawled < max_pages:
                    new_links = extract_links(fetch_result.html, base_url=fetch_result.url)
                    added = 0
                    for link in new_links:
                        if link.url in visited:
                            continue
                        child = CrawlCandidate(
                            url=link.url, anchor_text=link.anchor_text, depth=candidate.depth + 1
                        )
                        child_score = score_candidate(
                            url=child.url,
                            anchor_text=child.anchor_text,
                            objective=objective,
                            depth=child.depth,
                        )
                        heapq.heappush(frontier, (-child_score, next(counter), child))
                        added += 1
                    if added:
                        await _emit(
                            organization_id,
                            job_id,
                            "crawl.expanded",
                            {"from": candidate.url, "new_candidates": added},
                        )

            if gain_tracker.all_satisfied:
                stop_reason = "objective_satisfied"
                break
            stalled = gain_tracker.enabled and stall_streak >= _STALL_LIMIT
            if stalled and pages_crawled >= _STALL_FLOOR:
                stop_reason = "diminishing_returns"
                break

        if stop_reason:
            await _emit(
                organization_id,
                job_id,
                "crawl.stopped_early",
                {"reason": stop_reason, "pages_crawled": pages_crawled},
            )

        await _set_status(organization_id, job_id, ResearchStatus.EXTRACTING)
        await _set_status(organization_id, job_id, ResearchStatus.COMPLETED)
        await _emit(organization_id, job_id, "research.completed", {"result_count": result_count})

    except Exception as exc:  # top-level job guard: never leave a job stuck mid-status
        logger.exception("research job %s failed", job_id)
        await _set_status(organization_id, job_id, ResearchStatus.FAILED, error=str(exc))
        await _emit(organization_id, job_id, "research.failed", {"error": str(exc)})
