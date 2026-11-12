"""Section 8: overlap detection, pure functions only (no DB/web code
crosses this boundary — Section 7's rule for this package). Two things
live here:

1. `resolve_institution` — Section 8.1 Stage 0, free-text -> candidate
   institutions, for future callers (bulk case import, a CPGRAMS feed)
   that don't have a structured institution_id to hand. Nothing in the
   application calls this yet (Phase 3's case registration already uses
   a structured institution picker) — see docs/limitations.md.
2. `score_pair` — Section 8.3 Stage 2, a deterministic, explainable,
   versioned score for a pair of cases already confirmed to be on the
   same institution (that hard gate is Stage 0/1's job, enforced by the
   caller, not here). Every point of score traces to a named signal in
   `reasons`; there is no single opaque number.

Deliberately NOT implemented here (Section 0 rule 2 — no invented data):
"same complainant" (HMAC blind index) and "same documents" (SHA-256)
signals from Section 8.3's table. Phase 3's case model never captures
complainant identity or document uploads, so there is nothing real to
hash — inventing those fields just to light up a signal would be
exactly the kind of fabrication Section 0 forbids. Both are listed as
deferred in docs/limitations.md, not silently dropped.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from rapidfuzz import fuzz

CONFIG_VERSION = "overlap-v1"

OverlapLevel = str  # "info" | "potential" | "high"

_STOPWORDS = {"the", "of", "and", "a", "an", "for"}
_ABBREVIATIONS = {
    "engg": "engineering",
    "inst": "institute",
    "tech": "technology",
    "univ": "university",
    "coll": "college",
    "govt": "government",
}


def normalize_institution_text(text: str) -> str:
    """Section 8.1 step 2: lowercase, strip punctuation/honorifics,
    NFKC-normalize, expand common abbreviations, drop stop-words.
    Transliteration of Devanagari/Tamil script is explicitly out of
    scope here — no verified, licensed transliteration library is wired
    in yet (Section 15 open item #9's embedding-quality question is
    adjacent but distinct); non-Latin input is matched as-is, not
    guessed at."""
    normalized = unicodedata.normalize("NFKC", text).lower()
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    tokens = [t for t in normalized.split() if t]
    expanded = [_ABBREVIATIONS.get(t, t) for t in tokens]
    filtered = [t for t in expanded if t not in _STOPWORDS]
    return " ".join(filtered)


@dataclass(frozen=True)
class InstitutionCandidate:
    institution_id: str
    name: str
    permanent_id: str | None = None
    state: str | None = None
    district: str | None = None


@dataclass(frozen=True)
class ResolutionMatch:
    institution_id: str
    score: float  # 0..100
    reason: str


@dataclass(frozen=True)
class ResolutionResult:
    status: str  # "matched" | "unresolved"
    match: ResolutionMatch | None
    candidates: list[ResolutionMatch]


_PERMANENT_ID_RE = re.compile(r"^1-\d{6,12}$")


def resolve_institution(
    *,
    permanent_id: str | None,
    free_text_name: str | None,
    state: str | None,
    district: str | None,
    candidates: list[InstitutionCandidate],
    t_link: float = 90.0,
    delta: float = 8.0,
) -> ResolutionResult:
    """Section 8.1: never guess silently. An exact Permanent ID match
    always wins outright. Otherwise score every candidate by normalized
    token-set similarity, blocked by state/district when known (a
    candidate outside the known locality is not scored at all — this is
    what keeps the search bounded, not just more accurate), and
    auto-link only when the top score clears `t_link` AND beats the
    runner-up by at least `delta`. Anything short of that is
    `unresolved`: Section 8.1's "shown in an Unresolved institutions
    queue" is the caller's job, this function only refuses to guess."""
    if permanent_id and _PERMANENT_ID_RE.match(permanent_id):
        for c in candidates:
            if c.permanent_id == permanent_id:
                return ResolutionResult(
                    status="matched",
                    match=ResolutionMatch(c.institution_id, 100.0, "exact_permanent_id"),
                    candidates=[],
                )

    if not free_text_name:
        return ResolutionResult(status="unresolved", match=None, candidates=[])

    query = normalize_institution_text(free_text_name)
    blocked = [
        c
        for c in candidates
        if (not state or not c.state or c.state.lower() == state.lower())
        and (not district or not c.district or c.district.lower() == district.lower())
    ]
    scored = sorted(
        (
            ResolutionMatch(c.institution_id, fuzz.token_set_ratio(query, normalize_institution_text(c.name)), "name_similarity")
            for c in blocked
        ),
        key=lambda m: m.score,
        reverse=True,
    )
    if not scored:
        return ResolutionResult(status="unresolved", match=None, candidates=[])

    top = scored[0]
    runner_up_score = scored[1].score if len(scored) > 1 else 0.0
    if top.score >= t_link and (top.score - runner_up_score) >= delta:
        return ResolutionResult(status="matched", match=top, candidates=scored[:5])
    return ResolutionResult(status="unresolved", match=None, candidates=scored[:5])


