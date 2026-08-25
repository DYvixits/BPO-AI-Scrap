"""End-to-end worker tests for Phase 5's Entity Resolution — grouping
crawled pages into companies — with the network layer stubbed the same
way as test_research_pipeline.py."""

import pytest
from sqlalchemy import select

from app.engines.crawler.fetcher import FetchResult
from app.engines.query_intelligence.parser import parse_query
from app.engines.search.base import SearchHit
from app.models.entity import Company, EntityAlias
from app.models.organization import Organization, OrganizationMember, Role
from app.models.research import ResearchJob, ResearchMode, ResearchResult, ResearchStatus
from app.models.user import User
from app.repositories import research_repository
from app.workers.tasks import research as research_task_module


def _long_paragraphs(sentence: str, count: int = 12) -> str:
    return "".join(
        f"<p>{sentence} Filler sentence number {i} about the company.</p>" for i in range(count)
    )


async def _make_org_and_job(db_session, *, query: str, config: dict) -> object:
    async with db_session() as db:
        org = Organization(name="Entity Test Org", slug=f"entity-test-{id(config)}")
        user = User(
            email=f"entity-{id(config)}@example.com", hashed_password="x", full_name="Tester"
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
async def test_pipeline_resolves_same_domain_pages_into_one_company(db_session, monkeypatch):
    async def fake_search(self, query, *, max_results):
        return [SearchHit(url="https://acme.example/", title="Acme Home", snippet="")]

    async def fake_fetch(self, url):
        if url == "https://acme.example/":
            html = (
                "<html><head><title>Acme</title>"
                '<meta property="og:site_name" content="Acme">'
                "</head><body><article>"
                f"{_long_paragraphs('Acme builds great products.')}"
                '<a href="/about">About</a></article></body></html>'
            )
        elif url == "https://acme.example/about":
            html = (
                "<html><head><title>About Acme</title>"
                '<meta property="og:site_name" content="Acme">'
                "</head><body><article>"
                f"{_long_paragraphs('Acme was founded in 2019.')}"
                "</article></body></html>"
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
        companies = (
            await db.scalars(select(Company).where(Company.research_job_id == job_id))
        ).all()
        assert len(companies) == 1
        assert companies[0].canonical_name == "Acme"
        assert companies[0].primary_domain == "acme.example"
        assert companies[0].match_confidence == 1.0

        results = (
            await db.scalars(select(ResearchResult).where(ResearchResult.research_job_id == job_id))
        ).all()
        assert len(results) == 2
        assert all(r.company_id == companies[0].id for r in results)

        aliases = (
            await db.scalars(select(EntityAlias).where(EntityAlias.company_id == companies[0].id))
        ).all()
        alias_values = {a.value for a in aliases}
        assert "Acme" in alias_values
        assert "acme.example" in alias_values


@pytest.mark.asyncio
async def test_pipeline_merges_two_domains_with_matching_company_names(db_session, monkeypatch):
    async def fake_search(self, query, *, max_results):
        return [
            SearchHit(url="https://acme.example/", title="Acme Home", snippet=""),
            SearchHit(url="https://directory.example/acme", title="Acme on Directory", snippet=""),
        ]

    async def fake_fetch(self, url):
        body = _long_paragraphs(f"Some unique content for {url}.")
        html = (
            "<html><head><title>Acme</title>"
            '<meta property="og:site_name" content="Acme Inc">'
            f"</head><body><article>{body}</article></body></html>"
        )
        return FetchResult(url=url, http_status=200, html=html, content_hash=url, error=None)

    monkeypatch.setattr(research_task_module.DuckDuckGoSearchProvider, "search", fake_search)
    monkeypatch.setattr(research_task_module.PageFetcher, "fetch", fake_fetch)
    _install_stub_emit(monkeypatch, db_session)

    job_id = await _make_org_and_job(
        db_session, query="Find fintech companies", config={"max_results": 3, "max_pages": 5}
    )

    await research_task_module.run_research_job({}, str(job_id))

    async with db_session() as db:
        companies = (
            await db.scalars(select(Company).where(Company.research_job_id == job_id))
        ).all()
        assert len(companies) == 1
        assert companies[0].match_confidence == 0.7

        results = (
            await db.scalars(select(ResearchResult).where(ResearchResult.research_job_id == job_id))
        ).all()
        assert len(results) == 2
        assert all(r.company_id == companies[0].id for r in results)


@pytest.mark.asyncio
async def test_pipeline_with_no_search_hits_resolves_no_companies(db_session, monkeypatch):
    async def fake_search(self, query, *, max_results):
        return []

    monkeypatch.setattr(research_task_module.DuckDuckGoSearchProvider, "search", fake_search)
    _install_stub_emit(monkeypatch, db_session)

    job_id = await _make_org_and_job(
        db_session, query="Find fintech companies", config={"max_results": 3, "max_pages": 5}
    )

    await research_task_module.run_research_job({}, str(job_id))

    async with db_session() as db:
        companies = (
            await db.scalars(select(Company).where(Company.research_job_id == job_id))
        ).all()
        assert companies == []
