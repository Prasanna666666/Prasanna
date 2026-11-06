from finance import proof
from tests.test_tally import tx


def statement(conn, name, start, end, opening, closing, account="NL00TEST0001", status="verified"):
    conn.execute(
        "INSERT INTO statement_files (sha256,name,found,added,status,account,period_start,period_end,opening_minor,closing_minor) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (name, name, 2, 2, status, account, start, end, opening, closing),
    )


def seeded(conn, **kw):
    tx(conn, "2026-09-05", 1000, account="NL00TEST0001", note="Shop")
    tx(conn, "2026-09-20", 5000, kind="income", account="NL00TEST0001", note="Pay")
    statement(conn, "sep.pdf", "2026-09-01", "2026-09-30", 100000, 104000, **kw)


def test_a_month_fully_covered_by_proven_statements_is_proven(conn):
    seeded(conn)
    p = proof.month_proof(conn, {"month": "2026-09"})
    assert p["proven"] and p["reasons"] == [] and p["accounts"] == 1


def test_a_statement_that_needs_a_check_makes_the_month_not_proven(conn):
    seeded(conn, status="needs_check")
    p = proof.month_proof(conn, {"month": "2026-09"})
    assert not p["proven"] and any("needs a check" in r for r in p["reasons"])
    conn.execute("UPDATE statement_files SET status='unverified'")
    assert any("could not be proven" in r for r in proof.month_proof(conn, {"month": "2026-09"})["reasons"])


def test_a_month_with_a_missing_statement_is_not_proven(conn):
    tx(conn, "2026-09-05", 1000, account="NL00TEST0001")
    statement(conn, "sep-first-half.pdf", "2026-09-01", "2026-09-12", 100000, 99000)
    assert any("no statement covers all of 2026-09" in r for r in proof.month_proof(conn, {"month": "2026-09"})["reasons"])
    assert not proof.month_proof(conn, {"month": "2026-09"})["proven"]


def test_payments_with_no_known_account_are_not_proven(conn):
    seeded(conn)
    tx(conn, "2026-09-07", 700, account="", note="typed by hand")
    assert any("belong to no known account" in r for r in proof.month_proof(conn, {"month": "2026-09"})["reasons"])


def test_statements_whose_balances_do_not_join_up_are_not_proven(conn):
    tx(conn, "2026-09-05", 1000, account="NL00TEST0001")
    tx(conn, "2026-10-05", 1000, account="NL00TEST0001")
    statement(conn, "sep.pdf", "2026-09-01", "2026-09-30", 100000, 104000)
    statement(conn, "oct.pdf", "2026-10-01", "2026-10-31", 99999, 100000)
    assert any(
        "different balance" in r for r in proof.month_proof(conn, {"month": "2026-09"})["reasons"] + proof.month_proof(conn, {"month": "2026-10"})["reasons"]
    )


def test_a_failed_cross_check_stops_any_month_being_proven(conn):
    seeded(conn)
    conn.execute(
        "INSERT INTO findings (agent, level, subject, message, cross) VALUES ('continuity','fail','NL00','closing 1.00 does not match the next opening 2.00',1)"
    )
    p = proof.month_proof(conn, {"month": "2026-09"})
    assert not p["proven"] and any("continuity" in r for r in p["reasons"])


def test_no_data_is_not_proven(conn):
    assert not proof.month_proof(conn, {})["proven"]
