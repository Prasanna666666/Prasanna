from library import selfcheck
from tests.test_readers import text_pdf


def test_the_check_counts_every_file_by_what_it_is_and_how_it_read(tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "note.txt").write_text("Dad BP tablet after breakfast, doctor said reduce salt in every meal.")
    text_pdf(folder / "plain.pdf")
    odd = folder / "2025-02.pdf"
    odd.write_bytes(b"\xef\xbb\xbf\r\n" + (folder / "plain.pdf").read_bytes())  # stray bytes before the header
    (folder / "empty.bin").write_bytes(bytes(range(256)) * 4)
    report = selfcheck.check([("docs", folder)], timeout=60)
    assert report["files"] == 4
    assert report["by_kind"]["pdf"] == {"text with a table": 2}  # both PDFs, the one with stray bytes too
    assert report["by_kind"]["text"] == {"text": 1}
    assert "binary" in report["by_kind"]
    assert "files looked at" in selfcheck.render(report)
