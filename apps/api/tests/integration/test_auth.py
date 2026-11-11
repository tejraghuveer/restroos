from __future__ import annotations

import httpx

from tests.helpers import (
    TEST_PASSWORD,
    bearer,
    client_for,
    login,
    register_owner,
)


async def test_health_and_readiness(client: httpx.AsyncClient) -> None:
    health = await client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    ready = await client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"


async def test_registration_bootstraps_tenant_owner_branch_and_plan(
    client: httpx.AsyncClient,
) -> None:
    session = await register_owner(
        client, email="owner@spice.example", business_name="Spice Route"
    )

    assert session["token_type"] == "bearer"
    assert session["access_token"]
    assert "password" not in str(session).lower()

    context = session["context"]
    assert context["role"] == "owner"
    assert context["tenant_name"] == "Spice Route"
    assert context["tenant_wide"] is True
    assert context["restaurant_id"]
    assert "tenant:manage" in context["permissions"]

    headers = bearer(session["access_token"])
    tenant = await client.get("/api/v1/tenant", headers=headers)
    assert tenant.status_code == 200, tenant.text
    assert tenant.json()["slug"] == "spice-route"

    restaurants = await client.get("/api/v1/restaurants", headers=headers)
    assert restaurants.status_code == 200
    assert len(restaurants.json()) == 1
    assert restaurants.json()[0]["currency"] == "INR"

    billing = await client.get("/api/v1/billing/subscription", headers=headers)
    assert billing.status_code == 200
    assert billing.json()["plan_code"] == "free"
    assert billing.json()["limits"]["max_restaurants"] >= 1

    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "owner@spice.example"


async def test_login_returns_session_and_rejects_bad_credentials(
    client: httpx.AsyncClient,
) -> None:
    await register_owner(client, email="login@spice.example", business_name="Login Co")
    await client.post("/api/v1/auth/logout")

    rejected = await login(client, email="login@spice.example", password="wrong-password")
    assert rejected.status_code == 401
    assert rejected.headers["content-type"].startswith("application/problem+json")
    assert rejected.json()["code"] == "unauthorized"

    unknown = await login(client, email="nobody@spice.example")
    assert unknown.status_code == 401

    accepted = await login(client, email="login@spice.example")
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["access_token"]

    me = await client.get(
        "/api/v1/auth/me", headers=bearer(accepted.json()["access_token"])
    )
    assert me.status_code == 200


async def test_duplicate_registration_is_rejected(client: httpx.AsyncClient) -> None:
    await register_owner(client, email="dupe@spice.example", business_name="Dupe Co")
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "DUPE@spice.example",
            "password": TEST_PASSWORD,
            "full_name": "Another Owner",
            "business_name": "Dupe Two",
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "email_already_registered"


async def test_refresh_rotates_and_reuse_revokes_the_family(
    app, client: httpx.AsyncClient
) -> None:
    await register_owner(client, email="rotate@spice.example", business_name="Rotate Co")
    old_refresh = client.cookies.get("restroos_refresh")
    assert old_refresh

    refreshed = await client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200, refreshed.text
    new_refresh = client.cookies.get("restroos_refresh")
    assert new_refresh
    assert new_refresh != old_refresh

    async with client_for(app) as replay_client:
        replay = await replay_client.post(
            "/api/v1/auth/refresh",
            headers={"Cookie": f"restroos_refresh={old_refresh}"},
        )
    assert replay.status_code == 401

    # Reuse detection revokes the whole family, including the newest token.
    after_reuse = await client.post("/api/v1/auth/refresh")
    assert after_reuse.status_code == 401


async def test_logout_revokes_refresh_session(client: httpx.AsyncClient) -> None:
    await register_owner(client, email="logout@spice.example", business_name="Logout Co")
    logout = await client.post("/api/v1/auth/logout")
    assert logout.status_code == 204

    refreshed = await client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 401


async def test_unauthenticated_and_invalid_tokens_are_problem_json(
    client: httpx.AsyncClient,
) -> None:
    anonymous = await client.get("/api/v1/tenant")
    assert anonymous.status_code == 401
    assert anonymous.headers["www-authenticate"] == "Bearer"
    assert anonymous.json()["code"] == "unauthorized"

    invalid = await client.get(
        "/api/v1/tenant", headers=bearer("not-a-jwt")
    )
    assert invalid.status_code == 401
    assert invalid.json()["code"] == "unauthorized"


async def test_validation_errors_are_problem_json(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "not-an-email",
            "password": "short",
            "full_name": "X",
            "business_name": "Y",
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["errors"]
