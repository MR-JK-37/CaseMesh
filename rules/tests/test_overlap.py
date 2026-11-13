import datetime as dt

from rules.overlap import (
    CaseFacts,
    InstitutionCandidate,
    ResolutionMatch,
    calculate_time_proximity_score,
    calculate_token_jaccard,
    create_case_facts,
    filter_candidates_by_min_score,
    format_overlap_summary,
    get_compatible_categories,
    get_default_weights,
    get_known_abbreviations,
    get_overlap_config_version,
    get_overlap_reason_codes,
    get_shared_references,
    get_top_candidate,
    has_overlap_reason,
    is_category_compatible,
    is_cross_bureau_pair,
    is_high_overlap,
    is_info_overlap,
    is_potential_overlap,
    is_resolution_matched,
    normalize_institution_text,
    resolve_institution,
    score_pair,
    tokenize_normalized_text,
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


def test_overlap_level_predicates():
    high_case = score_pair(_case("c1", "bureau-rb", refs=["LTR/2026/001"]), _case("c2", "bureau-pgrc", refs=["LTR/2026/001"]))
    assert is_high_overlap(high_case) is True
    assert is_potential_overlap(high_case) is False
    assert is_info_overlap(high_case) is False

    info_case = score_pair(_case("c3", "bureau-rb", days_ago=200), _case("c4", "bureau-rb", days_ago=0))
    assert is_high_overlap(info_case) is False
    assert is_potential_overlap(info_case) is False
    assert is_info_overlap(info_case) is True


def test_format_overlap_summary():
    high_case = score_pair(_case("c1", "bureau-rb", refs=["LTR/2026/001"]), _case("c2", "bureau-pgrc", refs=["LTR/2026/001"]))
    summary = format_overlap_summary(high_case)
    assert "HIGH" in summary
    assert "Both cases cite the same reference number" in summary


def test_category_compatibility_helpers():
    assert is_category_compatible("court_case", "court_case") is True
    assert is_category_compatible("court_case", "parliament_question") is True
    compat = get_compatible_categories("court_case")
    assert "parliament_question" in compat
    assert "rti" in compat


def test_overlap_config_and_weights_helpers():
    assert get_overlap_config_version() == "overlap-v1"
    weights = get_default_weights()
    assert weights.shared_reference == 40
    assert weights.different_bureau == 15


def test_time_proximity_and_shared_references_helpers():
    t1 = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    t2 = dt.datetime(2026, 1, 10, tzinfo=dt.UTC)
    t3 = dt.datetime(2026, 6, 1, tzinfo=dt.UTC)

    prox = calculate_time_proximity_score(t1, t2, window_days=90)
    assert 0.8 < prox < 1.0
    assert calculate_time_proximity_score(t1, t3, window_days=90) == 0.0

    shared = get_shared_references(["REF-1", "REF-2"], ["REF-2", "REF-3"])
    assert shared == ["REF-2"]
    assert get_shared_references([], ["REF-1"]) == []


def test_create_case_facts_factory():
    facts = create_case_facts("case-100", bureau_id="b-1", external_refs=["REF-100"])
    assert facts.case_id == "case-100"
    assert facts.bureau_id == "b-1"
    assert facts.external_refs == ("REF-100",)
    assert facts.matter_type == "student_faculty_stakeholder_complaint"







def test_overlap_reason_inspection_helpers():
    pair = score_pair(_case("c1", "bureau-rb", refs=["REF-123"]), _case("c2", "bureau-pgrc", refs=["REF-123"]))
    codes = get_overlap_reason_codes(pair)
    assert "shared_reference" in codes
    assert has_overlap_reason(pair, "shared_reference") is True
    assert has_overlap_reason(pair, "non_existent_code") is False


def test_get_known_abbreviations():
    abbrevs = get_known_abbreviations()
    assert abbrevs["engg"] == "engineering"
    assert abbrevs["inst"] == "institute"
    assert abbrevs["coll"] == "college"


def test_filter_candidates_by_min_score():
    candidates = [
        ResolutionMatch("inst-1", 95.0, "name_similarity"),
        ResolutionMatch("inst-2", 80.0, "name_similarity"),
        ResolutionMatch("inst-3", 60.0, "name_similarity"),
    ]
    filtered = filter_candidates_by_min_score(candidates, 80.0)
    assert len(filtered) == 2
    assert [c.institution_id for c in filtered] == ["inst-1", "inst-2"]


def test_is_resolution_matched_predicate():
    candidates = [InstitutionCandidate("inst-1", "Govt Engg College", permanent_id="1-800000001")]
    matched = resolve_institution(
        permanent_id="1-800000001", free_text_name=None, state=None, district=None, candidates=candidates
    )
    assert is_resolution_matched(matched) is True

    unresolved = resolve_institution(
        permanent_id=None, free_text_name="Unknown", state=None, district=None, candidates=[]
    )
    assert is_resolution_matched(unresolved) is False


def test_get_top_candidate_helper():
    candidates = [
        InstitutionCandidate("inst-1", "Sandbox Institute of Technology"),
        InstitutionCandidate("inst-2", "Completely Different Polytechnic"),
    ]
    matched = resolve_institution(
        permanent_id=None,
        free_text_name="Sandbox Institute of Technology",
        state=None,
        district=None,
        candidates=candidates,
    )
    top = get_top_candidate(matched)
    assert top is not None
    assert top.institution_id == "inst-1"


def test_tokenize_normalized_text():
    tokens = tokenize_normalized_text("Govt. Engineering College, Pune (MH)")
    assert "govt" in tokens
    assert "engineering" in tokens
    assert "pune" in tokens


def test_calculate_token_jaccard():
    a = ["engineering", "college", "pune"]
    b = ["engineering", "technology", "pune"]
    sim = calculate_token_jaccard(a, b)
    assert 0.0 < sim < 1.0
    assert calculate_token_jaccard([], []) == 1.0
    assert calculate_token_jaccard(["a"], ["a"]) == 1.0


def test_is_cross_bureau_pair():
    c1 = _case("c1", "bureau-approval")
    c2 = _case("c2", "bureau-grievance")
    c3 = _case("c3", "bureau-approval")
    c_none = _case("c4", None)

    assert is_cross_bureau_pair(c1, c2) is True
    assert is_cross_bureau_pair(c1, c3) is False
    assert is_cross_bureau_pair(c1, c_none) is False
    assert is_cross_bureau_pair(c_none, c_none) is False








