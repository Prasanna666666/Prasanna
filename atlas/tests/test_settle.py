from atlas import settle

MATTER = {"id": 1, "title": "Ziggo internet", "what": "Monthly bill", "open": True, "due": "2026-11-20", "amounts": [{"value": "60,50"}]}
PAYS = [
    {"date": "2026-11-10", "amount": 60.5, "direction": "expense", "text": "SEPA Ziggo Nederland klantnr 9"},
    {"date": "2026-11-11", "amount": 5.0, "direction": "expense", "text": "Coffee"},
]


def test_an_exact_amount_with_a_real_quote_from_the_payment_settles_it():
    got = settle.judge(
        lambda *a: {"payment": 2, "relation": "full", "quote": "Ziggo Nederland"}, MATTER, PAYS
    )  # the payments are numbered closest to the due date first
    assert got == {"relation": "full", "amount": 60.5, "date": "2026-11-10"}


def test_a_made_up_quote_or_a_different_amount_never_settles_it():
    assert settle.judge(lambda *a: {"payment": 2, "relation": "full", "quote": "invented"}, MATTER, PAYS) == {"relation": "none"}
    off = [{**PAYS[0], "amount": 40.0}]
    assert (
        settle.judge(lambda *a: {"payment": 1, "relation": "full", "quote": "Ziggo"}, MATTER, off)["relation"] == "part"
    )  # the model said full, the numbers say part


def test_a_model_that_does_not_answer_is_asked_again_later():
    assert settle.judge(lambda *a: None, MATTER, PAYS) is None


def test_numbers_are_read_as_printed():
    assert settle.number("1.234,50 EUR") == 1234.5 and settle.number("60,50") == 60.5 and settle.number("12.5") == 12.5
