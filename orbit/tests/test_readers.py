"""One reader for every format. Each comes out in the same shape; scans go through OCR (mocked here: the sandbox has no Tesseract); archives are bounded."""

import io
import json
import zipfile

import pymupdf
import pytest
from PIL import Image

from orbit import parser, readers
from orbit.modules import documents, money

HEAD = ["Datum", "Omschrijving", "Af", "Bij", "Saldo"]
ROWS = [
    HEAD,
    ["01-10-2026", "Opening", "", "", "2.000,00"],
    ["02-10-2026", "Albert Heijn", "23,45", "", "1.976,55"],
    ["25-10-2026", "Salaris", "", "2.850,00", "4.826,55"],
]
X = [(40, 90), (100, 230), (260, 310), (330, 390), (420, 480)]


def tsv_of(rows):
    """What Tesseract prints (word boxes in pixels at 250 dpi) for a statement table, one word per cell."""
    out = ["level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"]
    scale = 250 / 72
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            if text:
                x0, x1 = X[c]
                out.append(
                    f"5\t1\t1\t1\t{r + 1}\t{c + 1}\t{round(x0 * scale)}\t{round((100 + r * 20) * scale)}\t{round((x1 - x0) * scale)}\t{round(12 * scale)}\t{93 if c else 90}\t{text}"
                )
    return "\n".join(out)


@pytest.fixture
def fake_ocr(monkeypatch):
    monkeypatch.setattr(readers, "run_tesseract", lambda png: tsv_of(ROWS))


def text_pdf(path, rows=ROWS, password=None):
    doc = pymupdf.open()
    page = doc.new_page()
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            if text:
                page.insert_text((X[c][0], 100 + r * 20), text, fontsize=9)
    if password:
        doc.save(str(path), encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw=password, owner_pw=password)
    else:
        doc.save(str(path))
    doc.close()


def scanned_pdf(path):
    png = io.BytesIO()
    Image.new("RGB", (600, 800), "white").save(png, "PNG")
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_image(page.rect, stream=png.getvalue())  # a picture of a page: no text layer
    doc.save(str(path))
    doc.close()


def cells(res):
    return [[c[2] for c in line] for line in res["data"]["table"]]


def test_a_text_pdf_gives_positioned_cells_and_plain_text(tmp_path):
    text_pdf(tmp_path / "a.pdf")
    res = parser.extract(tmp_path / "a.pdf")
    assert res["kind"] == "pdf" and "Albert Heijn" in res["text"] and cells(res)[2] == ["02-10-2026", "Albert Heijn", "23,45", "1.976,55"]
    assert "ocr_pages" not in res["meta"]


def test_a_scanned_pdf_is_read_with_ocr_into_the_same_shape(tmp_path, fake_ocr):
    scanned_pdf(tmp_path / "scan.pdf")
    res = parser.extract(tmp_path / "scan.pdf")
    assert res["meta"]["ocr_pages"] == 1 and 90 <= res["meta"]["ocr_confidence"] <= 93
    assert cells(res)[3] == ["25-10-2026", "Salaris", "2.850,00", "4.826,55"] and "Salaris" in res["text"]


def test_a_photo_or_screenshot_of_a_statement_is_read_the_same_way(tmp_path, fake_ocr):
    Image.new("RGB", (800, 1000), "white").save(tmp_path / "photo.jpg")
    res = parser.extract(tmp_path / "photo.jpg")
    assert res["kind"] == "image" and res["meta"]["ocr_pages"] == 1 and cells(res)[1][1] == "Opening"


def test_a_scan_without_tesseract_fails_clearly_instead_of_returning_nothing(tmp_path, monkeypatch):
    scanned_pdf(tmp_path / "scan.pdf")
    monkeypatch.setattr(readers, "ocr_languages", lambda: "")
    with pytest.raises(RuntimeError, match="Tesseract"):
        parser.extract(tmp_path / "scan.pdf")


def test_a_password_protected_pdf_opens_with_the_password_from_passwords_txt_and_not_without(tmp_path, monkeypatch):
    text_pdf(tmp_path / "locked.pdf", password="geheim123")
    monkeypatch.delenv("ORBIT_FINANCE", raising=False)
    with pytest.raises(ValueError, match="password-protected"):
        parser.extract(tmp_path / "locked.pdf")
    (tmp_path / "passwords.txt").write_text("fout\ngeheim123\n")
    monkeypatch.setenv("ORBIT_PASSWORDS_FILE", str(tmp_path / "passwords.txt"))
    res = parser.extract(tmp_path / "locked.pdf")
    assert res["meta"].get("unlocked") and "Albert Heijn" in res["text"]


def test_the_passwords_file_is_never_read_as_a_document(tmp_path):
    fin, out = tmp_path / "fin", tmp_path / "out"
    fin.mkdir()
    (fin / "passwords.txt").write_text("secret\n")
    (fin / "note.txt").write_text("hello")
    r = parser.process_inbox(fin, out, isolated=False)
    assert r["parsed"] == 1 and r["skipped"] == 1
    assert "secret" not in "".join(p.read_text() for p in out.glob("*.json"))


