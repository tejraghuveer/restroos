from __future__ import annotations

import httpx

from tests.helpers import bearer, client_for, register_owner


async def test_owner_can_create_and_switch_branches(
    client: httpx.AsyncClient,
) -> None:
    session = await register_owner(
        client, email="multi@spice.example", business_name="Multi Branch"
    )
    headers = bearer(session["access_token"])
    first_branch = session["context"]["restaurant_id"]

    created = await client.post(
        "/api/v1/restaurants",
        headers=headers,
        json={"name": "Indiranagar", "city": "Bengaluru"},
    )
    assert created.status_code == 201, created.text
    second_branch = created.json()["id"]

    branches = await client.get("/api/v1/restaurants", headers=headers)
    assert [item["id"] for item in branches.json()] == [first_branch, second_branch]

    switched = await client.post(
        "/api/v1/auth/switch-context",
        headers=headers,
        json={"restaurant_id": second_branch},
    )
    assert switched.status_code == 200, switched.text
    assert switched.json()["context"]["restaurant_id"] == second_branch
    assert switched.json()["context"]["tenant_wide"] is True

    back = await client.post(
        "/api/v1/auth/switch-context",
        headers=bearer(switched.json()["access_token"]),
        json={"restaurant_id": first_branch},
    )
    assert back.status_code == 200
    assert back.json()["context"]["restaurant_id"] == first_branch


async def test_switch_to_unknown_branch_is_not_found(client: httpx.AsyncClient) -> None:
    session = await register_owner(
        client, email="switch@spice.example", business_name="Switch Co"
    )
    response = await client.post(
        "/api/v1/auth/switch-context",
        headers=bearer(session["access_token"]),
        json={"restaurant_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


async def test_tenant_update_is_scoped_to_owner(client: httpx.AsyncClient) -> None:
    session = await register_owner(
        client, email="rename@spice.example", business_name="Rename Co"
    )
    headers = bearer(session["access_token"])

    updated = await client.patch(
        "/api/v1/tenant",
        headers=headers,
        json={"name": "Renamed Co", "timezone": "Asia/Kolkata"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Renamed Co"

    invalid_tz = await client.patch(
        "/api/v1/tenant", headers=headers, json={"timezone": "Mars/Olympus"}
    )
    assert invalid_tz.status_code == 422


async def test_branch_creation_respects_free_plan_limit(make_app) -> None:
    app = await make_app(free_plan_max_restaurants=1)
    async with client_for(app) as client:
        session = await register_owner(
            client, email="limit@spice.example", business_name="Limit Co"
        )
        response = await client.post(
            "/api/v1/restaurants",
            headers=bearer(session["access_token"]),
            json={"name": "Second Branch"},
        )
        assert response.status_code == 403
        assert "plan allows 1 restaurant" in response.json()["detail"]
