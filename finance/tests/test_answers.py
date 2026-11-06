"""The checks on what the assistant says about your money: every figure must come from a tool, every month must tie to the raw ledger, and what is
not proven or waiting for a check is said next to the figure."""

from finance import answers, toolrun
from tests.test_tally import tx


def seed(conn):
    tx(conn, "2026-09-03", 12000, cat="groceries", note="Albert Heijn")
    tx(conn, "2026-10-04", 5000, cat="groceries", note="Albert Heijn")
    tx(conn, "2026-10-09", 80000, cat="rent", note="Huur")
    tx(conn, "2026-10-25", 300000, kind="income", cat="salary", note="Acme salary")


def test_unproven_figures_ignore_dates_and_small_counts():
    tool = ['{"spent": 850.0, "month": "2026-10", "by_category": [{"category": "rent", "spent": 800.0}]}']
    assert answers.unproven_figures("You spent 850.00 on 2026-10-05, 3 payments, rent 800", tool) == []
    assert answers.unproven_figures("You spent 851.00", tool) == [851.0]
    assert answers.unproven_figures("No tool was used and 9,999 appears", []) == []


def run(conn, name, args):
    out, error = toolrun.run_tool(conn, name, args)
    assert not error
    return out


def test_a_report_that_ties_gets_the_data_health_and_proof_notes_next_to_it(conn):
    seed(conn)
    out = run(conn, "spending_summary", {"month": "2026-10"})
    problems, notes = answers.check_tool(conn, "spending_summary", {"month": "2026-10"}, out)
    assert problems == [] and any("NOT PROVEN" in n for n in notes)  # no statement backs this invented data, and the check says so
    conn.execute("INSERT INTO statement_files (sha256,name,found,added,status) VALUES ('x','a.pdf',3,3,'needs_check')")
    _, notes = answers.check_tool(conn, "spending_summary", {"month": "2026-10"}, out)
    assert any("1 file(s) are waiting for a check" in n for n in notes)


def test_a_month_that_does_not_tie_to_the_ledger_is_not_given(conn, monkeypatch):
    from finance import verify

    seed(conn)
    monkeypatch.setattr(verify, "tally_month", lambda c, m: "the ledger's net change is 1.00 but the reports plus transfers give 2.00")
    out = run(conn, "spending_summary", {"month": "2026-10"})
    problems, _ = answers.check_tool(conn, "spending_summary", {"month": "2026-10"}, out)
    assert problems and "ledger" in problems[0]


def test_tools_that_are_not_reports_need_no_check(conn):
    assert answers.check_tool(conn, "add_task", {"title": "x"}, "{}") == ([], [])
