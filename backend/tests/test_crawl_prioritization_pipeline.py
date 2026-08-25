"""End-to-end worker tests for Phase 3's goal-driven crawl prioritization —
link-following and early stopping — with network calls stubbed the same
way as test_research_pipeline.py. Everything else (DB writes, event log,
frontier scoring, InformationGainTracker) is real."""

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.engines.crawler.fetcher import FetchResult
from app.engines.query_intelligence.parser import parse_query
from app.engines.search.base import SearchHit
from app.models.organization import Organization, OrganizationMember, Role
from app.models.research import (
    CrawlPage,
    ResearchEvent,
    ResearchJob,
    ResearchMode,
    ResearchResult,
    ResearchStatus,
    Source,
)
from app.models.user import User
from app.repositories import research_repository
from app.workers.tasks import research as research_task_module


def _long_paragraphs(sentence: str, count: int = 12) -> str:
    # trafilatura needs a real amount of content to extract non-null text —
    # mirrors test_research_pipeline.py's padding approach.
    return "".join(
        f"<p>{sentence} Filler sentence number {i} about the company.</p>" for i in range(count)
    )


async def _make_org_and_job(db_session, *, query: str, config: dict) -> object:
    async with db_session() as db:
        org = Organization(name="Crawl Test Org", slug=f"crawl-test-{query[:10]}-{id(config)}")
        user = User(
            email=f"crawl-{id(config)}@example.com", hashed_password="x", full_name="Tester"
        )
        db.add_all([org, user])
        await db.flush()
        db.add(OrganizationMember(organization_id=org.id, user_id=user.id, role=Role.ADMIN))
        job = ResearchJob(
            organization_id=org.id,
            created_by=user.id,
            query=query,
            mode=ResearchMode.CUSTOM,
            config=config,
            objective=parse_query(query).model_dump(),
            status=ResearchStatus.CREATED,
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        return job.id


def _install_stub_emit(monkeypatch, db_session):
    async def fake_emit(organization_id, job_id, kind, payload):
        async with db_session() as db:
            await research_repository.add_event(
                db, organization_id=organization_id, job_id=job_id, kind=kind, payload=payload
            )

    monkeypatch.setattr(research_task_module, "_emit", fake_emit)


@pytest.mark.asyncio
async def test_pipeline_follows_same_domain_link_to_find_required_attribute(
    db_session, monkeypatch
):
    """The homepage doesn't mention the CEO, but links to /about, which
    does — the crawler should follow that link and crawl /about too."""

    async def fake_search(self, query, *, max_results):
        return [SearchHit(url="https://acme.example/", title="Acme Home", snippet="")]

    async def fake_fetch(self, url):
        if url == "https://acme.example/":
            html = (
                "<html><head><title>Acme</title></head><body>"
                f"<article>{_long_paragraphs('Acme builds great products.')}"
                '<a href="/about">About us</a></article></body></html>'
            )
        elif url == "https://acme.example/about":
            body = _long_paragraphs("Our CEO is Jane Doe, leading the company since 2019.")
            html = (
                "<html><head><title>About Acme</title></head><body>"
                f"<article>{body}</article></body></html>"
            )
        else:
            raise AssertionError(f"unexpected fetch: {url}")
        return FetchResult(url=url, http_status=200, html=html, content_hash=url, error=None)

    monkeypatch.setattr(research_task_module.DuckDuckGoSearchProvider, "search", fake_search)
    monkeypatch.setattr(research_task_module.PageFetcher, "fetch", fake_fetch)
    _install_stub_emit(monkeypatch, db_session)

    job_id = await _make_org_and_job(
        db_session,
        query="Find companies and their CEO",
        config={"max_results": 3, "max_pages": 5},
    )

    await research_task_module.run_research_job({}, str(job_id))

    async with db_session() as db:
        refreshed = await db.get(ResearchJob, job_id)
        assert refreshed.status == ResearchStatus.COMPLETED

        pages = (
            await db.scalars(select(CrawlPage).join(Source).where(Source.research_job_id == job_id))
        ).all()
        urls = {p.url for p in pages}
        assert urls == {"https://acme.example/", "https://acme.example/about"}


@pytest.mark.asyncio
async def test_pipeline_stops_early_once_required_attribute_satisfied(db_session, monkeypatch):
    """The homepage itself already answers the objective (mentions the
    CEO) and links to a /team page — that page should never be crawled,
    since the objective was already satisfied by the first page."""

    async def fake_search(self, query, *, max_results):
        return [SearchHit(url="https://acme.example/", title="Acme Home", snippet="")]

    fetched_urls: list[str] = []

    async def fake_fetch(self, url):
        fetched_urls.append(url)
        html = (
            "<html><head><title>Acme</title></head><body><article>"
            f"{_long_paragraphs('Our CEO is Jane Doe, leading the company since 2019.')}"
            '<a href="/team">Meet the team</a></article></body></html>'
        )
        return FetchResult(url=url, http_status=200, html=html, content_hash=url, error=None)

    monkeypatch.setattr(research_task_module.DuckDuckGoSearchProvider, "search", fake_search)
    monkeypatch.setattr(research_task_module.PageFetcher, "fetch", fake_fetch)
    _install_stub_emit(monkeypatch, db_session)

    job_id = await _make_org_and_job(
        db_session,
        query="Find companies and their CEO",
        config={"max_results": 3, "max_pages": 5},
    )

    await research_task_module.run_research_job({}, str(job_id))

    assert fetched_urls == ["https://acme.example/"]  # /team was discovered but never crawled

    async with db_session() as db:
        events = (
            await db.scalars(
                select(ResearchEvent)
                .where(ResearchEvent.research_job_id == job_id)
                .where(ResearchEvent.kind == "crawl.stopped_early")
            )
        ).all()
        assert len(events) == 1
        assert events[0].payload["reason"] == "objective_satisfied"
        assert events[0].payload["pages_crawled"] == 1


@pytest.mark.asyncio
async def test_pipeline_stops_on_diminishing_returns_before_exhausting_budget(
    db_session, monkeypatch
):
    """Six candidate pages, none of which ever mention what the objective
    is looking for — after a run of unproductive pages, the crawl should
    give up rather than burn through the whole max_pages budget. Forcing
    crawler_max_concurrency to 1 makes each page its own wave, so the
    stall counter is checked with page-level granularity."""

    async def fake_search(self, query, *, max_results):
        return [
            SearchHit(url=f"https://acme{i}.example/", title=f"Acme {i}", snippet="")
            for i in range(6)
        ]

    fetched_urls: list[str] = []

    async def fake_fetch(self, url):
        fetched_urls.append(url)
        # Distinct text per page (not just a distinct URL) so Phase 4's
        # near-duplicate detector doesn't collapse these into each other —
        # this test is about the stall/early-stop logic, not dedup.
        sentence = f"This page ({url}) has nothing to do with the objective at all."
        html = (
            "<html><head><title>Nothing relevant</title></head><body><article>"
            f"{_long_paragraphs(sentence)}"
            "</article></body></html>"
        )
        return FetchResult(url=url, http_status=200, html=html, content_hash=url, error=None)

    monkeypatch.setattr(research_task_module.DuckDuckGoSearchProvider, "search", fake_search)
    monkeypatch.setattr(research_task_module.PageFetcher, "fetch", fake_fetch)
    monkeypatch.setattr(
        research_task_module,
        "get_settings",
        lambda: SimpleNamespace(crawler_max_concurrency=1),
    )
    _install_stub_emit(monkeypatch, db_session)

    job_id = await _make_org_and_job(
        db_session,
        query="Find companies and their CEO",
        config={"max_results": 6, "max_pages": 6},
    )

    await research_task_module.run_research_job({}, str(job_id))

    # _STALL_FLOOR=3, _STALL_LIMIT=2: pages 1-3 crawled to reach the floor,
    # stall_streak hits the limit exactly at page 3 -> stop before page 4-6.
    assert len(fetched_urls) == 3

    async with db_session() as db:
        events = (
            await db.scalars(
                select(ResearchEvent)
                .where(ResearchEvent.research_job_id == job_id)
                .where(ResearchEvent.kind == "crawl.stopped_early")
            )
        ).all()
        assert len(events) == 1
        assert events[0].payload["reason"] == "diminishing_returns"

        results = (
            await db.scalars(select(ResearchResult).where(ResearchResult.research_job_id == job_id))
        ).all()
        assert len(results) == 3  # every crawled page yields a result (unique content each time)
