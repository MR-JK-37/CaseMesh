import datetime as dt

from rules.overlap import (
    CaseFacts,
    InstitutionCandidate,
    normalize_institution_text,
    resolve_institution,
    score_pair,
)

NOW = dt.datetime(2026, 10, 29, tzinfo=dt.UTC)


def _case(case_id, bureau_id, matter_type="student_faculty_stakeholder_complaint", refs=(), desc=None, days_ago=0):
    return CaseFacts(
        case_id=case_id,
        bureau_id=bureau_id,
        matter_type=matter_type,
        external_refs=tuple(refs),
        description=desc,
        received_at=NOW - dt.timedelta(days=days_ago),
    )


def test_normalize_expands_abbreviations_and_drops_stopwords():
    assert normalize_institution_text("The Govt Engg College of Pune") == "government engineering college pune"


def test_same_institution_different_wording_is_flagged_r4():
    """R4: 'complaints on the same institution... even if descriptions or
    references differ' — different free text, no shared reference, still
    produces a non-info-floor result once bureaus differ and categories
    are related."""
    a = _case("a", "bureau-rb", desc="Student alleges faculty misconduct during practicals")
    b = _case("b", "bureau-pgrc", desc="Complaint about professor behaviour in lab sessions", days_ago=2)
    result = score_pair(a, b)
    assert result.level in ("potential", "high")
    assert any(r.code == "different_bureau" for r in result.reasons)


def test_different_institution_pairs_are_never_scored_a_negative():
    """Stage 0/1's hard gate means this function is never even called for
    a cross-institution pair — this test documents that the gate lives
    in the caller (app/services/overlap.py's candidate fetch), not here,
    by asserting the pure function has no institution_id parameter at
    all to accidentally bypass."""
    import inspect

    sig = inspect.signature(score_pair)
    assert "institution_id" not in sig.parameters


def test_shared_reference_forces_high_regardless_of_score():
    a = _case("a", "bureau-rb", refs=["LTR/2026/001"], days_ago=400)
    b = _case("b", "bureau-pgrc", refs=["LTR/2026/001"], days_ago=0)
    result = score_pair(a, b)
    assert result.level == "high"
    assert any(r.code == "shared_reference" for r in result.reasons)


def test_same_bureau_same_category_no_shared_evidence_stays_info():
    a = _case("a", "bureau-rb", days_ago=200)
    b = _case("b", "bureau-rb", days_ago=0)
    result = score_pair(a, b)
    assert result.level == "info"
    assert result.signals["different_bureau"] is False


def test_time_proximity_decays_to_zero_outside_window():
    a = _case("a", "bureau-rb", days_ago=0)
    b = _case("b", "bureau-pgrc", days_ago=365)
    result = score_pair(a, b)
    assert result.signals["time_proximity"] == 0.0


def test_result_is_versioned_and_json_safe_reasons():
    a = _case("a", "bureau-rb")
    b = _case("b", "bureau-pgrc", days_ago=1)
    result = score_pair(a, b)
    assert result.config_version == "overlap-v1"
    assert all(isinstance(r.text, str) for r in result.reasons)


def test_resolve_institution_exact_permanent_id_wins_outright():
    candidates = [InstitutionCandidate("inst-1", "Example College", permanent_id="1-800000001")]
    result = resolve_institution(
        permanent_id="1-800000001", free_text_name=None, state=None, district=None, candidates=candidates
    )
    assert result.status == "matched"
    assert result.match.institution_id == "inst-1"
    assert result.match.reason == "exact_permanent_id"


def test_resolve_institution_clear_winner_matches():
    candidates = [
        InstitutionCandidate("inst-1", "Sandbox Institute of Technology", state="TN"),
        InstitutionCandidate("inst-2", "Completely Different Polytechnic", state="TN"),
    ]
    result = resolve_institution(
        permanent_id=None,
        free_text_name="Sandbox Inst of Tech",
        state="TN",
        district=None,
        candidates=candidates,
    )
    assert result.status == "matched"
    assert result.match.institution_id == "inst-1"


def test_resolve_institution_never_guesses_when_ambiguous():
    """R4/Section 8.1: two near-identical names, neither clears the
    margin — must come back unresolved, not pick one."""
    candidates = [
        InstitutionCandidate("inst-1", "Sandbox Institute of Technology"),
        InstitutionCandidate("inst-2", "Sandbox Institute of Technologies"),
    ]
    result = resolve_institution(
        permanent_id=None, free_text_name="Sandbox Institute of Technology", state=None, district=None, candidates=candidates
    )
    assert result.status == "unresolved"
    assert result.match is None
    assert len(result.candidates) == 2


def test_resolve_institution_blocks_by_state_before_scoring():
    candidates = [
        InstitutionCandidate("inst-1", "Example Institute of Technology", state="TN"),
        InstitutionCandidate("inst-2", "Example Institute of Technology", state="KA"),
    ]
    result = resolve_institution(
        permanent_id=None, free_text_name="Example Institute of Technology", state="KA", district=None, candidates=candidates
    )
    assert result.status == "matched"
    assert result.match.institution_id == "inst-2"


def test_resolve_institution_no_candidates_is_unresolved_not_an_error():
    result = resolve_institution(permanent_id=None, free_text_name="Nobody College", state=None, district=None, candidates=[])
    assert result.status == "unresolved"
