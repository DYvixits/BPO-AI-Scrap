import pytest


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

    other_listing = await client.get("/api/v1/research", headers=other_headers)
    assert all(job["id"] != job_id for job in other_listing.json())
