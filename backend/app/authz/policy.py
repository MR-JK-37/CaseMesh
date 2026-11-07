"""Single authorization choke point (Section 4.2 layer 1): every endpoint
calls `can()` here, never an inline `if role == "..."` check. Deny by
default — an action/role pair absent from ROLE_PERMISSIONS is denied.

This is Phase 1's slice of the full matrix: identity/RBAC actions only
(auth, users, sessions, TOTP, audit, reference-data read). Case/overlap/
report actions are added as their modules are built (Phase 2 onward) —
the generated permission-matrix test (tests/test_authz_matrix.py) only
iterates the actions that exist right now, honestly, rather than
asserting coverage of endpoints that don't exist yet.
"""

from enum import Enum

ROLES = (
    "super_admin",
    "competent_authority",
    "senior_management",
    "bureau_head",
    "case_officer",
    "regional_officer",
    "nodal_pg_officer",
    "registry_operator",
    "auditor",
    "system",
)


class Scope(str, Enum):
    ALL = "all"  # no bureau/region restriction
    OWN_BUREAU = "own_bureau"  # actor and resource share at least one bureau
    OWN_REGION = "own_region"  # actor and resource share at least one region
    SELF = "self"  # the resource must be the actor's own record


# Section 4.1's per-role core permissions, Phase 1 slice. `*` means every
# action is allowed at Scope.ALL (super_admin's "system" scope — note
# Section 4.1 also says super_admin has NO case-content access by
# default; that restriction applies once case content exists, Phase 3+,
# and is enforced there, not here).
ROLE_PERMISSIONS: dict[str, dict[str, Scope]] = {
    "super_admin": {
        "user:list": Scope.ALL,
        "user:read": Scope.ALL,
        "user:create": Scope.ALL,
        "user:update_role": Scope.ALL,
        "user:assign": Scope.ALL,
        "user:deactivate": Scope.ALL,
        "bureau:list": Scope.ALL,
        "bureau:manage": Scope.ALL,
        "region:list": Scope.ALL,
        "region:manage": Scope.ALL,
        "audit:read": Scope.ALL,
        "session:list_own": Scope.SELF,
        "session:revoke_own": Scope.SELF,
        "totp:enroll_self": Scope.SELF,
        "view:manage": Scope.SELF,
        "institution:list": Scope.ALL,
        "institution:read": Scope.ALL,
        "institution:import": Scope.ALL,
        "institution:verify": Scope.ALL,
        "institution:alias_manage": Scope.ALL,
        "case:list": Scope.ALL,
        "overlap:list": Scope.ALL,
        "alert:list": Scope.ALL,
        "alert:ack": Scope.ALL,
    },
    "competent_authority": {
        "institution:list": Scope.ALL,
        "institution:read": Scope.ALL,
        "user:list": Scope.ALL,
        "user:read": Scope.ALL,
        "bureau:list": Scope.ALL,
        "region:list": Scope.ALL,
        "audit:read": Scope.ALL,
        "session:list_own": Scope.SELF,
        "session:revoke_own": Scope.SELF,
        "totp:enroll_self": Scope.SELF,
        "view:manage": Scope.SELF,
        "case:list": Scope.ALL,
        "case:read_events": Scope.ALL,
        "case:reopen": Scope.ALL,
        "overlap:list": Scope.ALL,
        "alert:list": Scope.ALL,
        "alert:ack": Scope.ALL,
        "overlap:confirm": Scope.ALL,
        "overlap:dismiss": Scope.ALL,
        "overlap:coordinate": Scope.ALL,
        "overlap:decide": Scope.ALL,
    },
    "senior_management": {
        "institution:list": Scope.ALL,
        "institution:read": Scope.ALL,
        "user:list": Scope.ALL,
        "bureau:list": Scope.ALL,
        "region:list": Scope.ALL,
        "session:list_own": Scope.SELF,
        "session:revoke_own": Scope.SELF,
        "totp:enroll_self": Scope.SELF,
        "view:manage": Scope.SELF,
        "case:list": Scope.ALL,
        "overlap:list": Scope.ALL,
        "alert:list": Scope.ALL,
    },
    "bureau_head": {
        "institution:list": Scope.ALL,
        "institution:read": Scope.ALL,
        "user:list": Scope.OWN_BUREAU,
        "user:read": Scope.OWN_BUREAU,
        "bureau:list": Scope.ALL,
        "region:list": Scope.ALL,
        "session:list_own": Scope.SELF,
        "session:revoke_own": Scope.SELF,
        "totp:enroll_self": Scope.SELF,
        "view:manage": Scope.SELF,
        "case:list": Scope.ALL,
        "case:register": Scope.OWN_BUREAU,
        "case:read_events": Scope.OWN_BUREAU,
        "case:assign": Scope.OWN_BUREAU,
        "case:remark": Scope.OWN_BUREAU,
        "case:transfer_propose": Scope.OWN_BUREAU,
        "case:transfer_resolve": Scope.OWN_BUREAU,
        "case:escalate": Scope.OWN_BUREAU,
        "case:dispose": Scope.OWN_BUREAU,
        "case:reopen": Scope.OWN_BUREAU,
        "overlap:list": Scope.ALL,
        "alert:list": Scope.ALL,
        "alert:ack": Scope.OWN_BUREAU,
        "overlap:confirm": Scope.OWN_BUREAU,
        "overlap:dismiss": Scope.OWN_BUREAU,
        "overlap:coordinate": Scope.OWN_BUREAU,
        "overlap:decide": Scope.OWN_BUREAU,
    },
    "case_officer": {
        "institution:list": Scope.ALL,
        "institution:read": Scope.ALL,
        "bureau:list": Scope.ALL,
        "region:list": Scope.ALL,
        "session:list_own": Scope.SELF,
        "session:revoke_own": Scope.SELF,
        "totp:enroll_self": Scope.SELF,
        "view:manage": Scope.SELF,
        "case:list": Scope.ALL,
        "case:register": Scope.OWN_BUREAU,
        "case:read_events": Scope.OWN_BUREAU,
        "case:remark": Scope.OWN_BUREAU,
        "case:transfer_propose": Scope.OWN_BUREAU,
        "case:escalate": Scope.OWN_BUREAU,
        "overlap:list": Scope.ALL,
        "alert:list": Scope.ALL,
        "overlap:coordinate": Scope.OWN_BUREAU,
    },
    "regional_officer": {
        "institution:list": Scope.ALL,
        "institution:read": Scope.ALL,
        "bureau:list": Scope.ALL,
        "region:list": Scope.ALL,
        "session:list_own": Scope.SELF,
        "session:revoke_own": Scope.SELF,
        "totp:enroll_self": Scope.SELF,
        "view:manage": Scope.SELF,
        "case:list": Scope.ALL,
        "overlap:list": Scope.ALL,
        "alert:list": Scope.ALL,
    },
    "nodal_pg_officer": {
        "institution:list": Scope.ALL,
        "institution:read": Scope.ALL,
        "user:list": Scope.ALL,
        "bureau:list": Scope.ALL,
        "region:list": Scope.ALL,
        "session:list_own": Scope.SELF,
        "session:revoke_own": Scope.SELF,
        "totp:enroll_self": Scope.SELF,
        "view:manage": Scope.SELF,
        "case:list": Scope.ALL,
        "overlap:list": Scope.ALL,
        "alert:list": Scope.ALL,
    },
    "registry_operator": {
        "institution:list": Scope.ALL,
        "institution:read": Scope.ALL,
        "bureau:list": Scope.ALL,
        "region:list": Scope.ALL,
        "session:list_own": Scope.SELF,
        "session:revoke_own": Scope.SELF,
        "totp:enroll_self": Scope.SELF,
        "view:manage": Scope.SELF,
        "case:list": Scope.ALL,
        "case:register": Scope.ALL,
        "overlap:list": Scope.ALL,
        "alert:list": Scope.ALL,
    },
    "auditor": {
        "institution:list": Scope.ALL,
        "institution:read": Scope.ALL,
        "user:list": Scope.ALL,
        "audit:read": Scope.ALL,
        "bureau:list": Scope.ALL,
        "region:list": Scope.ALL,
        "session:list_own": Scope.SELF,
        "session:revoke_own": Scope.SELF,
        "totp:enroll_self": Scope.SELF,
        "view:manage": Scope.SELF,
        "case:list": Scope.ALL,
        "overlap:list": Scope.ALL,
        "alert:list": Scope.ALL,
    },
    "system": {},
}


