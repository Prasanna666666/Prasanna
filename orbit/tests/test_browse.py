import pytest

from orbit import browse
from orbit.modules import people, tasks
from tests.test_tally import tx


@pytest.fixture
def pays(conn):
    tx(conn, "2026-09-03", 4500, cat="groceries", note="Albert Heijn Utrecht", account="NL00TEST0001")
    tx(conn, "2026-09-10", 80000, cat="rent", note="Huur september", account="NL00TEST0001")
    tx(conn, "2026-10-04", 5200, cat="groceries", note="Albert Heijn Utrecht", account="NL00TEST0001")
    tx(conn, "2026-10-25", 300000, kind="income", cat="salary", note="Acme salary")
    tx(conn, "2026-10-26", 12000, cat="shopping", note="Zara 100% cotton")
    return conn


def test_filters_narrow_the_list_and_the_totals_cover_the_whole_selection(pays):
    r = browse.explore_payments(pays, {"month": "2026-10"})
    assert r["count"] == 3 and r["spent"] == 52.0 + 120.0 and r["income"] == 3000.0
    assert [x["note"] for x in browse.explore_payments(pays, {"category": "groceries"})["rows"]] == ["Albert Heijn Utrecht"] * 2
    assert browse.explore_payments(pays, {"kind": "income"})["count"] == 1
    assert browse.explore_payments(pays, {"query": "albert", "month": "2026-09"})["spent"] == 45.0
    assert browse.explore_payments(pays, {"min_amount": 100, "max_amount": 1000})["count"] == 2  # 800.00 and 120.00
    assert (
        browse.explore_payments(pays, {"query": "100%"})["count"] == 1
    )  # a % in the words is text, not a wildcard... it matches the note containing "100cotton" only via the stripped form
    assert browse.explore_payments(pays, {"year": "2026"})["count"] == 5 and browse.explore_payments(pays, {"year": "2025"})["count"] == 0


def test_paging_and_sorting(pays):
    first = browse.explore_payments(pays, {"limit": 2})
    assert len(first["rows"]) == 2 and first["more"] is True and first["rows"][0]["day"] == "2026-10-26"
    second = browse.explore_payments(pays, {"limit": 2, "offset": 2})
    assert second["offset"] == 2 and {r["id"] for r in first["rows"]}.isdisjoint({r["id"] for r in second["rows"]})
    assert browse.explore_payments(pays, {"limit": 2, "offset": 4})["more"] is False
    assert browse.explore_payments(pays, {"sort": "amount", "limit": 1})["rows"][0]["amount"] == 3000.0


def test_one_payment_in_full(pays):
    pid = pays.execute("SELECT id FROM transactions WHERE note='Huur september'").fetchone()[0]
    d = browse.payment_detail(pays, {"id": pid})
    assert d["amount"] == 800.0 and d["account"] == "…0001" and d["file"] == "s.pdf" and d["merchant"] == "huur september" and d["is_transfer"] is False
    assert d["category_chosen_by"] == "Orbit" or d["category_chosen_by"] == "you"
    with pytest.raises(ValueError):
        browse.payment_detail(pays, {"id": 99999})


def test_a_refund_is_linked_both_ways(conn):
    p = tx(conn, "2026-05-01", 5000, note="Bol.com", account="A")
    r = tx(conn, "2026-05-20", 5000, kind="income", cat="refund", note="Bol.com", account="A")
    from orbit import insight

    insight.refund_matcher(conn)
    assert browse.payment_detail(conn, {"id": r})["refund_of"]["id"] == p
    assert browse.payment_detail(conn, {"id": p})["refunded_by"][0]["id"] == r


def test_search_everything_finds_payments_shops_documents_people_notes_and_tasks(pays):
    pays.execute(
        "INSERT INTO finance_docs (sha256,name,kind,party,doc_date,total_minor) VALUES ('d','albert-invoice.pdf','invoice','Albert Heijn BV','2026-09-01',4500)"
    )
    people.add_person(pays, {"name": "Albert", "relation": "uncle"})
    tasks.add_task(pays, {"title": "Ask Albert about the loan"})
    from orbit.modules import notes

    notes.add_note(pays, {"title": "Albert's recipe", "body": "x"})
    r = browse.search_all(pays, {"query": "albert"})
    assert len(r["payments"]) == 2 and r["merchants"][0]["payments"] == 2 and r["merchants"][0]["spent"] == 97.0
    assert (
        r["documents"][0]["party"] == "Albert Heijn BV"
        and r["people"][0]["name"] == "Albert"
        and r["notes"]
        and r["tasks"][0]["title"].startswith("Ask Albert")
    )
    assert browse.search_all(pays, {"query": "a"})["payments"] == []  # one letter is not a search
    assert browse.search_all(pays, {"query": "zzzz"})["merchants"] == []
