"""End-to-end worker tests for Phase 6's Verification Engine — computing a
per-company confidence score and evidence trail right after Entity
Resolution groups pages — with the network layer stubbed the same way as
test_entity_resolution_pipeline.py."""

import pytest
from sqlalchemy import select

from app.engines.crawler.fetcher import FetchResult
from app.engines.query_intelligence.parser import parse_query
from app.engines.search.base import SearchHit
from app.engines.verification.engine import TruthStatus
from app.models.entity import Company
from app.models.organization import Organization, OrganizationMember, Role
from app.models.research import ResearchJob, ResearchMode, ResearchStatus
from app.models.user import User
from app.models.verification import ConfidenceScore, Evidence
from app.repositories import research_repository
from app.workers.tasks import research as research_task_module


def _long_paragraphs(sentence: str, count: int = 12) -> str:
    return "".join(
        f"<p>{sentence} Filler sentence number {i} about the company.</p>" for i in range(count)
    )


async def _make_org_and_job(db_session, *, query: str, config: dict) -> object:
    async with db_session() as db:
        org = Organization(name="Verify Test Org", slug=f"verify-test-{id(config)}")
        user = User(
            email=f"verify-{id(config)}@example.com", hashed_password="x", full_name="Tester"
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
async def test_single_domain_company_is_uncertain(db_session, monkeypatch):
    async def fake_search(self, query, *, max_results):
        return [SearchHit(url="https://acme.example/", title="Acme Home", snippet="")]

    async def fake_fetch(self, url):
        html = (
            "<html><head><title>Acme</title>"
            '<meta property="og:site_name" content="Acme">'
            "</head><body><article>"
            f"{_long_paragraphs('Acme builds great products.')}"
            "</article></body></html>"
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
        company = (await db.scalars(select(Company).where(Company.research_job_id == job_id))).one()
        score = (
            await db.scalars(
                select(ConfidenceScore).where(ConfidenceScore.company_id == company.id)
            )
        ).one()
        assert score.status == TruthStatus.UNCERTAIN
        assert score.source_count == 1
        assert score.source_diversity == 1
        assert score.freshness_score == 1.0

        evidence = (
            await db.scalars(select(Evidence).where(Evidence.company_id == company.id))
        ).all()
        assert len(evidence) == 1
        assert evidence[0].domain == "acme.example"
        assert evidence[0].excerpt and "Acme builds great products" in evidence[0].excerpt


@pytest.mark.asyncio
async def test_three_domain_merge_is_verified(db_session, monkeypatch):
    urls = [
        "https://acme.example/",
        "https://directory.example/acme",
        "https://news.example/acme-profile",
    ]

    async def fake_search(self, query, *, max_results):
        return [SearchHit(url=u, title="Acme", snippet="") for u in urls]

    async def fake_fetch(self, url):
        body = _long_paragraphs(f"Some unique content for {url}.")
        html = (
            "<html><head><title>Acme</title>"
            '<meta property="og:site_name" content="Acme">'
            f"</head><body><article>{body}</article></body></html>"
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
        company = (await db.scalars(select(Company).where(Company.research_job_id == job_id))).one()
        score = (
            await db.scalars(
                select(ConfidenceScore).where(ConfidenceScore.company_id == company.id)
            )
        ).one()
        assert score.status == TruthStatus.VERIFIED
        assert score.source_diversity == 3
        assert score.source_count == 3

        evidence = (
            await db.scalars(select(Evidence).where(Evidence.company_id == company.id))
        ).all()
        assert {e.domain for e in evidence} == {"acme.example", "directory.example", "news.example"}


@pytest.mark.asyncio
async def test_no_companies_means_no_confidence_scores(db_session, monkeypatch):
    async def fake_search(self, query, *, max_results):
        return []

    monkeypatch.setattr(research_task_module.DuckDuckGoSearchProvider, "search", fake_search)
    _install_stub_emit(monkeypatch, db_session)

    job_id = await _make_org_and_job(
        db_session, query="Find fintech companies", config={"max_results": 3, "max_pages": 3}
    )

    await research_task_module.run_research_job({}, str(job_id))

    async with db_session() as db:
        scores = (await db.scalars(select(ConfidenceScore))).all()
        assert scores == []
