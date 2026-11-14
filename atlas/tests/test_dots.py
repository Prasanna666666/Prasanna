from atlas import dots

TODAY = "2026-11-14"


def doc(kind, **k):
    return {"src": "documents", "kind": kind, "title": k.pop("title", kind), "date": "2026-10-01", **k}


def pay(amount, when, text, direction="expense"):
    return {"src": "finance", "kind": "payment", "amount": amount, "date": when, "text": text, "direction": direction}


def test_a_bill_seen_in_a_mail_and_its_attachment_is_one_event_and_the_bank_payment_settles_it():
    bill = {"party": "Ziggo", "reference": "INV-7", "amount": 60.5, "currency": "EUR", "due": "2026-11-20"}
    items = [doc("invoice", id=1, title="Internet bill", **bill), doc("invoice", id=2, title="Internet bill", **bill)]
    out = dots.agenda(items, TODAY)
    assert [(e["title"], e["sources"], e["state"]) for e in out["events"]] == [("Internet bill", 2, "open")]
    paid = dots.agenda([*items, pay(60.5, "2026-11-10", "SEPA Ziggo Nederland klantnr 9")], TODAY)
    assert paid["events"] == [] and paid["left_out"]["settled"] == 2


def test_the_same_amount_to_somebody_else_does_not_settle_a_bill():
    items = [doc("invoice", id=1, party="Eneco", amount=112.3, due="2026-11-18"), pay(112.3, "2026-11-12", "Albert Heijn")]
    assert [e["state"] for e in dots.agenda(items, TODAY)["events"]] == ["open"]


def test_a_receipt_with_the_reference_settles_it_and_an_old_unpaid_bill_is_overdue():
    items = [
        doc("invoice", id=1, party="Eneco", reference="E-1", amount=10.0, due="2026-11-18"),
        doc("receipt", id=2, party="Eneco", reference="E-1", amount=10.0),
    ]
    assert dots.agenda(items, TODAY)["events"] == []
    late = dots.agenda([doc("invoice", id=3, party="Landlord", amount=1100.0, due="2026-11-08")], TODAY)["events"]
    assert late[0]["state"] == "overdue" and late[0]["days"] == -6


def test_a_follow_up_is_done_when_a_newer_report_exists_and_a_policy_is_renewed_by_a_newer_one():
    items = [doc("medical", id=1, followup="2026-11-20", date="2026-05-01"), doc("medical", id=2, date="2026-11-19")]
    assert dots.agenda(items, TODAY)["events"] == [] and dots.agenda(items, TODAY)["left_out"]["done"] == 1
    policy = [
        doc("insurance", id=1, party="Centraal Beheer", end="2026-12-31", date="2025-12-01"),
        doc("insurance", id=2, party="Centraal Beheer", end="2027-12-31", date="2026-11-01"),
    ]
    out = dots.agenda(policy, TODAY)
    assert out["events"] == [] and out["left_out"]["renewed"] == 1  # the old policy is replaced; the new one ends beyond the window


def test_a_trip_carries_what_it_cost_and_half_understood_bills_are_counted_not_shown():
    trip = {"src": "documents", "kind": "trip", "title": "Lisbon", "date": "2026-11-10", "end": "2026-11-20", "photos": 12, "documents": 3}
    out = dots.agenda([trip, pay(80.0, "2026-11-12", "Cafe"), pay(120.0, "2026-11-13", "Hotel"), pay(5.0, "2026-12-01", "Later")], TODAY)
    assert out["events"][0]["subtitle"] == "3 documents · spent 200.00 · 12 photos"
    assert dots.agenda([doc("invoice", id=1, due="2026-11-20")], TODAY)["left_out"]["incomplete"] == 1


def test_a_matter_read_as_a_whole_gives_its_next_step_whatever_it_is():
    item = {
        "src": "documents",
        "kind": "matter",
        "id": 4,
        "title": "Roof repair",
        "open": True,
        "due": "2026-11-20",
        "next": "Pay the second instalment",
        "status": "half paid",
    }
    out = dots.agenda([item], "2026-11-14")["events"]
    assert [(e["title"], e["date"], e["subtitle"]) for e in out] == [("Roof repair", "2026-11-20", "Pay the second instalment · half paid")]
    assert dots.agenda([{**item, "open": False}], "2026-11-14")["events"] == []
