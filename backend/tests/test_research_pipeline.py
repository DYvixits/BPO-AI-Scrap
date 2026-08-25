"""End-to-end test of the worker pipeline itself (search -> crawl -> extract
-> store), with the network-touching pieces (search provider, HTTP fetch)
stubbed so CI never depends on live internet access. Everything else —
DB writes, event log, status transitions, confidence scoring, dedup — is
real."""

import pytest

from app.engines.crawler.fetcher import FetchResult
from app.engines.search.base import SearchHit
from app.models.organization import Organization, OrganizationMember, Role
from app.models.research import ResearchJob, ResearchMode, ResearchResult, ResearchStatus
from app.models.user import User
from app.repositories import research_repository
from app.workers.tasks import research as research_task_module


@pytest.mark.asyncio
async def test_pipeline_completes_and_stores_results(db_session, monkeypatch):
    async def fake_search(self, query, *, max_results):
        return [
            SearchHit(
                url="https://example.com/company-x", title="Company X", snippet="A fintech company"
            ),
            SearchHit(url="https://example.com/broken-page", title="Broken", snippet=""),
        ]

    async def fake_fetch(self, url):
        if "broken" in url:
            return FetchResult(
                url=url, http_status=500, html=None, content_hash=None, error="server error"
            )
        paragraphs = "".join(
            f"<p>Company X raised its Series {chr(65 + i)} round in African fintech market segment "
            f"number {i}, expanding operations and hiring across the continent this quarter.</p>"
            for i in range(12)
        )
        html = (
            "<html><head><title>Company X</title></head><body>"
            f"<article><h1>Company X</h1>{paragraphs}</article>"
            "</body></html>"
        )
        return FetchResult(url=url, http_status=200, html=html, content_hash="deadbeef", error=None)

    monkeypatch.setattr(research_task_module.DuckDuckGoSearchProvider, "search", fake_search)
    monkeypatch.setattr(research_task_module.PageFetcher, "fetch", fake_fetch)

    async def fake_emit(organization_id, job_id, kind, payload):
        # avoid requiring a live Redis for pub/sub in this unit test — the DB
        # side of event logging is still exercised via add_event below.
        async with db_session() as db:
            await research_repository.add_event(
                db, organization_id=organization_id, job_id=job_id, kind=kind, payload=payload
            )

    monkeypatch.setattr(research_task_module, "_emit", fake_emit)

    async with db_session() as db:
        org = Organization(name="Test Org", slug="test-org")
        user = User(email="pipeline@example.com", hashed_password="x", full_name="Pipeline Tester")
        db.add_all([org, user])
        await db.flush()
        db.add(OrganizationMember(organization_id=org.id, user_id=user.id, role=Role.ADMIN))
        job = ResearchJob(
            organization_id=org.id,
            created_by=user.id,
            query="African fintech companies",
            mode=ResearchMode.QUICK,
            config={"max_results": 3},
            status=ResearchStatus.CREATED,
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        job_id = job.id

    await research_task_module.run_research_job({}, str(job_id))

    async with db_session() as db:
        refreshed = await db.get(ResearchJob, job_id)
        assert refreshed.status == ResearchStatus.COMPLETED
        assert refreshed.error is None

        from sqlalchemy import select

        results = (
            await db.scalars(select(ResearchResult).where(ResearchResult.research_job_id == job_id))
        ).all()
        assert len(results) == 1  # the broken page yields no result, the good one does
        assert results[0].url == "https://example.com/company-x"
        assert results[0].confidence > 0.5  # base + 200 OK + long extracted text


@pytest.mark.asyncio
async def test_pipeline_with_no_search_hits_completes_with_zero_results(db_session, monkeypatch):
    async def fake_search(self, query, *, max_results):
        return []

    monkeypatch.setattr(research_task_module.DuckDuckGoSearchProvider, "search", fake_search)

    async def fake_emit(organization_id, job_id, kind, payload):
        async with db_session() as db:
            await research_repository.add_event(
                db, organization_id=organization_id, job_id=job_id, kind=kind, payload=payload
            )

    monkeypatch.setattr(research_task_module, "_emit", fake_emit)

    async with db_session() as db:
        org = Organization(name="Empty Org", slug="empty-org")
        user = User(email="empty@example.com", hashed_password="x", full_name="Empty Tester")
        db.add_all([org, user])
        await db.flush()
        db.add(OrganizationMember(organization_id=org.id, user_id=user.id, role=Role.ADMIN))
        job = ResearchJob(
            organization_id=org.id,
            created_by=user.id,
            query="Something with no results",
            mode=ResearchMode.QUICK,
            config={"max_results": 3},
            status=ResearchStatus.CREATED,
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        job_id = job.id

    await research_task_module.run_research_job({}, str(job_id))

    async with db_session() as db:
        refreshed = await db.get(ResearchJob, job_id)
        assert refreshed.status == ResearchStatus.COMPLETED
