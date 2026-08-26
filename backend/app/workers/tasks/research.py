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
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import database as database_module
from app.core.config import get_settings
from app.core.redis import get_redis_pool, publish_research_event
from app.engines.commercial_signals.detector import BASE_WEIGHT, decay_strength, detect_signals
from app.engines.crawler.fetcher import FetchResult, PageFetcher
from app.engines.crawler.links import extract_links
from app.engines.crawler.normalize import normalize_url
from app.engines.crawler.prioritization import (
    CrawlCandidate,
    InformationGainTracker,
    score_candidate,
)
from app.engines.entity_resolution.resolver import ResolvablePage, resolve_companies
from app.engines.extraction.content import ExtractedContent, extract_content
from app.engines.extraction.dedup import NearDuplicateDetector
from app.engines.extraction.structured import extract_structured_data
from app.engines.fit_scoring.engine import compute_fit
from app.engines.intent_scoring.engine import SignalInput, compute_intent
from app.engines.opportunity_scoring.engine import compute_momentum, compute_opportunity
from app.engines.query_intelligence.objective import ResearchObjective
from app.engines.search.base import SearchHit
from app.engines.search.duckduckgo import DuckDuckGoSearchProvider
from app.engines.search_strategy.strategy import build_queries
from app.engines.verification.engine import EvidenceInput, compute_confidence
from app.models.research import ResearchStatus
from app.repositories import (
    commercial_signal_repository,
    entity_repository,
    research_repository,
    scoring_repository,
    verification_repository,
)
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

        # URL normalization dedup (AUDIT_BPO_CRM.md Phase 4, layer 1): a
        # tracking-param variant of a URL already queued is the same page,
        # not a new candidate — checked at push time so it never occupies a
        # frontier slot or a crawl-budget page in the first place.
        seen_normalized: set[str] = set()

        counter = itertools.count()
        frontier: list[tuple[float, int, CrawlCandidate]] = []
        for hit in hits:
            normalized = normalize_url(hit.url)
            if normalized in seen_normalized:
                continue
            seen_normalized.add(normalized)
            candidate = CrawlCandidate(url=hit.url, anchor_text=hit.title or "", depth=0)
            score = score_candidate(
                url=candidate.url, anchor_text=candidate.anchor_text, objective=objective, depth=0
            )
            heapq.heappush(frontier, (-score, next(counter), candidate))

        gain_tracker = InformationGainTracker(objective.required_attributes)
        # Layer 3 (after URL normalization and exact content-hash match):
        # near-duplicate text, e.g. a page that differs only by a
        # timestamp or session token embedded in otherwise-identical
        # markup. Scoped to this one job, not a cross-job cache.
        near_dup_detector = NearDuplicateDetector()
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
                # No duplicate check needed here: seen_normalized is checked
                # (and updated) at push time below, so nothing that would
                # collide with an already-queued candidate ever enters the
                # frontier in the first place.
                _neg_score, _seq, candidate = heapq.heappop(frontier)
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
                structured = extract_structured_data(fetch_result.html, url=fetch_result.url)

                async with _tenant_session(organization_id) as db:
                    exact_duplicate = (
                        fetch_result.content_hash is not None
                        and await research_repository.content_hash_already_used(
                            db, job_id=job_id, content_hash=fetch_result.content_hash
                        )
                    )
                    # Only worth the comparison cost when it isn't already
                    # known to be a duplicate by the cheaper exact-hash
                    # check — but still record its shingles either way, so
                    # a *later* page can be compared against this one.
                    near_duplicate = near_dup_detector.check_and_record(content.text)
                    is_duplicate = exact_duplicate or near_duplicate
                    if exact_duplicate:
                        duplicate_reason: str | None = "exact_hash"
                    elif near_duplicate:
                        duplicate_reason = "near_duplicate"
                    else:
                        duplicate_reason = None

                    page = await research_repository.add_crawl_page(
                        db,
                        organization_id=organization_id,
                        source_id=source_id,
                        url=fetch_result.url,
                        http_status=fetch_result.http_status,
                        content_hash=fetch_result.content_hash,
                        title=content.title,
                        extracted_text=content.text,
                        structured_data=structured.as_dict(),
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
                    {
                        "url": candidate.url,
                        "title": content.title,
                        "duplicate": is_duplicate,
                        "duplicate_reason": duplicate_reason,
                    },
                )

                if pages_crawled < max_pages:
                    new_links = extract_links(fetch_result.html, base_url=fetch_result.url)
                    added = 0
                    for link in new_links:
                        normalized_link = normalize_url(link.url)
                        if normalized_link in seen_normalized:
                            continue
                        seen_normalized.add(normalized_link)
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

        # --- ENTITY RESOLUTION (AUDIT_BPO_CRM.md Phase 5) — group crawled
        # pages into resolved companies (e.g. a company's own site plus its
        # Crunchbase profile) instead of leaving every page as an
        # unrelated flat result. Runs once, after crawling ends; pages
        # that failed to fetch have no structured_data/title to resolve a
        # name from, so they're excluded. ---
        async with _tenant_session(organization_id) as db:
            crawled_pages = await research_repository.list_crawl_pages_for_job(db, job_id=job_id)
        resolvable = [
            ResolvablePage(
                url=page.url,
                domain=urlparse(page.url).netloc,
                title=page.title,
                structured_data=page.structured_data,
            )
            for page in crawled_pages
            if page.error is None
        ]
        resolved_companies = resolve_companies(resolvable)
        page_by_url = {page.url: page for page in crawled_pages}
        verification_counts: dict[str, int] = {}
        signal_counts: dict[str, int] = {}
        opportunity_scores: list[float] = []
        for resolved in resolved_companies:
            async with _tenant_session(organization_id) as db:
                company = await entity_repository.add_company(
                    db,
                    organization_id=organization_id,
                    job_id=job_id,
                    canonical_name=resolved.canonical_name,
                    primary_domain=resolved.primary_domain,
                    description=resolved.description,
                    match_confidence=resolved.match_confidence,
                )
                for alias in resolved.aliases:
                    await entity_repository.add_alias(
                        db,
                        organization_id=organization_id,
                        company_id=company.id,
                        alias_type=alias.alias_type,
                        value=alias.value,
                        source_url=alias.source_url,
                    )
                await entity_repository.set_results_company(
                    db, job_id=job_id, urls=resolved.member_urls, company_id=company.id
                )

                # --- VERIFICATION (AUDIT_BPO_CRM.md Phase 6) — a disclosed,
                # multi-source confidence score for this company, computed
                # from the same crawled pages Entity Resolution just
                # grouped. See engines/verification/engine.py's module
                # docstring for exactly what this does and doesn't cover. ---
                evidence_inputs = [
                    EvidenceInput(
                        domain=urlparse(url).netloc,
                        source_url=url,
                        excerpt=(page_by_url[url].extracted_text or "")[:300]
                        or page_by_url[url].title,
                        crawled_at=page_by_url[url].created_at,
                    )
                    for url in resolved.member_urls
                    if url in page_by_url
                ]
                confidence_result = compute_confidence(evidence_inputs, now=datetime.now(UTC))
                confidence_score_row = await verification_repository.add_confidence_score(
                    db,
                    organization_id=organization_id,
                    company_id=company.id,
                    result=confidence_result,
                )
                for evidence_input in evidence_inputs:
                    await verification_repository.add_evidence(
                        db,
                        organization_id=organization_id,
                        company_id=company.id,
                        source_url=evidence_input.source_url,
                        domain=evidence_input.domain,
                        excerpt=evidence_input.excerpt,
                    )
                verification_counts[confidence_result.status.value] = (
                    verification_counts.get(confidence_result.status.value, 0) + 1
                )

                # --- COMMERCIAL SIGNALS (AUDIT_BPO_CRM.md Phase 7) — scan
                # this company's own crawled pages for the same disclosed
                # keyword vocabulary Query Intelligence uses on the
                # user's query (query_intelligence/keywords.py::SIGNALS).
                # See engines/commercial_signals/detector.py's module
                # docstring for the time-decay approach and its limits. ---
                now = datetime.now(UTC)
                company_signals: list[SignalInput] = []
                for url in resolved.member_urls:
                    page = page_by_url.get(url)
                    if page is None:
                        continue
                    for detected in detect_signals(page.extracted_text):
                        decayed = decay_strength(BASE_WEIGHT, crawled_at=page.created_at, now=now)
                        await commercial_signal_repository.add_signal(
                            db,
                            organization_id=organization_id,
                            company_id=company.id,
                            job_id=job_id,
                            signal_type=detected.signal_type,
                            polarity=detected.polarity,
                            matched_keyword=detected.matched_keyword,
                            excerpt=detected.excerpt,
                            source_url=url,
                            base_weight=BASE_WEIGHT,
                            crawled_at=page.created_at,
                            decayed_strength=decayed,
                        )
                        signal_counts[detected.signal_type.value] = (
                            signal_counts.get(detected.signal_type.value, 0) + 1
                        )
                        company_signals.append(
                            SignalInput(
                                signal_type=detected.signal_type.value,
                                polarity=detected.polarity,
                                decayed_strength=decayed,
                            )
                        )

                # --- FIT + INTENT + OPPORTUNITY (AUDIT_BPO_CRM.md Phase 8)
                # — master spec §4's separate-tables scoring architecture:
                # Fit (does this company match the query's criteria),
                # Intent (this company's Commercial Signals, aggregated),
                # and Opportunity (a disclosed, fixed-weight combination
                # of Fit/Intent/Confidence/freshness/momentum — see
                # engines/opportunity_scoring/engine.py's module docstring
                # for why the weights aren't per-tenant-configurable yet). ---
                combined_text = " ".join(
                    page_by_url[url].extracted_text or ""
                    for url in resolved.member_urls
                    if url in page_by_url
                )
                fit_result = compute_fit(objective, combined_text)
                fit_score_row = await scoring_repository.add_fit_score(
                    db,
                    organization_id=organization_id,
                    company_id=company.id,
                    job_id=job_id,
                    result=fit_result,
                )
                intent_result = compute_intent(company_signals)
                intent_score_row = await scoring_repository.add_intent_score(
                    db,
                    organization_id=organization_id,
                    company_id=company.id,
                    job_id=job_id,
                    result=intent_result,
                )
                momentum = compute_momentum(company_signals)
                opportunity_result = compute_opportunity(
                    fit_score=fit_result.score,
                    intent_score=intent_result.score,
                    confidence_score=confidence_result.overall_score,
                    freshness_score=confidence_result.freshness_score,
                    momentum=momentum,
                )
                await scoring_repository.add_opportunity_score(
                    db,
                    organization_id=organization_id,
                    company_id=company.id,
                    job_id=job_id,
                    fit_score_id=fit_score_row.id,
                    intent_score_id=intent_score_row.id,
                    confidence_score_id=confidence_score_row.id,
                    result=opportunity_result,
                )
                opportunity_scores.append(opportunity_result.score)
        if resolved_companies:
            await _emit(
                organization_id, job_id, "entities.resolved", {"count": len(resolved_companies)}
            )
            await _emit(
                organization_id, job_id, "verification.completed", {"counts": verification_counts}
            )
            if signal_counts:
                await _emit(organization_id, job_id, "signals.detected", {"counts": signal_counts})
            await _emit(
                organization_id,
                job_id,
                "scoring.completed",
                {
                    "count": len(opportunity_scores),
                    "average_opportunity_score": round(
                        sum(opportunity_scores) / len(opportunity_scores), 2
                    ),
                    "top_opportunity_score": round(max(opportunity_scores), 2),
                },
            )

        await _set_status(organization_id, job_id, ResearchStatus.EXTRACTING)
        await _set_status(organization_id, job_id, ResearchStatus.COMPLETED)
        await _emit(organization_id, job_id, "research.completed", {"result_count": result_count})

    except Exception as exc:  # top-level job guard: never leave a job stuck mid-status
        logger.exception("research job %s failed", job_id)
        await _set_status(organization_id, job_id, ResearchStatus.FAILED, error=str(exc))
        await _emit(organization_id, job_id, "research.failed", {"error": str(exc)})
