"""Section 4.2: a generated test over every (role x action) pair this
phase defines. Not DB-backed — pure unit test over authz/policy.py's
data, so it runs everywhere including CI without Postgres."""

from app.authz.policy import ROLE_PERMISSIONS, ROLES, Scope, can

ALL_ACTIONS = sorted({action for perms in ROLE_PERMISSIONS.values() for action in perms})


def test_every_role_in_the_matrix_is_one_of_the_ten_defined_roles():
    assert set(ROLE_PERMISSIONS) <= set(ROLES)


def test_system_role_has_no_interactive_permissions():
    """Section 4.1: `system` is a machine identity with no interactive
    login — it must not accidentally gain a permission meant for a human
    role."""
    assert ROLE_PERMISSIONS["system"] == {}


def test_deny_by_default_for_unknown_role():
    assert can("not_a_real_role", "user:list") is False


def test_deny_by_default_for_unknown_action():
    assert can("super_admin", "not_a_real_action") is False


def test_every_role_x_action_pair_has_an_explicit_deterministic_result():
    """The actual generated matrix: every role crossed with every action
    that exists anywhere in the matrix must resolve to a boolean without
    raising, and the result must be stable (same call, same answer)."""
    for role in ROLES:
        for action in ALL_ACTIONS:
            first = can(role, action)
            second = can(role, action)
            assert first is second
            assert isinstance(first, bool)


def test_own_bureau_scope_requires_actual_overlap():
    assert (
        can(
            "bureau_head",
            "user:list",
            actor_bureau_ids=frozenset({"b1"}),
            resource_bureau_ids=frozenset({"b1"}),
        )
        is True
    )
    assert (
        can(
            "bureau_head",
            "user:list",
            actor_bureau_ids=frozenset({"b1"}),
            resource_bureau_ids=frozenset({"b2"}),
        )
        is False
    )


def test_self_scope_requires_is_own_record_true():
    assert can("case_officer", "session:list_own", is_own_record=True) is True
    assert can("case_officer", "session:list_own", is_own_record=False) is False


def test_super_admin_has_broader_phase1_access_than_case_officer():
    """Not a full lattice-order test (Scope isn't strictly ordered across
    bureau/region/self), just the concrete Phase 1 fact: super_admin can
    list all users, case_officer cannot list any."""
    assert can("super_admin", "user:list") is True
    assert can("case_officer", "user:list") is False


def test_all_scope_actions_never_require_bureau_or_region_overlap():
    for role, perms in ROLE_PERMISSIONS.items():
        for action, scope in perms.items():
            if scope is Scope.ALL:
                assert can(role, action) is True, f"{role}:{action} should be unconditionally allowed"
