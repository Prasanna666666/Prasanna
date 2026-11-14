"""The whole way: a file is read by the sealed reader, judged and stored by the Documents service, taken by Finance, and proved there.
Finance is one client of the service; a second client (health) takes its own kind from the same store."""

import json
import urllib.parse

import pytest
from finance import library_client
from finance.modules import ALL, money
from kit import db, extract

from library import parser, store
from tests.test_readers import fake_ocr, scanned_pdf  # noqa: F401 - the fixture is used by name

LAYOUT = {
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
    """Says what a file is (by a word in it) and what the columns of a statement are."""

    def __init__(self):
        self.asked = 0

    def chat(self, model, messages, schema=None, **kw):
        self.asked += 1
        if messages[0]["content"] == extract.KIND_PROMPT:
            text = messages[1]["content"]
            kind = "medical" if "bloedonderzoek" in text else "bank_statement"
            return {"content": json.dumps({"kind": kind, "title": "Blood test" if kind == "medical" else "Statement", "date": "2026-03-01"})}
        return {"content": json.dumps(LAYOUT)}


def library_over_http(service_conn):
    """What the HTTP calls would return, without a socket: the client under test asks the real store."""

    def fetch(method, path):
        if method == "POST":
            return {"ok": True}
        query = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(path).query).items()}
        kinds = [k for k in query.get("kind", "").split(",") if k]
        found = store.list_documents(
            service_conn, kinds, query.get("area", ""), since=int(query.get("since", 0)), limit=int(query.get("limit", 100)), full=query.get("full") == "1"
        )
        return {"documents": found}

    return fetch


@pytest.fixture
def finance(tmp_path):
    c = db.connect(tmp_path / "finance.db")
    db.migrate(c, ALL)
    return c


def test_a_scanned_statement_goes_from_the_reader_through_the_service_to_a_verified_import(tmp_path, fake_ocr, conn, finance):  # noqa: F811
    folder, parsed = tmp_path / "finance-folder", tmp_path / "parsed"
    folder.mkdir()
    scanned_pdf(folder / "ing-scan.pdf")
    parser.process_inbox(folder, parsed, isolated=False, area="finance")
    store.ingest_dir(conn, parsed)
    assert store.judge_pending(conn, Model(), "fake")["read"] == 1
    fetch = library_over_http(conn)
    assert library_client.pull(finance, fetch) == {"new": 1, "known": 0}
    assert library_client.pull(finance, fetch) == {"new": 0, "known": 0}  # the second time there is nothing new
    r = money.import_statements(finance, client=Model(), model="fake")
    assert r["new_transactions"] == 2 and r["needs_check"] == []


def test_a_second_app_takes_its_own_kind_from_the_same_store_and_finance_never_sees_it(tmp_path, conn, finance):
    health, parsed = tmp_path / "health-folder", tmp_path / "parsed"
    health.mkdir()
    (health / "bloed.txt").write_text("Uitslag bloedonderzoek 1 maart 2026: alle waarden normaal. Kliniek centrum.")
    parser.process_inbox(health, parsed, isolated=False, area="health")  # a collection with any name; its files are always read
    store.ingest_dir(conn, parsed)
    store.judge_pending(conn, Model(), "fake")
    assert store.list_documents(conn, ["invoice"]) == []  # an app asking for other kinds does not receive it
    assert [d["facts"]["title"] for d in store.list_documents(conn, ["medical"])] == ["Blood test"]  # what a health app would ask for
    assert library_client.pull(finance, library_over_http(conn)) == {"new": 0, "known": 0}  # Finance asks for its own kinds and its own folder only
    assert finance.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0
