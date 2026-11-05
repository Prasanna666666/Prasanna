from orbit import agent, answers
from tests.test_tally import tx


class NoModel:
    def chat(self, *a, **k):
        raise AssertionError("the model must not be used for a question like this")


def ask(conn, q):
    return agent.chat(conn, [], q, client=NoModel(), model="m")


def seed(conn):
    tx(conn, "2026-09-03", 12000, cat="groceries", note="Albert Heijn")
    tx(conn, "2026-10-04", 5000, cat="groceries", note="Albert Heijn")
    tx(conn, "2026-10-09", 80000, cat="rent", note="Huur")
    tx(conn, "2026-10-25", 300000, kind="income", cat="salary", note="Acme salary")


def test_spending_questions_are_answered_exactly_without_the_model(conn):
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