def can(
    role: str,
    action: str,
    *,
    actor_bureau_ids: frozenset[str] = frozenset(),
    resource_bureau_ids: frozenset[str] = frozenset(),
    actor_region_ids: frozenset[str] = frozenset(),
    resource_region_ids: frozenset[str] = frozenset(),
    is_own_record: bool = False,
) -> bool:
    perms = ROLE_PERMISSIONS.get(role)
    if not perms:
        return False
    scope = perms.get(action)
    if scope is None:
        return False
    if scope is Scope.ALL:
        return True
    if scope is Scope.OWN_BUREAU:
        return bool(actor_bureau_ids & resource_bureau_ids)
    if scope is Scope.OWN_REGION:
        return bool(actor_region_ids & resource_region_ids)
    if scope is Scope.SELF:
        return is_own_record
    return False


def get_allowed_actions(role: str) -> list[str]:
    """Return all action keys allowed for a given role."""
    return list(ROLE_PERMISSIONS.get(role, {}).keys())


def has_permission(role: str, action: str) -> bool:
    """Check if a role has permission for an action regardless of scope."""
    return action in ROLE_PERMISSIONS.get(role, {})


def get_permission_scope(role: str, action: str) -> Scope | None:
    """Return the granted Scope for a role and action, or None if denied."""
    return ROLE_PERMISSIONS.get(role, {}).get(action)
