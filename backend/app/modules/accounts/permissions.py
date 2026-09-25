"""Roles and what they may do. Checked in the service layer (see accounts.service.require_permission)."""

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    MANAGER = "manager"
    BILLING = "billing"  # counter staff: sell, collect money
    STOCK = "stock"  # godown staff: receive, transfer, wastage
    VIEWER = "viewer"


class Perm(StrEnum):
    LOCATIONS_VIEW = "locations.view"
    LOCATIONS_MANAGE = "locations.manage"
    AUDIT_VIEW = "audit.view"
    STAFF_MANAGE = "staff.manage"


_ALL = frozenset(Perm)

ROLE_PERMISSIONS: dict[Role, frozenset[Perm]] = {
    Role.OWNER: _ALL,
    Role.MANAGER: _ALL - {Perm.STAFF_MANAGE},
    Role.BILLING: frozenset({Perm.LOCATIONS_VIEW}),
    Role.STOCK: frozenset({Perm.LOCATIONS_VIEW}),
    Role.VIEWER: frozenset({Perm.LOCATIONS_VIEW}),
}


def role_has(role: str, perm: Perm) -> bool:
    try:
        return perm in ROLE_PERMISSIONS[Role(role)]
    except ValueError:
        return False
