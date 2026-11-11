from __future__ import annotations

from app.core.enums import Role
from app.core.permissions import (
    ROLE_PERMISSIONS,
    Permission,
    can_assign_role,
    permissions_for,
)


def test_owner_has_every_permission() -> None:
    assert permissions_for(Role.OWNER) == frozenset(Permission)


def test_privileged_permissions_are_not_ambient() -> None:
    assert Permission.TENANT_MANAGE not in ROLE_PERMISSIONS[Role.MANAGER]
    assert Permission.STAFF_MANAGE not in ROLE_PERMISSIONS[Role.WAITER]
    assert Permission.ORDER_VOID not in ROLE_PERMISSIONS[Role.CASHIER]
    assert Permission.BILLING_MANAGE not in ROLE_PERMISSIONS[Role.VIEWER]


def test_role_assignment_rules() -> None:
    assert can_assign_role(Role.OWNER, Role.MANAGER)
    assert can_assign_role(Role.OWNER, Role.CASHIER)
    assert not can_assign_role(Role.OWNER, Role.OWNER)
    assert can_assign_role(Role.MANAGER, Role.CASHIER)
    assert not can_assign_role(Role.MANAGER, Role.MANAGER)
    assert not can_assign_role(Role.MANAGER, Role.OWNER)
    assert not can_assign_role(Role.CASHIER, Role.WAITER)
