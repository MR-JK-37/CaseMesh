from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class Severity(str, Enum):
    INFO = "info"
    REVIEW = "review"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True)
class Flag:
    code: str
    severity: Severity
    reason: str
    evidence: dict[str, Any]
    rule_version: str


@dataclass(frozen=True)
class RuleContext:
    """Everything a rule needs, passed in by the caller. No DB/web handles
    cross this boundary (Section 7: 'pure package with no web/DB code')."""

    record: dict[str, Any]
    config: dict[str, Any] = field(default_factory=dict)


class Rule(Protocol):
    code: str
    version: str

    def evaluate(self, ctx: RuleContext) -> Flag | None: ...
