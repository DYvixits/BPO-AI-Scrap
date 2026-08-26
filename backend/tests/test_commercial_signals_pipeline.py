"""End-to-end worker tests for Phase 7's Commercial Signal Engine —
detecting keyword signals on a resolved company's crawled pages right
after Verification runs — with the network layer stubbed the same way as
test_verification_pipeline.py."""

import pytest
from sqlalchemy import select

from app.engines.commercial_signals.detector import CommercialSignalType
from app.engines.crawler.fetcher import FetchResult
from app.engines.query_intelligence.parser import parse_query
from app.engines.search.base import SearchHit
from app.models.commercial_signal import CommercialSignal
from app.models.entity import Company
from app.models.organization import Organization, OrganizationMember, Role
from app.models.research import ResearchEvent, ResearchJob, ResearchMode, ResearchStatus
from app.models.user import User
from app.repositories import research_repository
from app.workers.tasks import research as research_task_module


def _long_paragraphs(sentence: str, count: int = 12) -> str:
    return "".join(
        f"<p>{sentence} Filler sentence number {i} about the company.</p>" for i in range(count)
    )


async def _make_org_and_job(db_session, *, query: str, config: dict) -> object:
    async with db_session() as db:
        org = Organization(name="Signals Test Org", slug=f"signals-test-{id(config)}")
        user = User(
            email=f"signals-{id(config)}@example.com", hashed_password="x", full_name="Tester"
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
async def test_pipeline_detects_funding_signal_on_a_crawled_page(db_session, monkeypatch):
    async def fake_search(self, query, *, max_results):
        return [SearchHit(url="https://acme.example/", title="Acme Home", snippet="")]

    async def fake_fetch(self, url):
        html = (
            "<html><head><title>Acme</title>"
            '<meta property="og:site_name" content="Acme">'
            "</head><body><article>"
            f"{_long_paragraphs('Acme just raised a new funding round from top investors.')}"
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
        signals = (
            await db.scalars(
                select(CommercialSignal).where(CommercialSignal.company_id == company.id)
            )
        ).all()
        assert len(signals) == 1
        assert signals[0].signal_type == CommercialSignalType.FUNDING
        assert signals[0].polarity == "positive"
        assert signals[0].decayed_strength == 1.0
        assert signals[0].source_url == "https://acme.example/"


@pytest.mark.asyncio
async def test_pipeline_finds_no_signals_on_generic_content(db_session, monkeypatch):
    async def fake_search(self, query, *, max_results):
        return [SearchHit(url="https://acme.example/", title="Acme Home", snippet="")]

    async def fake_fetch(self, url):
        html = (
            "<html><head><title>Acme</title>"
            '<meta property="og:site_name" content="Acme">'
            "</head><body><article>"
            f"{_long_paragraphs('Acme is a company that makes widgets for widget enthusiasts.')}"
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
        signals = (await db.scalars(select(CommercialSignal))).all()
        assert signals == []

        events = (
            await db.scalars(select(ResearchEvent).where(ResearchEvent.research_job_id == job_id))
        ).all()
        assert all(e.kind != "signals.detected" for e in events)
