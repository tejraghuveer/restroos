from __future__ import annotations

import httpx

from tests.helpers import (
    bearer,
    client_for,
    register_owner,
    register_with_invitation,
)


async def test_branch_scoped_manager_is_contained(
    app, client: httpx.AsyncClient
) -> None:
    owner = await register_owner(
        client, email="owner@branch.example", business_name="Branch Group"
    )
    owner_headers = bearer(owner["access_token"])
    tenant_id = owner["context"]["tenant_id"]

    first_branch = owner["context"]["restaurant_id"]
    second = await client.post(
        "/api/v1/restaurants",
        headers=owner_headers,
        json={"name": "Koramangala"},
    )
    assert second.status_code == 201, second.text
    second_branch = second.json()["id"]

    invitation = await client.post(
        "/api/v1/staff/invitations",
        headers=owner_headers,
        json={
            "email": "manager@branch.example",
            "role": "manager",
            "restaurant_id": second_branch,
        },
    )
    assert invitation.status_code == 201, invitation.text
    token = invitation.json()["invite_token"]

    async with client_for(app) as manager_client:
        manager = await register_with_invitation(
            manager_client, email="manager@branch.example", token=token
        )
        assert manager["context"]["tenant_id"] == tenant_id
        assert manager["context"]["restaurant_id"] == second_branch
        assert manager["context"]["role"] == "manager"
        manager_headers = bearer(manager["access_token"])

        # Sees only its own branch.
        branches = await manager_client.get(
            "/api/v1/restaurants", headers=manager_headers
        )
        assert [item["id"] for item in branches.json()] == [second_branch]

        staff = await manager_client.get("/api/v1/staff", headers=manager_headers)
        assert staff.status_code == 200, staff.text
        assert len(staff.json()) == 1
        assert staff.json()[0]["email"] == "manager@branch.example"

        # Tenant-wide operations are denied.
        create_branch = await manager_client.post(
            "/api/v1/restaurants",
            headers=manager_headers,
            json={"name": "Unauthorized Branch"},
        )
        assert create_branch.status_code == 403

        rename_tenant = await manager_client.patch(
            "/api/v1/tenant", headers=manager_headers, json={"name": "Hacked"}
        )
        assert rename_tenant.status_code == 403

        # Cannot invite into another branch.
        cross_branch_invite = await manager_client.post(
            "/api/v1/staff/invitations",
            headers=manager_headers,
            json={
                "email": "someone@branch.example",
                "role": "cashier",
                "restaurant_id": first_branch,
            },
        )
        assert cross_branch_invite.status_code == 403

        # Cannot grant manager/owner privileges.
        manager_invite = await manager_client.post(
            "/api/v1/staff/invitations",
            headers=manager_headers,
            json={
                "email": "peer@branch.example",
                "role": "manager",
                "restaurant_id": second_branch,
            },
        )
        assert manager_invite.status_code == 403

        owner_invite = await manager_client.post(
            "/api/v1/staff/invitations",
            headers=manager_headers,
            json={
                "email": "boss@branch.example",
                "role": "owner",
                "restaurant_id": second_branch,
            },
        )
        assert owner_invite.status_code == 422

        # Cannot escape its branch via the context switcher.
        escape = await manager_client.post(
            "/api/v1/auth/switch-context",
            headers=manager_headers,
            json={"restaurant_id": first_branch},
        )
        assert escape.status_code == 403

        # Nor modify itself.
        own_membership = manager["available_contexts"][0]["membership_id"]
        self_update = await manager_client.patch(
            f"/api/v1/staff/{own_membership}",
            headers=manager_headers,
            json={"role": "owner"},
        )
        assert self_update.status_code == 403


async def test_staff_limit_counts_pending_invitations(make_app) -> None:
    app = await make_app(free_plan_max_staff=2)
    async with client_for(app) as client:
        owner = await register_owner(
            client, email="limit-owner@spice.example", business_name="Tiny Team"
        )
        headers = bearer(owner["access_token"])

        first = await client.post(
            "/api/v1/staff/invitations",
            headers=headers,
            json={"email": "one@spice.example", "role": "cashier"},
        )
        assert first.status_code == 201, first.text

        second = await client.post(
            "/api/v1/staff/invitations",
            headers=headers,
            json={"email": "two@spice.example", "role": "cashier"},
        )
        assert second.status_code == 403
        assert "plan allows 2 staff" in second.json()["detail"]