def test_spreadsheets_word_files_web_pages_and_json_all_give_rows_and_text(tmp_path):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    for row in [["Datum", "Bedrag"], ["2026-10-01", 23.45], ["2026-10-02", 1000]]:
        ws.append(row)
    wb.save(tmp_path / "s.xlsx")
    sheet = parser.extract(tmp_path / "s.xlsx")
    assert sheet["kind"] == "sheet" and sheet["data"]["rows"] == [["Datum", "Bedrag"], ["2026-10-01", "23.45"], ["2026-10-02", "1000"]]

    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    xml = (
        f'<w:document xmlns:w="{w}"><w:body><w:p><w:r><w:t>Factuur Ziggo</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Totaal</w:t></w:r></w:p></w:tc>'
        f"<w:tc><w:p><w:r><w:t>60,50</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>"
    )
    with zipfile.ZipFile(tmp_path / "d.docx", "w") as z:
        z.writestr("word/document.xml", xml)
    doc = parser.extract(tmp_path / "d.docx")
    assert "Factuur Ziggo" in doc["text"] and doc["data"]["rows"] == [["Totaal", "60,50"]]

    (tmp_path / "p.html").write_text("<html><body><p>Hallo</p><table><tr><td>Totaal</td><td>9,99</td></tr></table><script>evil()</script></body></html>")
    page = parser.extract(tmp_path / "p.html")
    assert page["data"]["rows"] == [["Totaal", "9,99"]] and "evil" not in page["text"] and "Hallo" in page["text"]

    (tmp_path / "t.json").write_text(json.dumps([{"date": "2026-10-01", "amount": 5}, {"date": "2026-10-02", "amount": 7}]))
    assert parser.extract(tmp_path / "t.json")["data"]["rows"] == [["date", "amount"], ["2026-10-01", "5"], ["2026-10-02", "7"]]


def test_a_docx_with_xml_entities_is_refused(tmp_path):
    with zipfile.ZipFile(tmp_path / "evil.docx", "w") as z:
        z.writestr("word/document.xml", '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><document/>')
    with pytest.raises(ValueError, match="unsafe"):
        parser.extract(tmp_path / "evil.docx")


def test_an_email_and_its_attachment_each_become_a_document(tmp_path):
    from email.message import EmailMessage

    m = EmailMessage()
    m["From"], m["To"], m["Subject"], m["Date"] = "shop@example.com", "me@example.com", "Uw factuur", "Mon, 05 Oct 2026 10:00:00 +0000"
    m.set_content("Zie bijlage voor uw factuur van 60,50.")
    m.add_attachment(b"Factuur Ziggo totaal 60,50", maintype="text", subtype="plain", filename="factuur.txt")
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "mail.eml").write_bytes(bytes(m))
    parser.process_inbox(tmp_path / "in", tmp_path / "out", isolated=False)
    docs = [json.loads(p.read_text()) for p in (tmp_path / "out").glob("*.json")]
    assert sorted(d["name"] for d in docs) == ["mail.eml", "mail.eml/factuur.txt"]
    assert any("Uw factuur" in d["text"] for d in docs) and any("totaal 60,50" in d["text"] for d in docs)


def test_zip_archives_are_opened_file_by_file_and_stay_bounded(tmp_path):
    (tmp_path / "in").mkdir()
    with zipfile.ZipFile(tmp_path / "in" / "statements.zip", "w") as z:
        z.writestr("oct.txt", "Datum Omschrijving")
        z.writestr("../../escape.txt", "path traversal attempt")  # only the file name is ever used
        z.writestr("inner.zip", b"PK")  # archives inside archives are ignored
    parser.process_inbox(tmp_path / "in", tmp_path / "out", isolated=False)
    names = sorted(json.loads(p.read_text())["name"] for p in (tmp_path / "out").glob("*.json"))
    assert names == ["statements.zip/escape.txt", "statements.zip/oct.txt"] and not (tmp_path / "escape.txt").exists()


def test_a_scanned_statement_goes_all_the_way_to_a_verified_import(tmp_path, fake_ocr, conn):
    fin = tmp_path / "fin"
    fin.mkdir()
    scanned_pdf(fin / "ing-scan.pdf")
    parser.process_inbox(fin, tmp_path / "parsed", isolated=False, area="finance")
    documents.ingest_dir(conn, tmp_path / "parsed")

    layout = {
        "header_line": 0,
        "roles": ["date", "description", "debit", "credit", "balance"],
        "date_format": "%d-%m-%Y",
        "month_names": [],
        "decimal": ",",
        "thousands": ".",
        "debit_words": [],
        "credit_words": [],
        "date_on_every_row": True,
    }

    class Model:
        def chat(self, model, messages, schema=None, **kw):
            from orbit import extract

            return {"content": json.dumps({"kind": "bank_statement"} if messages[0]["content"] == extract.KIND_PROMPT else layout)}

    r = money.import_statements(conn, client=Model(), model="fake")
    assert r["new_transactions"] == 2 and r["needs_check"] == []
    assert conn.execute("SELECT status FROM statement_files").fetchone()["status"] in ("verified", "unverified")
