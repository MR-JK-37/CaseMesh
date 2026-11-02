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
