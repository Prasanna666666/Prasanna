from atlas import dots

TODAY = "2026-11-14"


def matter(**kw):
    return {
        "src": "documents",
        "kind": "matter",
        "id": 1,
        "title": "Ziggo internet",
        "what": "Monthly internet bill",
        "open": True,
        "due": "2026-11-20",
        "next": "Pay the bill",
        "status": "unpaid",
        **kw,
    }


def pay(amount, text):
    return {"src": "finance", "kind": "payment", "direction": "expense", "amount": amount, "date": "2026-11-10", "text": text}


def test_a_matter_gives_its_next_step_whatever_it_is():
    out = dots.agenda([matter()], TODAY)["events"]
    assert [(e["title"], e["date"], e["subtitle"], e["state"]) for e in out] == [("Ziggo internet", "2026-11-20", "Pay the bill · unpaid", "open")]
    assert dots.agenda([matter(open=False)], TODAY)["events"] == []
    assert dots.agenda([matter(due="2026-11-08")], TODAY)["events"][0]["state"] == "overdue"


def test_a_matter_the_bank_shows_paid_is_settled_and_an_unrelated_payment_does_not_settle_it():
    m = matter(amounts=[{"label": "total", "value": "60,50", "quote": "x"}])
    paid = dots.agenda([m, pay(60.5, "SEPA Ziggo Nederland klantnr 9")], TODAY)
    assert paid["events"] == [] and paid["left_out"]["settled"] == 1
    assert len(dots.agenda([m, pay(60.5, "Albert Heijn")], TODAY)["events"]) == 1
    assert len(dots.agenda([m, pay(12.0, "Ziggo")], TODAY)["events"]) == 1


def test_a_trip_shows_what_was_spent_while_it_lasted():
    trip = {"src": "documents", "kind": "trip", "title": "India", "date": "2026-11-01", "end": "2026-11-20", "documents": 3}
    out = dots.agenda([trip, pay(80.0, "Cafe"), pay(120.0, "Hotel")], TODAY)["events"]
    assert out[0]["subtitle"] == "3 documents · spent 200.00"
