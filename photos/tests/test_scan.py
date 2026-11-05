from images import library as lib
from images.people import repository as people
from images.search.text import search_text_ids

from aperture.paging import make_page


def test_scan_indexes_everything(scanned):
    conn = scanned.db.connect()
    cov = lib.coverage(conn)
    assert (cov.total, cov.indexed, cov.embedded, cov.failed) == (5, 5, 5, 0)
    assert cov.faces_done == 5 and cov.ocr_done == 5


def test_originals_untouched(scanned, library):
    before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in library.rglob("*.jpg")}
    from images.indexing.runner import Scanner

    from tests.conftest import fake_services

    Scanner(scanned.paths, scanned.settings, scanned.db, fake_services).run()
    after = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in library.rglob("*.jpg")}
    assert before == after


def test_scan_is_idempotent_and_resumable(scanned):
    from images.indexing.runner import Scanner

    from tests.conftest import fake_services

    second = Scanner(scanned.paths, scanned.settings, scanned.db, fake_services).run()
    assert second.processed == 0


def test_text_search_finds_ocr_and_never_dumps_library(scanned):
    conn = scanned.db.connect()
    assert len(search_text_ids(conn, "invoice")) == 3
    assert len(search_text_ids(conn, "zzzznotthere")) == 0


def test_people_grouped(scanned):
    conn = scanned.db.connect()
    groups = people.list_people(conn)
    assert sorted(g.photos for g in groups) == [2, 3]


def test_library_listing_is_unbounded(scanned):
    conn = scanned.db.connect()
    assert len(lib.item_ids(conn)) == 5
    assert len(lib.item_ids(conn, name_like="italy")) == 3
    assert len(lib.item_ids(conn, kinds=())) == 0


def test_page_math_over_large_sets():
    page = make_page(40_001, 36, 99_999)
    assert page.pages == 1112 and page.number == 1112 and page.end == 40_001
