"""Pure unit tests, no DB — the parsing/diff core is deliberately
separated from the DB/HTTP layer so it's testable in isolation."""

from app.services.reference_import import compute_diff, parse_csv, parse_xlsx

VALID_CSV = (
    "permanent_id,name,address,state,district,region_name,programmes,approved_intake\n"
    "1-100000001,Test Institute of Technology,123 Test Road,Tamil Nadu,Chennai,South,B.Tech CSE,120\n"
)


def test_parses_a_valid_row():
    rows = parse_csv(VALID_CSV.encode("utf-8"))
    assert len(rows) == 1
    assert rows[0].errors == []
    assert rows[0].permanent_id == "1-100000001"
    assert rows[0].raw["name"] == "Test Institute of Technology"
    assert rows[0].raw["approved_intake"] == 120


def test_missing_required_column_is_an_error():
    csv_bytes = b"permanent_id,address\n1-100000001,123 Test Road\n"
    rows = parse_csv(csv_bytes)
    assert any("missing required column 'name'" in e for e in rows[0].errors)


def test_malformed_permanent_id_is_an_error():
    csv_bytes = b"permanent_id,name\nnot-a-valid-id,Some Institute\n"
    rows = parse_csv(csv_bytes)
    assert any("does not match" in e for e in rows[0].errors)


def test_non_integer_approved_intake_is_an_error():
    csv_bytes = b"permanent_id,name,approved_intake\n1-100000001,Some Institute,not-a-number\n"
    rows = parse_csv(csv_bytes)
    assert any("not an integer" in e for e in rows[0].errors)


def test_bom_prefixed_csv_still_parses():
    csv_bytes = VALID_CSV.encode("utf-8-sig")
    rows = parse_csv(csv_bytes)
    assert rows[0].errors == []
    assert rows[0].permanent_id == "1-100000001"


def test_row_numbers_start_at_2_matching_a_spreadsheet():
    csv_bytes = (VALID_CSV + "1-100000002,Second Institute,,,,,,\n").encode()
    rows = parse_csv(csv_bytes)
    assert rows[0].row_number == 2
    assert rows[1].row_number == 3


def test_xlsx_round_trip():
    from io import BytesIO

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["permanent_id", "name", "approved_intake"])
    ws.append(["1-100000003", "XLSX Institute", 60])
    buf = BytesIO()
    wb.save(buf)

    rows = parse_xlsx(buf.getvalue())
    assert len(rows) == 1
    assert rows[0].errors == []
    assert rows[0].raw["name"] == "XLSX Institute"
    assert rows[0].raw["approved_intake"] == 60


def test_diff_against_nothing_existing_includes_every_present_field():
    diff = compute_diff(None, {"name": "New Institute", "state": "Kerala"})
    assert diff == {"name": {"old": None, "new": "New Institute"}, "state": {"old": None, "new": "Kerala"}}


def test_diff_detects_a_changed_field():
    existing = {"name": "Old Name", "state": "Kerala"}
    diff = compute_diff(existing, {"name": "New Name", "state": "Kerala"})
    assert diff == {"name": {"old": "Old Name", "new": "New Name"}}


def test_diff_is_empty_when_nothing_changed():
    existing = {"name": "Same Name", "state": "Kerala"}
    diff = compute_diff(existing, {"name": "Same Name", "state": "Kerala"})
    assert diff == {}


def test_diff_ignores_blank_incoming_values_never_overwrites_with_blank():
    existing = {"name": "Keep Me", "address": "123 Real Street"}
    diff = compute_diff(existing, {"name": "Keep Me", "address": ""})
    assert diff == {}
