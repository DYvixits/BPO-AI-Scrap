"""End-to-end worker tests for Phase 4's multi-pass extraction and layered
dedup — URL normalization, near-duplicate content, and structured-data
extraction — with the network layer stubbed the same way as
test_research_pipeline.py."""

import pytest
from sqlalchemy import select

from app.engines.crawler.fetcher import FetchResult
from app.engines.query_intelligence.parser import parse_query
from app.engines.search.base import SearchHit
from app.models.organization import Organization, OrganizationMember, Role
from app.models.research import (
    CrawlPage,
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
    return "".join(
        f"<p>{sentence} Filler sentence number {i} about the company.</p>" for i in range(count)
    )


async def _make_org_and_job(db_session, *, query: str, config: dict) -> object:
    async with db_session() as db:
        org = Organization(name="Dedup Test Org", slug=f"dedup-test-{id(config)}")
        user = User(
            email=f"dedup-{id(config)}@example.com", hashed_password="x", full_name="Tester"
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
async def test_pipeline_never_crawls_a_tracking_param_variant_of_a_seed_url(
    db_session, monkeypatch
):
    """The homepage links to itself with a UTM tracking parameter — that
    link should never turn into a second crawl of the same page."""

    async def fake_search(self, query, *, max_results):
        return [SearchHit(url="https://acme.example/", title="Acme Home", snippet="")]

    fetched_urls: list[str] = []

    async def fake_fetch(self, url):
        fetched_urls.append(url)
        body = _long_paragraphs("Acme builds great products.")
        html = (
            "<html><head><title>Acme</title></head><body><article>"
            f"{body}"
            '<a href="/?utm_source=newsletter">Home</a>'
            "</article></body></html>"
        )
        return FetchResult(url=url, http_status=200, html=html, content_hash=url, error=None)

    monkeypatch.setattr(research_task_module.DuckDuckGoSearchProvider, "search", fake_search)
    monkeypatch.setattr(research_task_module.PageFetcher, "fetch", fake_fetch)
    _install_stub_emit(monkeypatch, db_session)

    job_id = await _make_org_and_job(
        db_session, query="Find fintech companies", config={"max_results": 3, "max_pages": 5}
    )

    await research_task_module.run_research_job({}, str(job_id))

    assert fetched_urls == ["https://acme.example/"]


@pytest.mark.asyncio
async def test_pipeline_marks_near_duplicate_page_but_still_records_it(db_session, monkeypatch):
    """The homepage links to a /print version with nearly identical
    content (just a footer note added) — both get crawled (they're
    different URLs), but the near-duplicate should not produce a second
    ResearchResult."""

    shared_body = _long_paragraphs(
        "Acme is a fintech company based in Lagos that builds payment infrastructure "
        "for small businesses across West Africa, serving thousands of merchants daily."
    )

    async def fake_search(self, query, *, max_results):
        return [SearchHit(url="https://acme.example/", title="Acme Home", snippet="")]

    async def fake_fetch(self, url):
        if url == "https://acme.example/":
            html = (
                "<html><head><title>Acme</title></head><body><article>"
                f"{shared_body}"
                '<a href="/print">Printer-friendly version</a></article></body></html>'
            )
        elif url == "https://acme.example/print":
            html = (
                "<html><head><title>Acme (print)</title></head><body><article>"
                f"{shared_body}<p>Printed on 2026-08-25.</p></article></body></html>"
            )
        else:
            raise AssertionError(f"unexpected fetch: {url}")
        return FetchResult(url=url, http_status=200, html=html, content_hash=url, error=None)

    monkeypatch.setattr(research_task_module.DuckDuckGoSearchProvider, "search", fake_search)
    monkeypatch.setattr(research_task_module.PageFetcher, "fetch", fake_fetch)
    _install_stub_emit(monkeypatch, db_session)

    job_id = await _make_org_and_job(
        db_session, query="Find fintech companies", config={"max_results": 3, "max_pages": 5}
    )

    await research_task_module.run_research_job({}, str(job_id))

    async with db_session() as db:
        pages = (
            await db.scalars(select(CrawlPage).join(Source).where(Source.research_job_id == job_id))
        ).all()
        assert {p.url for p in pages} == {"https://acme.example/", "https://acme.example/print"}

        results = (
            await db.scalars(select(ResearchResult).where(ResearchResult.research_job_id == job_id))
        ).all()
        assert len(results) == 1  # the near-duplicate page didn't produce a second result


@pytest.mark.asyncio
async def test_pipeline_stores_structured_data_from_json_ld_and_meta_tags(db_session, monkeypatch):
    async def fake_search(self, query, *, max_results):
        return [SearchHit(url="https://acme.example/", title="Acme Home", snippet="")]

    async def fake_fetch(self, url):
        body = _long_paragraphs("Acme builds great products for everyone.")
        html = (
            "<html><head><title>Acme</title>"
            '<meta name="description" content="Acme builds payment tools.">'
            '<script type="application/ld+json">'
            '{"@type": "Organization", "name": "Acme Inc", "email": "hi@acme.com"}'
            "</script></head>"
            f"<body><article>{body}</article></body></html>"
        )
        return FetchResult(url=url, http_status=200, html=html, content_hash=url, error=None)

    monkeypatch.setattr(research_task_module.DuckDuckGoSearchProvider, "search", fake_search)
    monkeypatch.setattr(research_task_module.PageFetcher, "fetch", fake_fetch)
    _install_stub_emit(monkeypatch, db_session)

    job_id = await _make_org_and_job(
        db_session, query="Find fintech companies", config={"max_results": 3, "max_pages": 3}
    )

    await research_task_module.run_research_job({}, str(job_id))

    async with db_session() as db:
        page = (
            await db.scalars(select(CrawlPage).join(Source).where(Source.research_job_id == job_id))
        ).one()
        assert page.structured_data["meta_description"] == "Acme builds payment tools."
        assert page.structured_data["json_ld"] == [
            {"@type": "Organization", "name": "Acme Inc", "email": "hi@acme.com"}
        ]
