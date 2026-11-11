from __future__ import annotations

import httpx

from tests.helpers import bearer, client_for, register_owner


async def test_tenant_a_cannot_read_or_mutate_tenant_b(
    app, client: httpx.AsyncClient
) -> None:
    tenant_a = await register_owner(
        client, email="owner-a@isolation.example", business_name="Tenant A"
    )
    headers_a = bearer(tenant_a["access_token"])

    async with client_for(app) as client_b:
        tenant_b = await register_owner(
            client_b, email="owner-b@isolation.example", business_name="Tenant B"
        )
        headers_b = bearer(tenant_b["access_token"])

        b_branch = tenant_b["context"]["restaurant_id"]
        b_membership = tenant_b["available_contexts"][0]["membership_id"]

        # Direct object access across tenants returns 404, not 403, so IDs do
        # not leak existence.
        read_b_branch = await client.get(
            f"/api/v1/restaurants/{b_branch}", headers=headers_a
        )
        assert read_b_branch.status_code == 404

        # Cannot move a session into another tenant's membership.
        switch = await client.post(
            "/api/v1/auth/switch-context",
            headers=headers_a,
            json={"membership_id": b_membership},
        )
        assert switch.status_code == 404

        # Cannot invite staff into another tenant's branch.
        invite = await client.post(
            "/api/v1/staff/invitations",
            headers=headers_a,
            json={
                "email": "plant@isolation.example",
                "role": "cashier",
                "restaurant_id": b_branch,
            },
        )
        assert invite.status_code == 404

        # Cannot mutate another tenant's membership.
        update = await client.patch(
            f"/api/v1/staff/{b_membership}",
            headers=headers_a,
            json={"status": "suspended"},
        )
        assert update.status_code == 404

        remove = await client.delete(
            f"/api/v1/staff/{b_membership}", headers=headers_a
        )
        assert remove.status_code == 404

        # Staff listings contain only the caller's tenant.
        staff_a = await client.get("/api/v1/staff", headers=headers_a)
        assert staff_a.status_code == 200
        assert {item["tenant_id"] for item in staff_a.json()} == {
            tenant_a["context"]["tenant_id"]
        }

        staff_b = await client_b.get("/api/v1/staff", headers=headers_b)
        assert {item["tenant_id"] for item in staff_b.json()} == {
            tenant_b["context"]["tenant_id"]
        }

        # A stolen invitation token is still bound to the invited email.
        invitation = await client_b.post(
            "/api/v1/staff/invitations",
            headers=headers_b,
            json={"email": "victim@isolation.example", "role": "waiter"},
        )
        assert invitation.status_code == 201
        stolen = invitation.json()["invite_token"]

        accept = await client.post(
            "/api/v1/staff/invitations/accept",
            headers=headers_a,
            json={"token": stolen},
        )
        assert accept.status_code == 403


async def test_owner_tokens_are_bound_to_their_tenant_claim(
    app, client: httpx.AsyncClient
) -> None:
    session = await register_owner(
        client, email="claims@isolation.example", business_name="Claims Co"
    )
    headers = bearer(session["access_token"])

    own = await client.get("/api/v1/tenant", headers=headers)
    assert own.status_code == 200
    assert own.json()["id"] == session["context"]["tenant_id"]

    # A tenant_id query parameter must never override the token context.
    spoof = await client.get(
        "/api/v1/restaurants?tenant_id=00000000-0000-0000-0000-000000000000",
        headers=headers,
    )
    assert spoof.status_code == 200
    assert len(spoof.json()) == 1
