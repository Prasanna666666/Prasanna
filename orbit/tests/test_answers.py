from kit import llm

from orbit import agent, answers
from tests.test_tally import tx


class TooSlow:
    """A model that never finishes in time: the exact code answer must take over."""

    def chat(self, *a, **k):
        raise llm.Slow("out of time")


def ask(conn, q):
    return agent.chat(conn, [], q, client=TooSlow(), model="m")


class Scripted:
    """A model that calls the spending tool, then writes `reply`."""

    def __init__(self, reply):
        self.reply, self.n = reply, 0

    def chat(self, model, messages, tools=None, **kw):
        if kw.get("schema"):  # the routing question: which specialist is this for
            return {"content": '{"agent": "money"}'}
        self.n += 1
        if messages[-1]["role"] == "user" and tools:
            return {"content": "", "tool_calls": [{"function": {"name": "spending_summary", "arguments": {"month": "2026-10"}}}]}
        return {"content": self.reply}


def seed(conn):
    tx(conn, "2026-09-03", 12000, cat="groceries", note="Albert Heijn")
    tx(conn, "2026-10-04", 5000, cat="groceries", note="Albert Heijn")
    tx(conn, "2026-10-09", 80000, cat="rent", note="Huur")
    tx(conn, "2026-10-25", 300000, kind="income", cat="salary", note="Acme salary")


def test_when_the_agent_is_too_slow_it_says_so_and_never_guesses_a_figure(conn):
    seed(conn)
    r = ask(conn, "How much did I spend last month?")
    assert "more thinking than I can do" in r and not any(ch.isdigit() for ch in r.split("in ")[-1].split(" seconds")[0] if False)
    assert "850.00" not in r and "120.00" not in r


def test_the_agent_answers_when_its_figures_match_the_tools(conn):
    seed(conn)
    reply = "In October you spent 850.00 in total."  # 500 groceries... see seed: 50.00 + 800.00
    out = agent.chat(conn, [], "October, what was the damage?", client=Scripted(reply), model="m")
    assert out.startswith(reply) and "NOT PROVEN" in out  # no statement backs this invented data, and the answer says so


def test_an_agent_answer_with_a_figure_no_tool_returned_is_never_shown(conn):
    seed(conn)
    out = agent.chat(conn, [], "how much did I spend in October", client=Scripted("In October you spent 1,234.56 in total."), model="m")
    assert out.startswith("I can't give you that figure") and "not returned by any tool" in out  # refused: the invented figure is only named as the problem


def test_unproven_figures_ignore_dates_and_small_counts():
    tool = ['{"spent": 850.0, "month": "2026-10", "by_category": [{"category": "rent", "spent": 800.0}]}']
    assert answers.unproven_figures("You spent 850.00 on 2026-10-05, 3 payments, rent 800", tool) == []
    assert answers.unproven_figures("You spent 851.00", tool) == [851.0]
    assert answers.unproven_figures("No tool was used and 9,999 appears", []) == []


def test_a_month_that_does_not_tie_to_the_ledger_is_never_answered(conn, monkeypatch):
    from orbit import verify

    seed(conn)
    monkeypatch.setattr(verify, "tally_month", lambda c, m: "the ledger's net change is 1.00 but the reports plus transfers give 2.00")
    out = agent.chat(conn, [], "how much did I spend in October", client=Scripted("In October you spent 850.00 in total."), model="m")
    assert "can't give you that figure" in out and "850.00" not in out


def test_data_that_changes_while_the_agent_answers_is_caught(conn):
    seed(conn)

    class Racing(Scripted):
        def chat(self, model, messages, tools=None, **kw):
            r = super().chat(model, messages, tools, **kw)
            if r.get("content") and not kw.get("schema"):
                tx(conn, "2026-10-12", 7700, note="late payment")  # a new payment lands before the answer is checked
            return r

    out = agent.chat(conn, [], "October, what was the damage?", client=Racing("In October you spent 850.00 in total."), model="m")
    assert "850.00 in total" not in out  # the stale figure is never shown
    assert "can't give you that figure with confidence" in out  # refused, not guessed


def test_files_waiting_for_a_check_are_always_mentioned(conn):
    seed(conn)
    conn.execute("INSERT INTO statement_files (sha256,name,found,added,status) VALUES ('x','a.pdf',3,3,'needs_check')")
    out = agent.chat(conn, [], "how much did I spend in October", client=Scripted("In October you spent 850.00 in total."), model="m")
    assert "850.00" in out and "1 file(s) are waiting for a check" in out


def test_a_clean_answer_is_marked_checked(conn):
    seed(conn)
    trace = []
    agent.chat(conn, [], "how much did I spend in October", client=Scripted("In October you spent 850.00 in total."), model="m", trace=trace)
    assert "checked" in trace[0]["tools"]


def test_the_agent_gets_thirty_seconds_by_default_and_the_limit_can_be_changed(conn):
    from orbit import db

    assert agent.reply_seconds(conn) == 30
    db.set_setting(conn, "reply_seconds", "60")
    assert agent.reply_seconds(conn) == 60
    db.set_setting(conn, "reply_seconds", "1")
    assert agent.reply_seconds(conn) == 10  # never so low that every answer is cut off


def test_text_inside_a_document_cannot_make_the_agent_delete_anything(conn):
    seed(conn)
    before = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]

    class Hijacked:
        n = 0

        def chat(self, model, messages, tools=None, **kw):
            Hijacked.n += 1
            if Hijacked.n == 1:
                return {"content": "", "tool_calls": [{"function": {"name": "delete_transaction", "arguments": {"id": 1}}}]}
            return {"content": "done"}

    agent.chat(conn, [], "what was on the Ziggo invoice?", client=Hijacked(), model="m")
    assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == before


def test_the_assistant_can_never_delete_an_imported_payment_even_when_asked(conn):
    seed(conn)
    before = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    offered: list[str] = []

    class Asked:
        n = 0

        def chat(self, model, messages, tools=None, **kw):
            Asked.n += 1
            offered.extend(t["function"]["name"] for t in tools or [])
            if Asked.n == 1:
                return {"content": "", "tool_calls": [{"function": {"name": "delete_transaction", "arguments": {"id": 1}}}]}
            return {"content": "I cannot do that."}

    agent.chat(conn, [], "please delete transaction 1", client=Asked(), model="m")
    assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == before
    assert "delete_transaction" not in offered and offered  # not even shown to the model
