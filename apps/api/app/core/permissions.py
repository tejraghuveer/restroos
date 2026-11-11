from __future__ import annotations

from enum import StrEnum

from app.core.enums import Role


class Permission(StrEnum):
    TENANT_READ = "tenant:read"
    TENANT_MANAGE = "tenant:manage"
    BRANCH_READ = "branch:read"
    BRANCH_MANAGE = "branch:manage"
    STAFF_READ = "staff:read"
    STAFF_INVITE = "staff:invite"
    STAFF_MANAGE = "staff:manage"
    MENU_READ = "menu:read"
    MENU_MANAGE = "menu:manage"
    ORDER_READ = "order:read"
    ORDER_CREATE = "order:create"
    ORDER_MANAGE = "order:manage"
    ORDER_VOID = "order:void"
    KITCHEN_READ = "kitchen:read"
    KITCHEN_MANAGE = "kitchen:manage"
    INVENTORY_READ = "inventory:read"
    INVENTORY_MANAGE = "inventory:manage"
    ANALYTICS_READ = "analytics:read"
    BILLING_READ = "billing:read"
    BILLING_MANAGE = "billing:manage"


ALL_PERMISSIONS = frozenset(Permission)

_READ_ONLY = {
    Permission.TENANT_READ,
    Permission.BRANCH_READ,
    Permission.MENU_READ,
    Permission.ORDER_READ,
    Permission.KITCHEN_READ,
    Permission.INVENTORY_READ,
    Permission.ANALYTICS_READ,
}

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.OWNER: ALL_PERMISSIONS,
    Role.MANAGER: frozenset(
        {
            Permission.TENANT_READ,
            Permission.BRANCH_READ,
            Permission.STAFF_READ,
            Permission.STAFF_INVITE,
            Permission.STAFF_MANAGE,
            Permission.MENU_READ,
            Permission.MENU_MANAGE,
            Permission.ORDER_READ,
            Permission.ORDER_CREATE,
            Permission.ORDER_MANAGE,
            Permission.ORDER_VOID,
            Permission.KITCHEN_READ,
            Permission.KITCHEN_MANAGE,
            Permission.INVENTORY_READ,
            Permission.INVENTORY_MANAGE,
            Permission.ANALYTICS_READ,
            Permission.BILLING_READ,
        }
    ),
    Role.CASHIER: frozenset(
        {
            Permission.TENANT_READ,
            Permission.BRANCH_READ,
            Permission.MENU_READ,
            Permission.ORDER_READ,
            Permission.ORDER_CREATE,
            Permission.ORDER_MANAGE,
            Permission.BILLING_READ,
        }
    ),
    Role.WAITER: frozenset(
        {
            Permission.TENANT_READ,
            Permission.BRANCH_READ,
            Permission.MENU_READ,
            Permission.ORDER_READ,
            Permission.ORDER_CREATE,
            Permission.KITCHEN_READ,
        }
    ),
    Role.KITCHEN: frozenset(
        {
            Permission.TENANT_READ,
            Permission.BRANCH_READ,
            Permission.MENU_READ,
            Permission.ORDER_READ,
            Permission.KITCHEN_READ,
            Permission.KITCHEN_MANAGE,
        }
    ),
    Role.INVENTORY: frozenset(
        {
            Permission.TENANT_READ,
            Permission.BRANCH_READ,
            Permission.MENU_READ,
            Permission.INVENTORY_READ,
            Permission.INVENTORY_MANAGE,
            Permission.ANALYTICS_READ,
        }
    ),
    Role.VIEWER: frozenset(_READ_ONLY),
}

# Roles a manager may assign or modify. Owners may assign any non-owner role.
MANAGER_ASSIGNABLE_ROLES = frozenset(
    {Role.CASHIER, Role.WAITER, Role.KITCHEN, Role.INVENTORY, Role.VIEWER}
)


def permissions_for(role: Role) -> frozenset[Permission]:
    return ROLE_PERMISSIONS[role]


def can_assign_role(actor_role: Role, target_role: Role) -> bool:
    if target_role is Role.OWNER:
        return False
    if actor_role is Role.OWNER:
        return True
    if actor_role is Role.MANAGER:
        return target_role in MANAGER_ASSIGNABLE_ROLES
    return False
