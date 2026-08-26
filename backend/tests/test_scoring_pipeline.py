"""End-to-end worker tests for Phase 8's Fit/Intent/Opportunity Scoring —
computed right after Verification and Commercial Signals, from the same
crawled pages — with the network layer stubbed the same way as
test_verification_pipeline.py / test_commercial_signals_pipeline.py."""

import pytest
from sqlalchemy import select

from app.engines.crawler.fetcher import FetchResult
from app.engines.query_intelligence.parser import parse_query
from app.engines.search.base import SearchHit
from app.models.entity import Company
from app.models.organization import Organization, OrganizationMember, Role
from app.models.research import ResearchJob, ResearchMode, ResearchStatus
from app.models.scoring import FitScore, IntentScore, OpportunityScore
from app.models.user import User
from app.repositories import research_repository
from app.workers.tasks import research as research_task_module


def _long_paragraphs(sentence: str, count: int = 12) -> str:
    return "".join(
        f"<p>{sentence} Filler sentence number {i} about the company.</p>" for i in range(count)
    )


async def _make_org_and_job(db_session, *, query: str, config: dict) -> object:
    async with db_session() as db:
        org = Organization(name="Scoring Test Org", slug=f"scoring-test-{id(config)}")
        user = User(
            email=f"scoring-{id(config)}@example.com", hashed_password="x", full_name="Tester"
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
async def test_pipeline_computes_all_three_scores_for_a_matching_company(db_session, monkeypatch):
    async def fake_search(self, query, *, max_results):
        return [SearchHit(url="https://acme.example/", title="Acme Home", snippet="")]

    async def fake_fetch(self, url):
        html = (
            "<html><head><title>Acme</title>"
            '<meta property="og:site_name" content="Acme">'
            "</head><body><article>"
            f"{_long_paragraphs('Acme is a leading fintech company that just raised funding.')}"
            "</article></body></html>"
        )
        return FetchResult(url=url, http_status=200, html=html, content_hash=url, error=None)

    monkeypatch.setattr(research_task_module.DuckDuckGoSearchProvider, "search", fake_search)
    monkeypatch.setattr(research_task_module.PageFetcher, "fetch", fake_fetch)
    _install_stub_emit(monkeypatch, db_session)

    job_id = await _make_org_and_job(
        db_session,
        query="Find fintech companies",
        config={"max_results": 3, "max_pages": 3},
    )

    await research_task_module.run_research_job({}, str(job_id))

    async with db_session() as db:
        company = (await db.scalars(select(Company).where(Company.research_job_id == job_id))).one()

        fit = (await db.scalars(select(FitScore).where(FitScore.company_id == company.id))).one()
        assert fit.score == 1.0
        assert fit.matched_factors == ["industry:fintech"]

        intent = (
            await db.scalars(select(IntentScore).where(IntentScore.company_id == company.id))
        ).one()
        assert intent.score > 0.0
        assert intent.contributing_signals[0]["signal_type"] == "funding"

        opportunity = (
            await db.scalars(
                select(OpportunityScore).where(OpportunityScore.company_id == company.id)
            )
        ).one()
        assert 0.0 < opportunity.score <= 1.0
        assert opportunity.fit_score_id == fit.id
        assert opportunity.intent_score_id == intent.id
        assert opportunity.weights_used["fit"] == 0.3


@pytest.mark.asyncio
async def test_pipeline_fit_score_is_none_for_a_query_with_no_criteria(db_session, monkeypatch):
    async def fake_search(self, query, *, max_results):
        return [SearchHit(url="https://acme.example/", title="Acme Home", snippet="")]

    async def fake_fetch(self, url):
        html = (
            "<html><head><title>Acme</title>"
            '<meta property="og:site_name" content="Acme">'
            "</head><body><article>"
            f"{_long_paragraphs('Acme makes widgets for widget enthusiasts everywhere.')}"
            "</article></body></html>"
        )
        return FetchResult(url=url, http_status=200, html=html, content_hash=url, error=None)

    monkeypatch.setattr(research_task_module.DuckDuckGoSearchProvider, "search", fake_search)
    monkeypatch.setattr(research_task_module.PageFetcher, "fetch", fake_fetch)
    _install_stub_emit(monkeypatch, db_session)

    # A query with no matchable industry/geography/attribute keywords —
    # parse_query still needs >= 3 chars and won't tag anything specific.
    job_id = await _make_org_and_job(
        db_session, query="Find some companies please", config={"max_results": 3, "max_pages": 3}
    )

    await research_task_module.run_research_job({}, str(job_id))

    async with db_session() as db:
        company = (await db.scalars(select(Company).where(Company.research_job_id == job_id))).one()
        fit = (await db.scalars(select(FitScore).where(FitScore.company_id == company.id))).one()
        assert fit.score is None

        opportunity = (
            await db.scalars(
                select(OpportunityScore).where(OpportunityScore.company_id == company.id)
            )
        ).one()
        # None fit falls back to the neutral 0.5 component, not 0 or an error.
        assert opportunity.fit_component == 0.5
