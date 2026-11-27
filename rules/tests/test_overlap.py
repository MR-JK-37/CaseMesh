import datetime as dt

from rules.overlap import (
    CaseFacts,
    InstitutionCandidate,
    ResolutionMatch,
    calculate_days_between_cases,
    calculate_time_proximity_score,
    calculate_token_jaccard,
    count_cases_by_matter_type,
    count_cases_with_description,
    count_candidates_with_permanent_id,
    count_shared_references,
    create_case_facts,
    filter_candidates_by_min_score,
    filter_candidates_by_district,
    filter_candidates_by_state,
    filter_cases_by_bureau,
    filter_cases_by_date_range,
    filter_cases_by_matter_type,
    filter_cases_with_external_refs,
    filter_matches_by_min_score,
    format_case_reference_summary,
    format_overlap_summary,
    get_all_category_names,
    get_average_resolution_score,
    get_candidate_by_id,
    get_candidate_by_permanent_id,
    get_candidate_ids,
    get_candidate_institution_names,
    get_candidate_permanent_ids,
    get_case_age_days,
    get_compatible_categories,
    get_default_weights,
    get_external_references_count,
    get_resolution_score_range,
    get_highest_scoring_candidate,
    get_known_abbreviations,
    get_matter_type,
    get_overlap_config_version,
    get_overlap_reason_codes,
    get_shared_references,
    get_top_candidate,
    get_top_candidate_score,
    get_top_n_candidates,
    get_unique_matter_types,
    has_any_overlap_reasons,
    has_any_shared_external_reference,
    has_case_id,
    has_description,
    has_distinct_bureau_pair,
    has_duplicate_case_ids,
    has_matching_district_and_state,
    has_matching_permanent_id,
    has_matching_receipt_year,
    has_overlap_reason,
    is_category_compatible,
    is_case_within_window,
    is_cross_bureau_pair,
    is_cross_state_institution_pair,
    is_empty_external_references,
    is_empty_or_whitespace,
    is_exact_resolution_match,
    is_high_overlap,
    is_info_overlap,
    is_institution_candidate_active,
    is_potential_overlap,
    is_recent_case,
    is_resolution_matched,
    is_same_bureau,
    is_same_receipt_month,
    is_valid_matter_category,
    is_valid_resolution_status,
    normalize_external_reference,
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


def test_get_all_category_names():
    names = get_all_category_names()
    assert isinstance(names, tuple)
    assert "court_case" in names
    assert "ragging" in names
    assert "norm_violation" in names
    assert "student_faculty_stakeholder_complaint" in names
    # Must be sorted alphabetically
    assert list(names) == sorted(names)


def test_normalize_external_reference():
    assert normalize_external_reference("  aicte/2026/001  ") == "AICTE/2026/001"
    assert normalize_external_reference("cpgrams-998877") == "CPGRAMS-998877"
    assert normalize_external_reference("") == ""


def test_has_matching_permanent_id():
    c1 = InstitutionCandidate("i1", "Inst 1", permanent_id="1-1234567")
    c2 = InstitutionCandidate("i2", "Inst 2", permanent_id=" 1-1234567 ")
    c3 = InstitutionCandidate("i3", "Inst 3", permanent_id="1-9999999")
    c_none = InstitutionCandidate("i4", "Inst 4", permanent_id=None)

    assert has_matching_permanent_id(c1, c2) is True
    assert has_matching_permanent_id(c1, c3) is False
    assert has_matching_permanent_id(c1, c_none) is False
    assert has_matching_permanent_id(c_none, c_none) is False


def test_get_top_n_candidates():
    candidates = [
        InstitutionCandidate("inst-1", "Sandbox Institute of Technology"),
        InstitutionCandidate("inst-2", "State Engineering College"),
        InstitutionCandidate("inst-3", "Polytechnic Institute"),
    ]
    matched = resolve_institution(
        permanent_id=None,
        free_text_name="Engineering College",
        state=None,
        district=None,
        candidates=candidates,
    )
    top2 = get_top_n_candidates(matched, n=2)
    assert len(top2) <= 2
    assert isinstance(top2, list)


def test_has_matching_district_and_state():
    c1 = InstitutionCandidate("i1", "Inst 1", state="Maharashtra", district="Pune")
    c2 = InstitutionCandidate("i2", "Inst 2", state="maharashtra", district="pune")
    c3 = InstitutionCandidate("i3", "Inst 3", state="Maharashtra", district="Mumbai")
    c_none = InstitutionCandidate("i4", "Inst 4", state=None, district="Pune")

    assert has_matching_district_and_state(c1, c2) is True
    assert has_matching_district_and_state(c1, c3) is False
    assert has_matching_district_and_state(c1, c_none) is False


def test_is_recent_case():
    case_recent = _case("c1", "b1", days_ago=5)
    case_old = _case("c2", "b1", days_ago=45)

    assert is_recent_case(case_recent, days_threshold=30, now=NOW) is True
    assert is_recent_case(case_old, days_threshold=30, now=NOW) is False


def test_is_valid_matter_category():
    assert is_valid_matter_category("court_case") is True
    assert is_valid_matter_category("ragging") is True
    assert is_valid_matter_category("cpgrams_grievance") is True
    assert is_valid_matter_category("completely_unknown_category") is False
    assert is_valid_matter_category("") is False


def test_get_candidate_by_id():
    candidates = [
        InstitutionCandidate("inst-1", "Sandbox Institute of Technology"),
        InstitutionCandidate("inst-2", "State Engineering College"),
    ]
    matched = resolve_institution(
        permanent_id=None,
        free_text_name="Engineering College",
        state=None,
        district=None,
        candidates=candidates,
    )
    found = get_candidate_by_id(matched, "inst-2")
    assert found is not None
    assert found.institution_id == "inst-2"

    not_found = get_candidate_by_id(matched, "inst-nonexistent")
    assert not_found is None


def test_format_case_reference_summary():
    c = _case("case-100", "bureau-approval", matter_type="ragging")
    summary = format_case_reference_summary(c)
    assert "Case[case-100]" in summary
    assert "bureau-approval" in summary
    assert "ragging" in summary

    c_nobureau = _case("case-101", None)
    summary_nobureau = format_case_reference_summary(c_nobureau)
    assert "unassigned" in summary_nobureau


def test_has_any_shared_external_reference():
    c1 = _case("c1", "b1", refs=("REF-A", "REF-B"))
    c2 = _case("c2", "b2", refs=("REF-B", "REF-C"))
    c3 = _case("c3", "b3", refs=("REF-X", "REF-Y"))

    assert has_any_shared_external_reference(c1, c2) is True
    assert has_any_shared_external_reference(c1, c3) is False
    assert has_any_shared_external_reference(c2, c3) is False


def test_is_institution_candidate_active():
    c_valid = InstitutionCandidate("i1", "Test College", permanent_id="1-000")
    c_no_id = InstitutionCandidate("", "Test College", permanent_id=None)
    c_no_name = InstitutionCandidate("i2", "   ", permanent_id="1-001")

    assert is_institution_candidate_active(c_valid) is True
    assert is_institution_candidate_active(c_no_id) is False
    assert is_institution_candidate_active(c_no_name) is False


def test_calculate_days_between_cases():
    c1 = _case("c1", "b1", days_ago=10)
    c2 = _case("c2", "b1", days_ago=25)
    assert calculate_days_between_cases(c1, c2) == 15
    assert calculate_days_between_cases(c2, c1) == 15
    assert calculate_days_between_cases(c1, c1) == 0


def test_get_top_candidate_score():
    candidates = [
        InstitutionCandidate("inst-1", "Sandbox Institute of Technology"),
        InstitutionCandidate("inst-2", "State Engineering College"),
    ]
    matched = resolve_institution(
        permanent_id=None,
        free_text_name="Sandbox Institute of Technology",
        state=None,
        district=None,
        candidates=candidates,
    )
    score = get_top_candidate_score(matched)
    assert score is not None
    assert score > 0.0

    unmatched = resolve_institution(
        permanent_id=None,
        free_text_name="Unknown School",
        state=None,
        district=None,
        candidates=[],
    )
    assert get_top_candidate_score(unmatched) is None


def test_is_valid_resolution_status():
    assert is_valid_resolution_status("matched") is True
    assert is_valid_resolution_status("unresolved") is True
    assert is_valid_resolution_status("pending") is False
    assert is_valid_resolution_status("error") is False
    assert is_valid_resolution_status("") is False


def test_count_shared_references():
    c1 = _case("c1", "b1", refs=("REF-A", "REF-B", "REF-C"))
    c2 = _case("c2", "b1", refs=("REF-B", "REF-C", "REF-D"))
    c3 = _case("c3", "b1", refs=("REF-X", "REF-Y"))

    assert count_shared_references(c1, c2) == 2
    assert count_shared_references(c1, c3) == 0
    assert count_shared_references(c1, c1) == 3


def test_is_same_bureau():
    c1 = _case("c1", "bureau-approval")
    c2 = _case("c2", "bureau-approval")
    c3 = _case("c3", "bureau-grievance")
    c_none = _case("c4", None)

    assert is_same_bureau(c1, c2) is True
    assert is_same_bureau(c1, c3) is False
    assert is_same_bureau(c1, c_none) is False
    assert is_same_bureau(c_none, c_none) is False


def test_get_matter_type():
    c1 = _case("c1", "b1", matter_type="ragging")
    c2 = _case("c2", "b1", matter_type="court_case")
    assert get_matter_type(c1) == "ragging"
    assert get_matter_type(c2) == "court_case"


def test_has_description():
    c_with = _case("c1", "b1", desc="Valid description text")
    c_empty = _case("c2", "b1", desc="")
    c_whitespace = _case("c3", "b1", desc="   ")
    c_none = _case("c4", "b1", desc=None)

    assert has_description(c_with) is True
    assert has_description(c_empty) is False
    assert has_description(c_whitespace) is False
    assert has_description(c_none) is False


def test_get_external_references_count():
    c3 = _case("c1", "b1", refs=("REF-1", "REF-2", "REF-3"))
    c0 = _case("c2", "b1", refs=())

    assert get_external_references_count(c3) == 3
    assert get_external_references_count(c0) == 0


def test_get_unique_matter_types():
    c1 = _case("c1", "b1", matter_type="ragging")
    c2 = _case("c2", "b1", matter_type="norm_violation")
    c3 = _case("c3", "b1", matter_type="ragging")
    assert get_unique_matter_types([c1, c2, c3]) == ["norm_violation", "ragging"]
    assert get_unique_matter_types([]) == []


def test_has_any_overlap_reasons():
    c1 = _case("c1", "b1", refs=("REF-A",))
    c2 = _case("c2", "b1", refs=("REF-A",))
    res = score_pair(c1, c2)
    assert has_any_overlap_reasons(res) is True


def test_is_cross_state_institution_pair():
    c1 = InstitutionCandidate("i1", "Inst 1", state="Maharashtra")
    c2 = InstitutionCandidate("i2", "Inst 2", state="Delhi")
    c3 = InstitutionCandidate("i3", "Inst 3", state="maharashtra")
    c_none = InstitutionCandidate("i4", "Inst 4", state=None)

    assert is_cross_state_institution_pair(c1, c2) is True
    assert is_cross_state_institution_pair(c1, c3) is False
    assert is_cross_state_institution_pair(c1, c_none) is False
    assert is_cross_state_institution_pair(c_none, c_none) is False


def test_filter_cases_by_matter_type():
    c1 = _case("c1", "b1", matter_type="ragging")
    c2 = _case("c2", "b1", matter_type="norm_violation")
    c3 = _case("c3", "b1", matter_type="ragging")

    ragging_cases = filter_cases_by_matter_type([c1, c2, c3], "ragging")
    assert len(ragging_cases) == 2
    assert all(c.matter_type == "ragging" for c in ragging_cases)
    assert filter_cases_by_matter_type([c1, c2, c3], "court_case") == []


def test_filter_cases_by_bureau():
    c1 = _case("c1", "bureau_a", matter_type="ragging")
    c2 = _case("c2", "bureau_b", matter_type="ragging")
    c3 = _case("c3", "bureau_a", matter_type="norm_violation")

    bureau_a_cases = filter_cases_by_bureau([c1, c2, c3], "bureau_a")
    assert len(bureau_a_cases) == 2
    assert {c.case_id for c in bureau_a_cases} == {"c1", "c3"}
    assert filter_cases_by_bureau([c1, c2, c3], "bureau_c") == []


def test_has_matching_receipt_year():
    c1 = _case("c1", "b1", days_ago=10)
    c2 = _case("c2", "b1", days_ago=20)
    c3 = _case("c3", "b1", days_ago=400)

    assert has_matching_receipt_year(c1, c2) is True
    assert has_matching_receipt_year(c1, c3) is False


def test_is_same_receipt_month():
    c1 = _case("c1", "b1", days_ago=2)
    c2 = _case("c2", "b1", days_ago=5)
    c3 = _case("c3", "b1", days_ago=60)

    assert is_same_receipt_month(c1, c2) is True
    assert is_same_receipt_month(c1, c3) is False


def test_get_candidate_institution_names():
    c1 = InstitutionCandidate("i1", "Indian Institute of Science")
    c2 = InstitutionCandidate("i2", "  ")
    c3 = InstitutionCandidate("i3", "IIT Bombay")

    names = get_candidate_institution_names([c1, c2, c3])
    assert names == ["Indian Institute of Science", "IIT Bombay"]
    assert get_candidate_institution_names([]) == []


def test_is_empty_or_whitespace():
    assert is_empty_or_whitespace(None) is True
    assert is_empty_or_whitespace("") is True
    assert is_empty_or_whitespace("   ") is True
    assert is_empty_or_whitespace("\t\n") is True
    assert is_empty_or_whitespace("valid") is False
    assert is_empty_or_whitespace("  valid  ") is False


def test_get_candidate_by_permanent_id():
    c1 = InstitutionCandidate("i1", "Inst 1", permanent_id="1-1234567")
    c2 = InstitutionCandidate("i2", "Inst 2", permanent_id="1-7654321")

    assert get_candidate_by_permanent_id([c1, c2], "1-1234567") == c1
    assert get_candidate_by_permanent_id([c1, c2], " 1-7654321 ") == c2
    assert get_candidate_by_permanent_id([c1, c2], "1-9999999") is None
    assert get_candidate_by_permanent_id([], "1-1234567") is None


def test_count_cases_by_matter_type():
    c1 = _case("c1", "b1", matter_type="ragging")
    c2 = _case("c2", "b1", matter_type="ragging")
    c3 = _case("c3", "b1", matter_type="norm_violation")

    counts = count_cases_by_matter_type([c1, c2, c3])
    assert counts == {"ragging": 2, "norm_violation": 1}
    assert count_cases_by_matter_type([]) == {}


def test_filter_candidates_by_state():
    c1 = InstitutionCandidate("i1", "Inst 1", state="Maharashtra")
    c2 = InstitutionCandidate("i2", "Inst 2", state="Delhi")
    c3 = InstitutionCandidate("i3", "Inst 3", state="maharashtra")
    c4 = InstitutionCandidate("i4", "Inst 4", state=None)

    mh_cands = filter_candidates_by_state([c1, c2, c3, c4], "Maharashtra")
    assert len(mh_cands) == 2
    assert {c.institution_id for c in mh_cands} == {"i1", "i3"}
    assert filter_candidates_by_state([c1, c2, c3, c4], "Karnataka") == []


def test_filter_candidates_by_district():
    c1 = InstitutionCandidate("i1", "Inst 1", district="Pune")
    c2 = InstitutionCandidate("i2", "Inst 2", district="Nagpur")
    c3 = InstitutionCandidate("i3", "Inst 3", district="pune")
    c4 = InstitutionCandidate("i4", "Inst 4", district=None)

    pune_cands = filter_candidates_by_district([c1, c2, c3, c4], "Pune")
    assert len(pune_cands) == 2
    assert {c.institution_id for c in pune_cands} == {"i1", "i3"}
    assert filter_candidates_by_district([c1, c2, c3, c4], "Thane") == []


def test_is_case_within_window():
    base_date = dt.datetime(2026, 6, 1, tzinfo=dt.UTC)
    c_close = _case("c1", "b1", days_ago=0)  # NOW is 2026-10-29
    # Let's test with respect to NOW
    c1 = _case("c1", "b1", days_ago=30)
    c2 = _case("c2", "b1", days_ago=120)

    assert is_case_within_window(c1, NOW, window_days=90) is True
    assert is_case_within_window(c2, NOW, window_days=90) is False
    assert is_case_within_window(c2, NOW, window_days=150) is True


def test_has_distinct_bureau_pair():
    c1 = _case("c1", "bureau_a")
    c2 = _case("c2", "bureau_b")
    c3 = _case("c3", "bureau_a")
    c_none = _case("c4", None)

    assert has_distinct_bureau_pair([c1, c2]) is True
    assert has_distinct_bureau_pair([c1, c3]) is False
    assert has_distinct_bureau_pair([c1, c_none]) is False
    assert has_distinct_bureau_pair([]) is False


def test_get_candidate_permanent_ids():
    c1 = InstitutionCandidate("i1", "Inst 1", permanent_id="1-2345678")
    c2 = InstitutionCandidate("i2", "Inst 2", permanent_id="1-1234567")
    c3 = InstitutionCandidate("i3", "Inst 3", permanent_id="1-2345678")
    c4 = InstitutionCandidate("i4", "Inst 4", permanent_id=None)

    perm_ids = get_candidate_permanent_ids([c1, c2, c3, c4])
    assert perm_ids == ["1-1234567", "1-2345678"]
    assert get_candidate_permanent_ids([]) == []


def test_filter_cases_by_date_range():
    c1 = _case("c1", "b1", days_ago=10)
    c2 = _case("c2", "b1", days_ago=20)
    c3 = _case("c3", "b1", days_ago=50)

    start = NOW - dt.timedelta(days=25)
    end = NOW - dt.timedelta(days=5)
    filtered = filter_cases_by_date_range([c1, c2, c3], start, end)
    assert len(filtered) == 2
    assert {c.case_id for c in filtered} == {"c1", "c2"}


def test_is_empty_external_references():
    c_empty = _case("c1", "b1", refs=[])
    c_refs = _case("c2", "b1", refs=["REF-123"])

    assert is_empty_external_references(c_empty) is True
    assert is_empty_external_references(c_refs) is False


def test_get_highest_scoring_candidate():
    m1 = ResolutionMatch("i1", 75.0, "reason1")
    m2 = ResolutionMatch("i2", 95.0, "reason2")
    m3 = ResolutionMatch("i3", 85.0, "reason3")

    top = get_highest_scoring_candidate([m1, m2, m3])
    assert top == m2
    assert get_highest_scoring_candidate([]) is None


def test_has_case_id():
    c1 = _case("CASE-101", "b1")
    c2 = _case("CASE-102", "b1")

    assert has_case_id([c1, c2], "CASE-101") is True
    assert has_case_id([c1, c2], "CASE-999") is False
    assert has_case_id([], "CASE-101") is False


def test_filter_matches_by_min_score():
    m1 = ResolutionMatch("i1", 85.0, "reason1")
    m2 = ResolutionMatch("i2", 60.0, "reason2")
    m3 = ResolutionMatch("i3", 92.0, "reason3")

    high = filter_matches_by_min_score([m1, m2, m3], 80.0)
    assert len(high) == 2
    assert {m.institution_id for m in high} == {"i1", "i3"}
    assert filter_matches_by_min_score([m1, m2, m3], 95.0) == []


def test_is_exact_resolution_match():
    m_exact = ResolutionMatch("i1", 100.0, "exact_id")
    m_near = ResolutionMatch("i2", 99.5, "fuzzy")

    assert is_exact_resolution_match(m_exact) is True
    assert is_exact_resolution_match(m_near) is False
    assert is_exact_resolution_match(None) is False


def test_get_candidate_ids():
    c1 = InstitutionCandidate("inst_b", "Inst B")
    c2 = InstitutionCandidate("inst_a", "Inst A")
    c3 = InstitutionCandidate("inst_b", "Inst B copy")

    assert get_candidate_ids([c1, c2, c3]) == ["inst_a", "inst_b"]
    assert get_candidate_ids([]) == []


def test_has_duplicate_case_ids():
    c1 = _case("c1", "b1")
    c2 = _case("c2", "b1")
    c3 = _case("c1", "b2")

    assert has_duplicate_case_ids([c1, c2, c3]) is True
    assert has_duplicate_case_ids([c1, c2]) is False
    assert has_duplicate_case_ids([]) is False


def test_get_resolution_score_range():
    m1 = ResolutionMatch("i1", 72.5, "name")
    m2 = ResolutionMatch("i2", 95.0, "permanent_id")
    m3 = ResolutionMatch("i3", 81.0, "name")

    assert get_resolution_score_range([m1, m2, m3]) == (72.5, 95.0)
    assert get_resolution_score_range([m1]) == (72.5, 72.5)
    assert get_resolution_score_range([]) is None


def test_count_candidates_with_permanent_id():
    c1 = InstitutionCandidate(institution_id="i1", name="A", permanent_id="1-100")
    c2 = InstitutionCandidate(institution_id="i2", name="B", permanent_id=None)
    c3 = InstitutionCandidate(institution_id="i3", name="C", permanent_id="   ")
    c4 = InstitutionCandidate(institution_id="i4", name="D", permanent_id="1-200")

    assert count_candidates_with_permanent_id([c1, c2, c3, c4]) == 2
    assert count_candidates_with_permanent_id([]) == 0


def test_count_cases_with_description():
    now = dt.datetime(2026, 1, 10, tzinfo=dt.timezone.utc)
    c1 = CaseFacts(case_id="c1", bureau_id="b1", matter_type="admission", external_refs=(), description="Fee refund", received_at=now)
    c2 = CaseFacts(case_id="c2", bureau_id="b1", matter_type="admission", external_refs=(), description=None, received_at=now)
    c3 = CaseFacts(case_id="c3", bureau_id="b1", matter_type="admission", external_refs=(), description="   ", received_at=now)

    assert count_cases_with_description([c1, c2, c3]) == 1
    assert count_cases_with_description([]) == 0


def test_get_case_age_days():
    received = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    ref_later = dt.datetime(2026, 1, 16, tzinfo=dt.timezone.utc)
    ref_earlier = dt.datetime(2025, 12, 25, tzinfo=dt.timezone.utc)
    case = CaseFacts(case_id="c1", bureau_id="b1", matter_type="admission", external_refs=(), description=None, received_at=received)

    assert get_case_age_days(case, ref_later) == 15
    assert get_case_age_days(case, ref_earlier) == 0


def test_get_average_resolution_score():
    m1 = ResolutionMatch("i1", 70.0, "name")
    m2 = ResolutionMatch("i2", 90.0, "permanent_id")
    assert get_average_resolution_score([m1, m2]) == 80.0
    assert get_average_resolution_score([]) is None


def test_filter_cases_with_external_refs():
    now = dt.datetime(2026, 1, 10, tzinfo=dt.timezone.utc)
    c1 = CaseFacts(case_id="c1", bureau_id="b1", matter_type="admission", external_refs=("REF-1",), description=None, received_at=now)
    c2 = CaseFacts(case_id="c2", bureau_id="b1", matter_type="admission", external_refs=(), description=None, received_at=now)
    assert filter_cases_with_external_refs([c1, c2]) == [c1]
    assert filter_cases_with_external_refs([]) == []