# --- Stage 2: pair scoring --------------------------------------------

CATEGORY_FAMILIES: tuple[frozenset[str], ...] = (
    frozenset({"student_faculty_stakeholder_complaint", "ragging", "norm_violation"}),
    frozenset({"cpgrams_grievance", "student_faculty_stakeholder_complaint", "miscellaneous"}),
    frozenset({"court_case", "parliament_question", "rti"}),
)


def _categories_compatible(a: str, b: str) -> bool:
    if a == b:
        return True
    return any(a in family and b in family for family in CATEGORY_FAMILIES)


def is_category_compatible(a: str, b: str) -> bool:
    """Check whether two matter types belong to compatible categories."""
    return _categories_compatible(a, b)


def get_compatible_categories(category: str) -> set[str]:
    """Return set of all categories compatible with the given category (including itself)."""
    res = {category}
    for fam in CATEGORY_FAMILIES:
        if category in fam:
            res.update(fam)
    return res




@dataclass(frozen=True)
class OverlapWeights:
    different_bureau: int = 15
    category_compatible: int = 10
    shared_reference: int = 40
    text_similarity_max: int = 30
    time_proximity_max: int = 15


@dataclass(frozen=True)
class OverlapConfig:
    version: str = CONFIG_VERSION
    weights: OverlapWeights = field(default_factory=OverlapWeights)
    time_window_days: int = 90
    threshold_potential: int = 30
    threshold_high: int = 60
    text_similarity_notable: float = 0.55  # 0..1, ratio above which the reason is surfaced


DEFAULT_CONFIG = OverlapConfig()


def get_overlap_config_version(config: OverlapConfig = DEFAULT_CONFIG) -> str:
    """Return the configuration version string."""
    return config.version


def get_default_weights() -> OverlapWeights:
    """Return the default scoring weights configuration."""
    return DEFAULT_CONFIG.weights



@dataclass(frozen=True)
class CaseFacts:
    case_id: str
    bureau_id: str | None
    matter_type: str
    external_refs: tuple[str, ...]
    description: str | None
    received_at: datetime


@dataclass(frozen=True)
class OverlapReason:
    code: str
    text: str


@dataclass(frozen=True)
class OverlapResult:
    score: int
    level: OverlapLevel
    reasons: list[OverlapReason]
    signals: dict[str, Any]
    config_version: str


