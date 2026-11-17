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


def test_lab_values_far_into_a_long_report_are_read_too_and_a_row_in_the_overlap_is_kept_once():
    filler = "toelichting " * 420  # 5040 characters
    row = "Hemoglobine 8,4 mmol/L 7,5 - 10,0\n"  # printed across the boundary of the first two pieces: both pieces see it
    text = "Uitslag bloedonderzoek.\n" + filler + row + filler + "Glucose 6,4 mmol/L 4,0 - 6,0\n"
    assert extract.WINDOW - extract.OVERLAP < text.index(row) < extract.WINDOW
    hb = {"test": "Hemoglobine", "value": "8,4", "unit": "mmol/L", "range": "7,5 - 10,0"}
    glucose = {"test": "Glucose", "value": "6,4", "unit": "mmol/L", "range": "4,0 - 6,0"}
    model = Model({"values": [hb]}, {"values": [hb, glucose]})
    got = extract.medical_details(model, "m", "b.pdf", text)
    assert sorted(v["test"] for v in got["values"]) == ["Glucose", "Hemoglobine"]
    assert got["complete"] is True and got["unprocessed"] == []


def test_the_same_test_printed_twice_far_apart_is_two_rows():
    hb = {"test": "Hemoglobine", "value": "8,4", "unit": "mmol/L", "range": "7,5 - 10,0"}
    line = "Hemoglobine 8,4 mmol/L 7,5 - 10,0\n"
    text = line + "toelichting " * 1500 + line
    got = extract.medical_details(Model({"values": [hb]}), "m", "b.pdf", text)
    assert [v["test"] for v in got["values"]].count("Hemoglobine") == 2


def test_a_very_long_report_is_read_to_the_end_with_no_cap_on_values_or_medicines():
    lines = [f"Test{i:04d} {i:04d},5 mmol/L" for i in range(300)]
    meds = [f"Medicijn{i:04d} {i:04d} mg" for i in range(80)]
    text = "\n".join(lines + meds)
    wanted = {
        "values": [{"test": f"Test{i:04d}", "value": f"{i:04d},5", "unit": "mmol/L"} for i in range(300)],
        "medicines": [{"name": f"Medicijn{i:04d}", "dose": f"{i:04d} mg"} for i in range(80)],
    }
    got = extract.medical_details(Model(wanted), "m", "big.pdf", text)
    assert len(got["values"]) == 300 and len(got["medicines"]) == 80 and got["complete"] is True


def test_more_than_twelve_pieces_are_all_read():
    text = "Hemoglobine 8,4 mmol/L\n" + "toelichting " * 9000  # about 108,000 characters: more than twelve pieces
    model = Model({"values": []})
    got = extract.medical_details(model, "m", "long.pdf", text)
    assert len(model.shown) == len(extract._windows(text)) > 12
    assert got["complete"] is True


def test_exact_printed_text_is_never_shortened():
    long_name = "Een zeer lange testnaam " * 8
    text = f"{long_name} 8,4 mmol/L"
    got = extract.medical_details(Model({"values": [{"test": long_name.strip(), "value": "8,4", "unit": "mmol/L"}]}), "m", "x", text)
    assert got["values"][0]["test"] == long_name.strip()


def test_a_piece_the_model_cannot_read_is_reported_and_the_rest_is_still_read():
    class FailsOnce:
        def __init__(self):
            self.calls = 0

        def chat(self, model, messages, **kw):
            self.calls += 1
            body = messages[-1]["content"]
            if "FAILHERE" in body and len(body) > 2 * extract.WINDOW // 5:
                return {"content": ""}
            return {"content": json.dumps({"values": [{"test": "Glucose", "value": "6,4"}]})}

    text = "Glucose 6,4 mmol/L\n" + "x " * 2600 + "FAILHERE\n" + "x " * 2600 + "\f" + "y " * 6000
    got = extract.medical_details(FailsOnce(), "m", "p.pdf", text)
    assert [v["test"] for v in got["values"]] == ["Glucose"], "what the good pieces held was kept"
    assert got["complete"] is False and got["unprocessed"]
    failed = got["unprocessed"][0]
    assert failed["from_character"] <= text.index("FAILHERE") < failed["to_character"] and "returned nothing" in failed["reason"]


