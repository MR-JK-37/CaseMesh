from rules.types import Rule

# Empty pending Phase 4 (overlap detection, Section 8) and Phase 5 (SLA
# engine, Section 7) — the APAAR-era catalog (duplicate/invalid-ID rules
# for a student registry) was removed as out-of-domain for AICTE case
# monitoring (docs/decision-log.md). The engine/types/registry shape
# itself (run_rules never short-circuits, returns all flags) is kept.
DEFAULT_RULES: list[Rule] = []


def get_default_rules() -> list[Rule]:
    """Return a shallow copy of the active default rule list."""
    return list(DEFAULT_RULES)
