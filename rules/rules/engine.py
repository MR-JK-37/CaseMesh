from rules.types import Flag, Rule, RuleContext


def run_rules(ctx: RuleContext, rule_set: list[Rule]) -> list[Flag]:
    """Runs every rule and returns all flags raised — never short-circuits,
    per Section 5/M5 ('returns all flags')."""
    flags: list[Flag] = []
    for rule in rule_set:
        flag = rule.evaluate(ctx)
        if flag is not None:
            flags.append(flag)
    return flags


def filter_flags_by_severity(flags: list[Flag], severity_code: str) -> list[Flag]:
    """Filter evaluated flags by severity level."""
    return [f for f in flags if f.severity.value == severity_code]


def has_flag_code(flags: list[Flag], code: str) -> bool:
    """Check if any flag with the given code is present in the evaluated flags."""
    return any(f.code == code for f in flags)


def get_flag_codes(flags: list[Flag]) -> list[str]:
    """Return all unique flag codes raised from evaluation."""
    return sorted({f.code for f in flags})
