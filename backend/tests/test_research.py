import pytest

from app.engines.crawler.fetcher import FetchResult
from app.engines.search.base import SearchHit
from app.workers.tasks import research as research_task_module


@pytest.mark.asyncio
async def test_create_research_requires_auth(client):
    response = await client.post("/api/v1/research", json={"query": "African fintech companies"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_research_returns_queued_job(client, auth_headers):
    response = await client.post(
        "/api/v1/research",
        json={"query": "African fintech companies founded after 2020", "mode": "quick"},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "queued"
    assert body["mode"] == "quick"
    assert body["config"]["max_results"] == 3  # quick mode default


@pytest.mark.asyncio
async def test_create_research_rejects_short_query(client, auth_headers):
    response = await client.post("/api/v1/research", json={"query": "hi"}, headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_and_get_research(client, auth_headers):
    create = await client.post(
        "/api/v1/research", json={"query": "Kenyan agritech startups"}, headers=auth_headers
    )
    job_id = create.json()["id"]

    listing = await client.get("/api/v1/research", headers=auth_headers)
    assert listing.status_code == 200
    assert any(job["id"] == job_id for job in listing.json())

    detail = await client.get(f"/api/v1/research/{job_id}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["id"] == job_id
    assert "events" in detail.json()


@pytest.mark.asyncio
async def test_get_unknown_research_returns_404(client, auth_headers):
    response = await client.get(
        "/api/v1/research/00000000-0000-0000-0000-000000000000", headers=auth_headers
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_results_empty_before_pipeline_runs(client, auth_headers):
    create = await client.post(
        "/api/v1/research", json={"query": "Nigerian logistics startups"}, headers=auth_headers
    )
    job_id = create.json()["id"]
    results = await client.get(f"/api/v1/research/{job_id}/results", headers=auth_headers)
    assert results.status_code == 200
    assert results.json() == []


@pytest.mark.asyncio
async def test_companies_empty_before_pipeline_runs(client, auth_headers):
    create = await client.post(
        "/api/v1/research", json={"query": "Nigerian logistics startups"}, headers=auth_headers
    )
    job_id = create.json()["id"]
    companies = await client.get(f"/api/v1/research/{job_id}/companies", headers=auth_headers)
    assert companies.status_code == 200
    assert companies.json() == []


@pytest.mark.asyncio
async def test_companies_for_unknown_research_returns_404(client, auth_headers):
    response = await client.get(
        "/api/v1/research/00000000-0000-0000-0000-000000000000/companies", headers=auth_headers
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_companies_response_includes_verification_and_evidence(
    client, auth_headers, monkeypatch
):
    """API-layer check that CompanyOut's nested confidence_score/evidence/
    signals actually serialize from the ORM relationships (entity_
    repository.py's eager-loads) — the pipeline tests in
    test_verification_pipeline.py / test_commercial_signals_pipeline.py
    check the DB rows directly, not that FastAPI can turn them into JSON."""

    async def fake_search(self, query, *, max_results):
        return [SearchHit(url="https://acme.example/", title="Acme Home", snippet="")]

    async def fake_fetch(self, url):
        html = (
            "<html><head><title>Acme</title>"
            '<meta property="og:site_name" content="Acme">'
            "</head><body><article>"
            "<p>Acme is a fintech company hiring across every team this quarter.</p>"
            + "".join(f"<p>Acme builds great products, sentence {i}.</p>" for i in range(12))
            + "</article></body></html>"
        )
        return FetchResult(url=url, http_status=200, html=html, content_hash=url, error=None)

    async def fake_emit(organization_id, job_id, kind, payload):
        return None

    monkeypatch.setattr(research_task_module.DuckDuckGoSearchProvider, "search", fake_search)
    monkeypatch.setattr(research_task_module.PageFetcher, "fetch", fake_fetch)
    monkeypatch.setattr(research_task_module, "_emit", fake_emit)

    create = await client.post(
        "/api/v1/research",
        json={"query": "Find fintech companies", "config": {"max_results": 3, "max_pages": 3}},
        headers=auth_headers,
    )
    job_id = create.json()["id"]

    await research_task_module.run_research_job({}, job_id)

    response = await client.get(f"/api/v1/research/{job_id}/companies", headers=auth_headers)
    assert response.status_code == 200
    companies = response.json()
    assert len(companies) == 1
    company = companies[0]
    assert company["confidence_score"]["status"] == "uncertain"
    assert company["confidence_score"]["source_diversity"] == 1
    assert len(company["evidence"]) == 1
    assert company["evidence"][0]["domain"] == "acme.example"
    assert len(company["signals"]) == 1
    assert company["signals"][0]["signal_type"] == "hiring"
    assert company["signals"][0]["decayed_strength"] == 1.0
    assert company["fit_score"]["score"] == 1.0
    assert company["fit_score"]["matched_factors"] == ["industry:fintech"]
    assert company["intent_score"]["score"] > 0.0
    assert 0.0 < company["opportunity_score"]["score"] <= 1.0


@pytest.mark.asyncio
async def test_organizations_cannot_see_each_others_research(client, auth_headers):
    other_org = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "second-org@example.com",
            "password": "another correct horse battery",
            "full_name": "Second Org Admin",
            "organization_name": "Rival Research Co",
        },
    )
    other_headers = {"Authorization": f"Bearer {other_org.json()['access_token']}"}

    create = await client.post(
        "/api/v1/research",
        json={"query": "First org's confidential research"},
        headers=auth_headers,
    )
    job_id = create.json()["id"]

    # The second organization must not be able to fetch the first org's job,
    # nor see it in its own listing — this is the tenant-isolation guarantee
    # SECURITY.md documents.
    cross_org_get = await client.get(f"/api/v1/research/{job_id}", headers=other_headers)
    assert cross_org_get.status_code == 404

    cross_org_companies = await client.get(
        f"/api/v1/research/{job_id}/companies", headers=other_headers
    )
    assert cross_org_companies.status_code == 404

    other_listing = await client.get("/api/v1/research", headers=other_headers)
    assert all(job["id"] != job_id for job in other_listing.json())
