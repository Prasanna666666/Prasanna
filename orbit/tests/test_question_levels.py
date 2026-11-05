"""Questions from simple to hard: code answers only what it fully understands, exactly; everything else goes to the model.

The expected figures are known by construction (see `seed`): September 120.00; October spent 850.00 (rent 800.00, groceries 50.00), money in 3,000.00.
A wrong answer to a different question than the one asked is worse than no instant answer, so the hard cases must NOT be answered by code."""

import time

import pytest

from orbit import answers
from tests.test_answers import seed

ANSWERED = [
    # level 1: plain
    ("how much did I spend last month?", ["€120.00", "September 2026"]),
    ("how much did I earn last month?", ["No money in for September 2026"]),
    # level 2: other wording and an explicit month
    ("How much did I spend in October?", ["€850.00", "October 2026"]),
    ("what did I spend in october 2026", ["€850.00"]),
    ("what was my income in October", ["€3,000.00"]),
    # level 3: one filter
    ("how much did I spend on groceries in October?", ["groceries €50.00"]),
    ("show me my regular payments", []),
]

HAND_TO_THE_MODEL = [
    # level 3: a condition code does not apply (a merchant, a period it does not know)
    "how much to Albert Heijn in September",
    "top merchants in October",
    "biggest expense in October",
    "total spent this year",
    "how much did I spend last week?",
    "how much did I spend on groceries and rent in October?",
    # level 4: comparing or combining periods or figures
    "did I spend more in October than in September?",
    "how much did I spend in October and September together",
    "compare October and September spending",
    "what is the difference between my income and spending in October",
    "how much money came in last month",
    # level 5: reasoning and advice
    "why was October more expensive than September?",
    "what should I cut to save 500 a month?",
    "summarise my year",
    "am I on track for my goals",
    "can I afford a 20000 car",
    # not a money question, or not a question at all
    "what is the capital of France",
    "hello",
    "remind me to call the dentist",
    "I spent 100 on food",
]


@pytest.mark.parametrize(("question", "expect"), ANSWERED)
def test_a_question_code_fully_understands_is_answered_exactly_and_fast(conn, question, expect):
    seed(conn)
    started = time.perf_counter()
    reply = answers.answer(conn, question, [])
    elapsed = time.perf_counter() - started
    assert reply, question
    for text in expect:
        assert text in reply, (question, reply)
    assert elapsed < 0.5, f"{question!r} took {elapsed:.2f} s"


@pytest.mark.parametrize("question", HAND_TO_THE_MODEL)
def test_a_question_with_a_condition_code_does_not_apply_goes_to_the_model_instead_of_being_answered_wrongly(conn, question):
    seed(conn)
    assert answers.answer(conn, question, []) is None, question
