from atlas import crosscheck

MATTER = {"id": 1, "title": "Ziggo internet", "what": "Monthly bill", "open": True, "due": "2026-11-20", "amounts": [{"value": "60,50"}]}
PAYS = [
    {"kind": "payment", "date": "2026-11-10", "amount": 60.5, "direction": "expense", "text": "SEPA Ziggo Nederland klantnr 9"},
    {"kind": "payment", "date": "2026-11-11", "amount": 5.0, "direction": "expense", "text": "Coffee"},
]


def test_an_exact_amount_with_a_real_quote_from_the_payment_settles_it():
    got = crosscheck.judge(
        lambda *a: {"item": 2, "relation": "full", "quote": "Ziggo Nederland"}, MATTER, PAYS
    )  # the payments are numbered closest to the due date first
    assert got["relation"] == "full" and got["amount"] == 60.5 and got["date"] == "2026-11-10" and got["kind"] == "payment"


def test_a_made_up_quote_or_a_different_amount_never_settles_it():
    assert crosscheck.judge(lambda *a: {"item": 2, "relation": "full", "quote": "invented"}, MATTER, PAYS) == {"relation": "none"}
    off = [{**PAYS[0], "amount": 40.0}]
    assert (
        crosscheck.judge(lambda *a: {"item": 1, "relation": "full", "quote": "Ziggo"}, MATTER, off)["relation"] == "part"
    )  # the model said full, the numbers say part


def test_a_model_that_does_not_answer_is_asked_again_later():
    assert crosscheck.judge(lambda *a: None, MATTER, PAYS) is None


def test_numbers_are_read_as_printed():
    assert crosscheck.number("1.234,50 EUR") == 1234.5 and crosscheck.number("60,50") == 60.5 and crosscheck.number("12.5") == 12.5


def test_an_item_from_any_other_app_is_compared_the_same_way():
    trip = [{"kind": "trip", "date": "2026-11-18", "title": "India", "place": "India"}]
    got = crosscheck.judge(lambda *a: {"item": 1, "relation": "related", "quote": "India"}, MATTER, trip)
    assert got == {
        "relation": "related",
        "kind": "trip",
        "title": "India India",
        "date": "2026-11-18",
    }  # no amount, no payment rule: only a real quote is needed
    assert crosscheck.judge(lambda *a: {"item": 1, "relation": "related", "quote": "Nepal"}, MATTER, trip) == {"relation": "none"}
    assert (
        crosscheck.judge(lambda *a: {"item": 1, "relation": "full", "quote": "India"}, MATTER, trip)["relation"] == "related"
    )  # "full" only means something for a payment
