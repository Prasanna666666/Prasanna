from orbit import agent, answers, llm
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
    from orbit import llm

    seed(conn)
    monkeypatch.setattr(llm.OllamaClient, "_call", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Ollama is not running")))
    assert "120.00" in agent.chat(conn, [], "How much did I spend last month?")


def test_the_agent_answers_when_its_figures_match_the_tools(conn):
    seed(conn)
    reply = "In October you spent 850.00 in total."  # 500 groceries... see seed: 50.00 + 800.00
    out = agent.chat(conn, [], "how much did I spend in October", client=Scripted(reply), model="m")
    assert out == reply


def test_an_agent_answer_with_a_figure_no_tool_returned_is_never_shown(conn):
    seed(conn)
    out = agent.chat(conn, [], "how much did I spend in October", client=Scripted("In October you spent 1,234.56 in total."), model="m")
    assert "1,234.56" not in out and "850.00" in out  # replaced by the exact answer


def test_unproven_figures_ignore_dates_and_small_counts():
    tool = ['{"spent": 850.0, "month": "2026-10", "by_category": [{"category": "rent", "spent": 800.0}]}']
    assert answers.unproven_figures("You spent 850.00 on 2026-10-05, 3 payments, rent 800", tool) == []
    assert answers.unproven_figures("You spent 851.00", tool) == [851.0]
    assert answers.unproven_figures("No tool was used and 9,999 appears", []) == []
