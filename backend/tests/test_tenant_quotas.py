"""Quota enforcement (master spec §38 — fair resource scheduling). This is
pure app-layer logic (count active jobs, compare to TenantQuota), so it's
fully testable against SQLite — unlike Row-Level Security itself, which
needs a real PostgreSQL and is covered separately in tests/test_rls.py."""

import pytest


@pytest.mark.asyncio
async def test_standard_tier_blocks_a_third_concurrent_job(client, auth_headers):
    # standard tier default: max_concurrent_research_jobs = 2 (jobs never
    # actually run in this test — arq enqueue is mocked to a no-op by the
    # `no_real_redis` conftest fixture — so both stay "queued," i.e. active).
    first = await client.post(
        "/api/v1/research", json={"query": "First query"}, headers=auth_headers
    )
    second = await client.post(
        "/api/v1/research", json={"query": "Second query"}, headers=auth_headers
    )
    assert first.status_code == 201
    assert second.status_code == 201

    third = await client.post(
        "/api/v1/research", json={"query": "Third query"}, headers=auth_headers
    )
    assert third.status_code == 429
    assert "2/2" in third.json()["detail"] or "limit" in third.json()["detail"].lower()


@pytest.mark.asyncio
async def test_quota_is_per_organization_not_global(client, auth_headers):
    # Two jobs for org A should not affect org B's ability to create its own.
    await client.post("/api/v1/research", json={"query": "Org A job 1"}, headers=auth_headers)
    await client.post("/api/v1/research", json={"query": "Org A job 2"}, headers=auth_headers)

    other_org = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "quota-other-org@example.com",
            "password": "another correct horse battery",
            "full_name": "Other Org Admin",
            "organization_name": "Other Quota Org",
        },
    )
    other_headers = {"Authorization": f"Bearer {other_org.json()['access_token']}"}

    response = await client.post(
        "/api/v1/research", json={"query": "Org B's own first job"}, headers=other_headers
    )
    assert response.status_code == 201
