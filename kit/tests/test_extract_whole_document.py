"""What is read of a long document, and what is thrown away: nothing the document says may be lost to a cut-off, and nothing it does not say may be kept."""

import json

import pytest

from kit import extract


class Model:
    """Answers from a script; remembers what it was shown."""

    def __init__(self, *answers):
        self.answers, self.shown = list(answers), []

    def chat(self, model, messages, **kw):
        self.shown.append(messages[-1]["content"])
        return {"content": json.dumps(self.answers.pop(0) if len(self.answers) > 1 else self.answers[0])}


def test_a_total_at_the_end_of_a_long_invoice_is_seen_and_verified_against_the_whole_text():
    text = "FACTUUR Ziggo " + "regel met uitleg over de dienst. " * 300 + " Totaal te betalen 60,50 EUR"
    model = Model({"kind": "invoice", "title": "Internet", "party": "Ziggo", "total": "60,50", "currency": "EUR"})
    got = extract.classify(model, "m", "f.pdf", text)
    assert "Totaal te betalen 60,50" in model.shown[0]  # the end of the document was shown, not only the first pages
    assert got["total"] == 60.5 and got["party"] == "Ziggo"


def test_a_party_the_document_does_not_contain_is_dropped_not_kept():
    got = extract.classify(Model({"kind": "invoice", "title": "Bill", "party": "Made Up BV"}), "m", "f.pdf", "FACTUUR Ziggo totaal 60,50")
    assert got["party"] == ""


def test_a_broken_answer_is_asked_again_once_and_then_it_is_unclear_never_other():
    class Flaky:
        def __init__(self):
            self.calls = 0

        def chat(self, *a, **k):
            self.calls += 1
            return {"content": "{not json" if self.calls == 1 else json.dumps({"kind": "receipt", "title": "Bon"})}

    flaky = Flaky()
    assert extract.classify(flaky, "m", "f.pdf", "KASSABON Jumbo")["kind"] == "receipt" and flaky.calls == 2
    with pytest.raises(extract.Unclear):
        extract.classify(Model({}), "m", "f.pdf", "text")


def test_lab_values_far_into_a_long_report_are_read_too_and_a_row_seen_twice_is_kept_once():
    first = "Uitslag bloedonderzoek. Hemoglobine 8,4 mmol/L 7,5 - 10,0\n" + "toelichting " * 700
    second = "Glucose 6,4 mmol/L 4,0 - 6,0\nHemoglobine 8,4 mmol/L 7,5 - 10,0\n"
    text = first + second
    assert len(text) > extract.WINDOW
    hb = {"test": "Hemoglobine", "value": "8,4", "unit": "mmol/L", "range": "7,5 - 10,0"}
    glucose = {"test": "Glucose", "value": "6,4", "unit": "mmol/L", "range": "4,0 - 6,0"}
    model = Model({"values": [hb]}, {"values": [glucose, hb]})
    got = extract.medical_details(model, "m", "b.pdf", text)
    assert sorted(v["test"] for v in got["values"]) == ["Glucose", "Hemoglobine"]  # the second piece's value is not lost, the repeated one is not doubled


def test_a_document_the_full_question_failed_on_gets_a_second_look_with_a_smaller_question():
    class TwoStep:
        def __init__(self):
            self.calls = []

        def chat(self, model, messages, schema=None, **kw):
            self.calls.append("kind-only" if schema and "party" not in schema["properties"] else "full")
            if "kind-only" in self.calls[-1]:
                return {"content": json.dumps({"kind": "contract", "title": "Lease"})}
            return {"content": "{broken"}

    model = TwoStep()
    got = extract.classify(model, "m", "f.pdf", "HUUROVEREENKOMST tussen partijen " * 20)
    assert got == {"kind": "contract", "title": "Lease", "partial": True}
    assert model.calls.count("full") == 2 and model.calls[-1] == "kind-only"  # two tries of the full question, then the smaller one
