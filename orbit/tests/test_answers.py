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


def test_when_the_agent_is_too_slow_the_exact_code_answer_takes_over(conn):
    seed(conn)
    r = ask(conn, "How much did I spend last month?")
    assert "September 2026" in r and "120.00" in r
    assert "1,300.00" in ask(conn, "how much did I spend in October") or "800.00" in ask(conn, "how much did I spend in October")
    assert "50.00" in ask(conn, "how much did I spend on groceries in October?")


def test_default_month_is_the_newest_month_with_data(conn):
    seed(conn)
    assert "October 2026" in ask(conn, "How much did I spend?")


def test_income_and_trend_and_missing_month(conn):
    seed(conn)
    assert "3,000.00" in ask(conn, "what was my income in October?")
    assert "September 2026" in ask(conn, "show me the trend")
    assert "don't have March" in ask(conn, "how much did I spend in March?")


def test_a_statement_or_an_opinion_question_is_not_answered_by_rules(conn):
    seed(conn)
    assert answers.answer(conn, "I spent 100 on food") is None
    assert answers.answer(conn, "should I spend less on groceries?") is None
    assert answers.answer(conn, "what do you make of my finances overall?") is None


def test_regular_and_upcoming_and_empty_database(conn):
    assert "No payments yet" in ask(conn, "how much did I spend?")
    assert answers.answer(conn, "what are my regular payments?")
    assert answers.answer(conn, "what is coming up?")


def test_instant_answers_work_even_when_the_model_server_is_off(conn, monkeypatch):
    from kit import llm

    seed(conn)
    monkeypatch.setattr(llm.OllamaClient, "_call", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Ollama is not running")))
    assert "120.00" in agent.chat(conn, [], "How much did I spend last month?")


def test_the_agent_answers_when_its_figures_match_the_tools(conn):
    seed(conn)
    reply = "In October you spent 850.00 in total."  # 500 groceries... see seed: 50.00 + 800.00
    out = agent.chat(conn, [], "October, what was the damage?", client=Scripted(reply), model="m")
    assert out.startswith(reply) and "NOT PROVEN" in out  # no statement backs this invented data, and the answer says so


def test_an_agent_answer_with_a_figure_no_tool_returned_is_never_shown(conn):
    seed(conn)
    out = agent.chat(conn, [], "how much did I spend in October", client=Scripted("In October you spent 1,234.56 in total."), model="m")
    assert "1,234.56" not in out and "850.00" in out  # replaced by the exact answer


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
    out = ask(conn, "how much did I spend in October?")  # the code answer is held to the same check
    assert "can't give you that figure" in out


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
    assert "can't give you that figure with confidence" in out  # this wording is not one code can answer exactly, so it is refused, not guessed
    assert "927.00" in agent.chat(
        conn, [], "how much did I spend in October", client=Racing("unused"), model="m"
    )  # a recognised question gets the fresh exact answer


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


def test_a_recognised_question_is_answered_by_code_without_ever_calling_the_model(conn):
    seed(conn)

    class Forbidden:
        def chat(self, *a, **kw):
            raise AssertionError("the model must not be used for a recognised question")

    trace: list = []
    out = agent.chat(conn, [], "how much did I spend in October", client=Forbidden(), model="m", trace=trace)
    assert "850.00" in out and trace[0]["agent"] == "instant" and "checked" in trace[0]["tools"]
    h: list = []
    agent.chat(conn, h, "how much did I spend in October", client=Forbidden(), model="m")
    assert [m["role"] for m in h] == ["user", "assistant"]  # and the conversation still remembers it
