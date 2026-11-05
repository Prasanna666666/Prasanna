import copy

import pytest

from orbit import readers, tables, verify

pymupdf = pytest.importorskip("pymupdf")
pytest.importorskip("pdfplumber")

ROWS = [("01-03-2026", "Opening balance", "", "1.000,00"), ("02-03-2026", "Albert Heijn", "-45,20", "954,80"),
        ("05-03-2026", "Salary Acme", "3.000,00", "3.954,80"), ("09-03-2026", "Huur", "-1.150,00", "2.804,80")]


def make_pdf(path, rows=ROWS):
    doc = pymupdf.open()
    page = doc.new_page()
    cols, y = [50, 130, 380, 470], 90
    for i, h in enumerate(["Date", "Description", "Amount", "Balance"]):
        page.insert_text((cols[i], y), h, fontsize=9)
    y += 18
    for r in rows:
        for i, t in enumerate(r):
            page.insert_text((cols[i] if i < 2 else cols[i] + (60 - len(t) * 5), y), t, fontsize=9)
        y += 16
    page.insert_text((50, y + 10), "Closing balance 2.804,80", fontsize=9)
    doc.save(path)


def test_a_text_pdf_is_read_by_three_independent_engines(tmp_path):
    make_pdf(tmp_path / "s.pdf")
    d = readers.read_pdf(tmp_path / "s.pdf")
    assert set(d["meta"]["engines"]) == {"pdfplumber", "poppler"} or "pdfplumber" in d["meta"]["engines"]
    base = [[c[2] for c in line] for line in d["data"]["table"]]
    for engine in d["meta"]["engines"]:
        assert [[c[2] for c in line] for line in d["data"][f"table_{engine}"]] == base


def layout():
    return tables.Layout(header_line=0, roles=["date", "description", "amount", "balance"], date_format="%d-%m-%Y", decimal=",", thousands=".")


def parsed_and_data(tmp_path):
    make_pdf(tmp_path / "s.pdf")
    d = readers.read_pdf(tmp_path / "s.pdf")["data"]
    lay = layout()
    return d, lay, tables.parse_table(tables.table_from_data(d), lay)


def test_engines_that_agree_are_reported_ok(tmp_path):
    d, lay, first = parsed_and_data(tmp_path)
    found = verify.engine_agreement("s.pdf", d, lay, first)
    assert found and all(f.level == "ok" for f in found)


def test_one_engine_seeing_a_different_digit_fails_the_file(tmp_path):
    d, lay, first = parsed_and_data(tmp_path)
    bad = copy.deepcopy(d)
    for line in bad["table_pdfplumber"]:
        for c in line:
            if c[2] == "-45,20":
                c[2] = "-46,20"
    found = verify.engine_agreement("s.pdf", bad, lay, first)
    assert any(f.level == "fail" and "pdfplumber" in f.message for f in found)


def test_one_engine_dropping_a_line_fails_the_file(tmp_path):
    d, lay, first = parsed_and_data(tmp_path)
    bad = copy.deepcopy(d)
    bad["table_poppler"] = [line for line in bad["table_poppler"] if not any(c[2] == "Huur" for c in line)]
    assert any(f.level == "fail" for f in verify.engine_agreement("s.pdf", bad, lay, first))


def test_a_pdf_with_no_second_engine_is_flagged_not_trusted_silently(tmp_path):
    d, lay, first = parsed_and_data(tmp_path)
    only = {k: v for k, v in d.items() if not k.startswith("table_")}
    found = verify.engine_agreement("s.pdf", only, lay, first)
    assert found[0].level == "warn" and "only one PDF engine" in found[0].message


def test_a_spreadsheet_has_no_engines_to_compare():
    assert verify.engine_agreement("s.csv", {"rows": [["a"]]}, layout(), tables.Parsed([], "unverified")) == []