async def test_existing_user_can_accept_invitation_and_switch_tenant(
    app, client: httpx.AsyncClient
) -> None:
    owner = await register_owner(
        client, email="host@accept.example", business_name="Host Restaurant"
    )
    owner_tenant = owner["context"]["tenant_id"]

    invitation = await client.post(
        "/api/v1/staff/invitations",
        headers=bearer(owner["access_token"]),
        json={"email": "joiner@accept.example", "role": "cashier"},
    )
    assert invitation.status_code == 201, invitation.text
    token = invitation.json()["invite_token"]

    async with client_for(app) as joiner_client:
        joiner = await register_owner(
            joiner_client,
            email="joiner@accept.example",
            business_name="Joiner Own Restaurant",
        )
        assert joiner["context"]["tenant_id"] != owner_tenant

        accepted = await joiner_client.post(
            "/api/v1/staff/invitations/accept",
            headers=bearer(joiner["access_token"]),
            json={"token": token},
        )
        assert accepted.status_code == 200, accepted.text
        body = accepted.json()
        assert body["tenant_id"] == owner_tenant
        assert body["membership"]["role"] == "cashier"

        switched = await joiner_client.post(
            "/api/v1/auth/switch-context",
            headers=bearer(joiner["access_token"]),
            json={"membership_id": body["membership_id"]},
        )
        assert switched.status_code == 200, switched.text
        assert switched.json()["context"]["tenant_id"] == owner_tenant
        assert switched.json()["context"]["tenant_name"] == "Host Restaurant"

        tenant = await joiner_client.get(
            "/api/v1/tenant",
            headers=bearer(switched.json()["access_token"]),
        )
        assert tenant.status_code == 200
        assert tenant.json()["id"] == owner_tenant


async def test_invitation_revocation_and_email_binding(
    app, client: httpx.AsyncClient
) -> None:
    owner = await register_owner(
        client, email="revoke@accept.example", business_name="Revoke Co"
    )
    headers = bearer(owner["access_token"])

    invitation = await client.post(
        "/api/v1/staff/invitations",
        headers=headers,
        json={"email": "intended@accept.example", "role": "waiter"},
    )
    assert invitation.status_code == 201
    invitation_id = invitation.json()["id"]
    token = invitation.json()["invite_token"]

    # A different email cannot consume the token.
    async with client_for(app) as other_client:
        attacker = await register_owner(
            other_client,
            email="attacker@accept.example",
            business_name="Attacker Co",
        )
        denied = await other_client.post(
            "/api/v1/staff/invitations/accept",
            json={"token": token},
            headers=bearer(attacker["access_token"]),
        )
        assert denied.status_code == 403

    revoked = await client.delete(
        f"/api/v1/staff/invitations/{invitation_id}", headers=headers
    )
    assert revoked.status_code == 204

    listed = await client.get("/api/v1/staff/invitations", headers=headers)
    assert listed.status_code == 200
    assert listed.json() == []

    async with client_for(app) as intended_client:
        blocked = await intended_client.post(
            "/api/v1/auth/register",
            json={
                "email": "intended@accept.example",
                "password": "RestroOS-Test-Pass-1",
                "full_name": "Intended User",
                "invitation_token": token,
            },
        )
        assert blocked.status_code == 409
        assert blocked.json()["code"] == "invitation_used"


async def test_removing_staff_revokes_access(
    app, client: httpx.AsyncClient
) -> None:
    owner = await register_owner(
        client, email="remove@accept.example", business_name="Remove Co"
    )
    headers = bearer(owner["access_token"])

    invitation = await client.post(
        "/api/v1/staff/invitations",
        headers=headers,
        json={"email": "leaver@accept.example", "role": "waiter"},
    )
    token = invitation.json()["invite_token"]

    async with client_for(app) as leaver_client:
        leaver = await register_with_invitation(
            leaver_client, email="leaver@accept.example", token=token
        )
        leaver_headers = bearer(leaver["access_token"])
        assert (
            await leaver_client.get("/api/v1/tenant", headers=leaver_headers)
        ).status_code == 200

        staff = await client.get("/api/v1/staff", headers=headers)
        membership_id = next(
            item["id"] for item in staff.json() if item["email"] == "leaver@accept.example"
        )

        removed = await client.delete(
            f"/api/v1/staff/{membership_id}", headers=headers
        )
        assert removed.status_code == 204

        denied = await leaver_client.get("/api/v1/tenant", headers=leaver_headers)
        assert denied.status_code == 403

        refreshed = await leaver_client.post("/api/v1/auth/refresh")
        assert refreshed.status_code == 401
