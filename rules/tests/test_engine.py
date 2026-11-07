from rules.engine import run_rules
from rules.registry import DEFAULT_RULES
from rules.types import Flag, RuleContext, Severity


class _AlwaysFlags:
    code = "ALWAYS_FLAGS"
    version = "0.0.1"

    def evaluate(self, ctx: RuleContext) -> Flag | None:
        return Flag(
            code=self.code,
            severity=Severity.REVIEW,
            reason="test rule always flags",
            evidence={"record": ctx.record},
            rule_version=self.version,
        )


class _NeverFlags:
    code = "NEVER_FLAGS"
    version = "0.0.1"

    def evaluate(self, ctx: RuleContext) -> Flag | None:
        return None


def test_default_rules_is_empty_pending_phase_4_5():
    # Real, current state: the AICTE overlap (Phase 4) and SLA (Phase 5)
    # rules have not been written yet — this is not a stub left by
    # accident, it is the honest starting point after removing the
    # out-of-domain APAAR catalog (docs/decision-log.md).
    assert DEFAULT_RULES == []


def test_run_rules_collects_every_flag_and_never_short_circuits():
    ctx = RuleContext(record={"id": "x"})
    flags = run_rules(ctx, [_AlwaysFlags(), _NeverFlags(), _AlwaysFlags()])
    assert len(flags) == 2
    assert all(f.code == "ALWAYS_FLAGS" for f in flags)


def test_run_rules_with_no_rules_returns_no_flags():
    ctx = RuleContext(record={})
    assert run_rules(ctx, []) == []


def test_filter_flags_by_severity():
    from rules.engine import filter_flags_by_severity

    ctx = RuleContext(record={"id": "x"})
    flags = run_rules(ctx, [_AlwaysFlags()])
    reviews = filter_flags_by_severity(flags, "review")
    errors = filter_flags_by_severity(flags, "error")

    assert len(reviews) == 1
    assert len(errors) == 0


def test_has_flag_code():
    from rules.engine import has_flag_code

    ctx = RuleContext(record={"id": "x"})
    flags = run_rules(ctx, [_AlwaysFlags()])

    assert has_flag_code(flags, "ALWAYS_FLAGS")
    assert not has_flag_code(flags, "NON_EXISTENT")
