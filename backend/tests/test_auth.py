import pytest


@pytest.mark.asyncio
async def test_register_returns_tokens(client):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "founder@example.com",
            "password": "correct horse battery staple",
            "full_name": "Founding Researcher",
            "organization_name": "Example Org",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_register_duplicate_email_rejected(client, registered_user):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "researcher@example.com",  # same as registered_user fixture
            "password": "another password entirely",
            "full_name": "Someone Else",
            "organization_name": "Another Org",
        },
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_login_with_correct_credentials(client, registered_user):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "researcher@example.com", "password": "correct horse battery staple"},
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


@pytest.mark.asyncio
async def test_login_with_wrong_password_rejected(client, registered_user):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "researcher@example.com", "password": "wrong password"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_auth(client):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_profile(client, auth_headers):
    response = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "researcher@example.com"
    assert body["role"] == "admin"  # first user in a new org is its admin
    assert body["organization"]["name"] == "Acme Research Co"


@pytest.mark.asyncio
async def test_refresh_issues_new_access_token(client, registered_user):
    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": registered_user["refresh_token"]}
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


@pytest.mark.asyncio
async def test_refresh_rejects_access_token(client, registered_user):
    # Passing an access token where a refresh token is expected must fail —
    # the two token types are not interchangeable.
    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": registered_user["access_token"]}
    )
    assert response.status_code == 401