def test_what_is_not_processed_is_named_with_part_and_page_and_never_called_complete():
    text = ("page one " * 300 + "\f") * 4
    got = extract.medical_details(Model({"values": []}), "m", "p.pdf", text, max_parts=1)
    assert got["complete"] is False
    assert got["unprocessed"] and got["unprocessed"][0]["part"] == 2 and got["unprocessed"][0]["of"] == len(extract._windows(text))
    assert {"from_character", "to_character", "from_page", "to_page", "reason"} <= set(got["unprocessed"][0])


def test_a_piece_that_fails_as_a_whole_is_read_in_halves():
    class OnlyHalves:
        def chat(self, model, messages, **kw):
            if len(messages[-1]["content"]) > 4000:
                return {"content": ""}
            return {"content": json.dumps({"values": [{"test": "Glucose", "value": "6,4"}]})}

    text = "Glucose 6,4 mmol/L " + "toelichting " * 400
    got = extract.medical_details(OnlyHalves(), "m", "h.pdf", text)
    assert got["complete"] is True and got["values"]


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


class _Said:
    def __init__(self, data):
        self.data = data

    def chat(self, model, messages, **kw):
        return {"content": json.dumps(self.data)}


INVOICE = "Factuur 2026-03-02\nFactuurdatum: 2 maart 2026\nBetaal uiterlijk 16 maart 2026\nTotaal 12,50"


def test_a_date_is_kept_only_if_the_document_writes_it_and_its_source_line_is_kept():
    info = {"date": "2026-03-02", "date_quote": "Factuurdatum: 2 maart 2026", "due_date": "2026-03-16", "due_date_quote": "Betaal uiterlijk 16 maart 2026"}
    got = extract.verify_dates(info, INVOICE)
    assert (got["date"], got["due_date"]) == ("2026-03-02", "2026-03-16")
    assert got["date_source"] == "Factuurdatum: 2 maart 2026" and got["due_date_source"] == "Betaal uiterlijk 16 maart 2026"
    assert "date_quote" not in got


@pytest.mark.parametrize("model_said", ["2026-04-30", "2026-02-30", "2026-13-01", "02/03/2026", "yesterday", "", None, 20260302])
def test_a_date_the_document_does_not_write_or_that_is_not_a_calendar_date_is_unknown(model_said):
    got = extract.verify_dates({"date": model_said, "due_date": model_said}, INVOICE)
    assert got["date"] is None and got["due_date"] is None


def test_a_valid_looking_date_with_a_wrong_quote_is_kept_without_a_source():
    got = extract.verify_dates({"date": "2026-03-02", "date_quote": "Datum 1 januari"}, INVOICE)
    assert got["date"] == "2026-03-02" and got["date_source"] == ""


def test_a_due_date_before_the_date_is_dropped():
    text = "Datum 16 maart 2026. Vervaldatum 2 maart 2026."
    got = extract.verify_dates({"date": "2026-03-16", "due_date": "2026-03-02"}, text)
    assert got["date"] == "2026-03-16" and got["due_date"] is None


@pytest.mark.parametrize(
    ("text", "iso"),
    [
        ("12-01-2026", "2026-01-12"),
        ("12.01.2026", "2026-01-12"),
        ("12 januari 2026", "2026-01-12"),
        ("January 12, 2026", "2026-01-12"),
        ("12th Jan 2026", "2026-01-12"),
        ("1 mrt 2026", "2026-03-01"),
    ],
)
def test_dutch_english_and_numeric_dates_are_all_read(text, iso):
    assert extract.verify_dates({"date": iso}, f"Datum: {text}")["date"] == iso


def test_numbers_are_day_first_so_the_other_reading_is_not_accepted():
    assert extract.verify_dates({"date": "2026-01-02"}, "Datum 01/02/2026")["date"] is None  # 1 February, not 2 January: the model's other reading is unknown


def test_the_classifier_returns_only_verified_dates():
    said = {"kind": "invoice", "title": "T", "date": "2026-03-02", "due_date": "2027-01-01", "apps": []}
    got = extract.classify(_Said(said), "m", "f.pdf", INVOICE)
    assert got["date"] == "2026-03-02" and got["due_date"] is None


@pytest.mark.parametrize(
    ("text", "iso"),
    [("Geboren 12 maart 1985", "1985-03-12"), ("Datum 1999-12-31", "1999-12-31"), ("Contract 3.4.1998", "1998-04-03"), ("Born January 5, 1972", "1972-01-05")],
)
def test_dates_before_2000_are_read_too(text, iso):
    assert iso in extract.dates_in(text)
    assert extract.verify_dates({"date": iso}, text)["date"] == iso


def test_a_two_digit_year_is_not_guessed():
    assert extract.dates_in("Datum 12-01-26") == set()