def score_pair(a: CaseFacts, b: CaseFacts, *, config: OverlapConfig = DEFAULT_CONFIG) -> OverlapResult:
    """Section 8.3: the caller has already confirmed `a` and `b` share an
    institution (Stage 0/1's hard gate) — this only scores how urgently
    that pair needs coordination. Every weighted contribution is also a
    structured, non-sensitive reason string (no raw complaint text is
    ever included in a reason — Section 4.3's T1/T2 boundary still
    applies to what this function's *caller* is allowed to surface on a
    broadly-visible banner, even though the function itself may be fed
    T2 content like `description` to compute the similarity signal)."""
    reasons: list[OverlapReason] = []
    signals: dict[str, Any] = {}
    score = 0
    w = config.weights

    different_bureau = bool(a.bureau_id and b.bureau_id and a.bureau_id != b.bureau_id)
    signals["different_bureau"] = different_bureau
    if different_bureau:
        score += w.different_bureau
        reasons.append(
            OverlapReason("different_bureau", "Different Bureaus/Cells are both handling this institution")
        )

    compatible = _categories_compatible(a.matter_type, b.matter_type)
    signals["category_compatible"] = compatible
    if compatible:
        score += w.category_compatible
        reasons.append(OverlapReason("category_compatible", "The two cases' categories are related"))

    shared_refs = sorted(set(a.external_refs) & set(b.external_refs))
    signals["shared_reference"] = bool(shared_refs)
    if shared_refs:
        score += w.shared_reference
        reasons.append(OverlapReason("shared_reference", "Both cases cite the same reference number"))

    text_sim = 0.0
    if a.description and b.description:
        text_sim = fuzz.token_set_ratio(a.description, b.description) / 100.0
    signals["text_similarity"] = round(text_sim, 3)
    if text_sim > 0:
        score += round(text_sim * w.text_similarity_max)
        if text_sim >= config.text_similarity_notable:
            reasons.append(OverlapReason("text_similarity", "Complaint descriptions are textually similar"))

    days_apart = abs((a.received_at - b.received_at).days)
    signals["days_apart"] = days_apart
    proximity = max(0.0, 1 - days_apart / config.time_window_days) if days_apart <= config.time_window_days else 0.0
    signals["time_proximity"] = round(proximity, 3)
    if proximity > 0:
        score += round(proximity * w.time_proximity_max)
        if proximity >= 0.5:
            reasons.append(OverlapReason("time_proximity", "Cases were received close together in time"))

    score = min(100, score)

    if shared_refs or score >= config.threshold_high:
        level: OverlapLevel = "high"
    elif score >= config.threshold_potential:
        level = "potential"
    else:
        level = "info"

    if not reasons:
        reasons.append(OverlapReason("same_institution", "Both cases concern the same institution"))

    return OverlapResult(score=score, level=level, reasons=reasons, signals=signals, config_version=config.version)


def is_high_overlap(result: OverlapResult) -> bool:
    """Return True if the overlap result is classified at high urgency."""
    return result.level == "high"


def is_potential_overlap(result: OverlapResult) -> bool:
    """Return True if the overlap result is classified as potential overlap."""
    return result.level == "potential"


def is_info_overlap(result: OverlapResult) -> bool:
    """Return True if the overlap result is classified at baseline info urgency."""
    return result.level == "info"



def get_overlap_reason_codes(result: OverlapResult) -> list[str]:
    """Return list of distinct reason codes from the overlap result."""
    return [r.code for r in result.reasons]


def has_overlap_reason(result: OverlapResult, code: str) -> bool:
    """Return True if the overlap result contains a specific reason code."""
    return any(r.code == code for r in result.reasons)


def get_known_abbreviations() -> dict[str, str]:
    """Return a copy of the canonical abbreviation expansion dictionary."""
    return dict(_ABBREVIATIONS)


def filter_candidates_by_min_score(
    candidates: list[ResolutionMatch], min_score: float
) -> list[ResolutionMatch]:
    """Filter candidate matches to those that meet or exceed min_score."""
    return [c for c in candidates if c.score >= min_score]


def is_resolution_matched(result: ResolutionResult) -> bool:
    """Return True if the resolution result successfully matched an institution."""
    return result.status == "matched" and result.match is not None


def get_top_candidate(result: ResolutionResult) -> ResolutionMatch | None:
    """Return the top candidate resolution match if available."""
    if result.match:
        return result.match
    return result.candidates[0] if result.candidates else None


def tokenize_normalized_text(text: str) -> list[str]:
    """Tokenize normalized text into cleaned lowercase tokens."""
    normalized = unicodedata.normalize("NFKC", text).lower()
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    return [t for t in normalized.split() if t]


def calculate_token_jaccard(tokens_a: list[str], tokens_b: list[str]) -> float:
    """Calculate the Jaccard similarity coefficient between two token sequences."""
    set_a = set(tokens_a)
    set_b = set(tokens_b)
    if not set_a and not set_b:
        return 1.0
    union = set_a | set_b
    if not union:
        return 0.0
    return round(len(set_a & set_b) / len(union), 4)


def format_overlap_summary(result: OverlapResult) -> str:
    """Format a human-readable non-sensitive summary of the overlap result."""
    reasons_summary = "; ".join(r.text for r in result.reasons)
    return f"{result.level.upper()} ({result.score}/100): {reasons_summary}"


def calculate_time_proximity_score(
    received_a: datetime, received_b: datetime, window_days: int = 90
) -> float:
    """Calculate normalized time proximity score between two case receipt dates (0..1)."""
    days_apart = abs((received_a - received_b).days)
    if days_apart > window_days:
        return 0.0
    return round(max(0.0, 1.0 - (days_apart / window_days)), 3)










