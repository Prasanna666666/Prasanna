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


def test_a_matter_the_bank_shows_paid_is_settled_and_a_part_payment_is_shown_as_such():
    full = {1: {"relation": "full", "amount": 60.5, "date": "2026-11-10"}}
    out = dots.agenda([matter()], TODAY, settled=full)
    assert out["events"] == [] and out["left_out"]["settled"] == 1
    part = dots.agenda([matter()], TODAY, settled={1: {"relation": "part", "amount": 20.0, "date": "2026-11-10"}})["events"]
    assert "part paid 20.00 on 2026-11-10" in part[0]["subtitle"]
    assert len(dots.agenda([matter()], TODAY, settled={1: {"relation": "none"}})["events"]) == 1


def test_a_trip_shows_what_was_spent_while_it_lasted():
    trip = {"src": "documents", "kind": "trip", "title": "India", "date": "2026-11-01", "end": "2026-11-20", "documents": 3}
    out = dots.agenda([trip, pay(80.0, "Cafe"), pay(120.0, "Hotel")], TODAY)["events"]
    assert out[0]["subtitle"] == "3 documents · spent 200.00"
