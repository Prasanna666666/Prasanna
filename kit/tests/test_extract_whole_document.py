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
    assert got == {"kind": "contract", "title": "Lease", "apps": [], "partial": True}
    assert model.calls.count("full") == 2 and model.calls[-1] == "kind-only"  # two tries of the full question, then the smaller one


def test_a_long_medical_document_says_which_part_of_it_is_being_read():
    said = []
    text = "Hemoglobine 8,4 mmol/L 7,5 - 10,0\n" * 800

    class Model:
        def chat(self, model, messages, **kw):
            return {"content": json.dumps({"values": [], "medicines": [], "follow_up": ""})}

    extract.medical_details(Model(), "m", "report.pdf", text, said.append)
    assert len(said) > 1 and said[0] == f"report.pdf: reading part 1 of {len(said)}"


def test_the_model_failing_says_why_and_never_with_anything_from_the_text():
    import pytest

    class Nothing:
        def chat(self, model, messages, **kw):
            return {"content": ""}

    class Cut:
        def chat(self, model, messages, **kw):
            return {"content": '{"kind": "invoice", "title": "Bank statement Jan'}

    class Empty:
        def chat(self, model, messages, **kw):
            return {"content": "{}"}

    for client, reason in (
        (Nothing(), "the model returned nothing"),
        (Cut(), "the model's answer was cut off or not valid"),
        (Empty(), "the model's answer was empty"),
    ):
        with pytest.raises(extract.Unclear) as why:
            extract._ask(client, "m", "system", "Bank statement of Jan Jansen", {})
        assert str(why.value) == reason and "Jansen" not in str(why.value)


def test_the_text_for_the_model_loses_control_characters_but_keeps_every_script():
    dirty = "Aadhaar\x00 card\x07\n\tनाम: प्रसन्ना \udc80 Name: Prasanna\r\n"
    assert extract.clean(dirty) == "Aadhaar card\n\tनाम: प्रसन्ना  Name: Prasanna\r\n"


def test_the_model_describes_the_file_freely_and_marks_only_the_apps_that_are_declared():
    seen = {}

    class Model:
        def chat(self, model, messages, schema=None, **kw):
            seen["prompt"], seen["schema"] = messages[0]["content"], schema
            return {"content": json.dumps({"kind": "Aadhaar identity card", "title": "Aadhaar", "apps": ["identity", "wallet"]})}

    declared = {"wallet": "money and payments", "garden": "the garden"}
    got = extract.classify(Model(), "m", "id.pdf", "Aadhaar card " * 30, declared)
    assert got["kind"] == "Aadhaar identity card"  # whatever the model calls it: there is no list to choose from, nothing is refused for being unknown
    assert got["apps"] == ["wallet"]  # "identity" is not a declared app: dropped
    assert "enum" not in seen["schema"]["properties"]["kind"] and seen["schema"]["properties"]["apps"]["items"]["enum"] == ["wallet", "garden"]
    assert "wallet: money and payments" in seen["prompt"] and "garden: the garden" in seen["prompt"]
    for word in ("invoice", "payslip", "bank_statement", "medical", "ticket"):
        assert word not in seen["prompt"]  # no kind of document is named in the question


def test_when_the_larger_questions_fail_the_smallest_one_still_sorts_the_file():
    class Stubborn:
        def __init__(self):
            self.sizes = []

        def chat(self, model, messages, schema=None, **kw):
            self.sizes.append(len(schema["properties"]))
            if len(schema["properties"]) > 2:
                return {"content": "{cut off"}  # the full and the brief question fail
            return {"content": json.dumps({"kind": "circuit design"})}

    model = Stubborn()
    got = extract.classify(model, "m", "a.vhd", "entity adder is port ( a : in bit ); " * 30)
    assert got["kind"] == "circuit design" and got["partial"] is True
    assert model.sizes[-1] == 2  # the last look asked only for the kind and the apps


def test_the_model_also_sees_the_lines_with_figures_from_the_middle_of_a_long_document():
    filler = "\n".join(f"line {i} of ordinary words and nothing else" for i in range(400))
    middle = filler + "\nTotal to pay 1.234,56 EUR\nDue date 2026-03-15\n" + filler
    text = "Invoice start\n" + "x " * 2000 + middle + "\n" + "y " * 1000 + "\nend of the document"
    shown = extract.sample_of(text)
    assert "1.234,56" in shown and "2026-03-15" in shown  # neither at the start nor at the end, yet shown
    assert len(shown) < extract.HEAD_CHARS + extract.TAIL_CHARS + extract.MIDDLE_CHARS + 50
    assert extract.sample_of("short") == "short"
    assert "line 7 of ordinary words" not in extract.key_passages(filler)  # lines without figures are left out
