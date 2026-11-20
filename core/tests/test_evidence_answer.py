"""Criteria 4, 5, 9 and 15: exact citations that fail closed, deterministic figure and date checks, honest language disclosure, and explicit failure states."""

from __future__ import annotations

import pytest
from conftest import CORPUS, DOC_PAGE1, DOC_TEXT, DUTCH_TEXT, MAIL_BODY, FixtureStore, World, evidence, grant, request

from atlas_core.answer import AnswerInput, build_envelope
from atlas_core.contracts import validate
from atlas_core.evidence import CitationError, StoredSource, check_citation, resolve
from atlas_core.gate import ContextBuilder
from atlas_core.policy import PolicyEngine
from atlas_core.rules import Rules, load_rules
from atlas_core.values import LanguageIn

DOC, DOCNL, MAIL = CORPUS[0], CORPUS[1], CORPUS[2]
STORE = FixtureStore()
PAGE1 = {"kind": "page", "page": 1}
PAGE2 = {"kind": "page", "page": 2}


def _item(draft: str, citations: list, requested=("documents",), **extra) -> AnswerInput:
    return AnswerInput("task0001", draft, citations, list(requested), [], [c["evidence"] for c in citations], **extra)


@pytest.mark.criterion(4)
def test_a_citation_resolves_to_the_exact_text_by_page_block_message_part_and_span():
    assert resolve(evidence(DOC, 0, len(DOC_PAGE1), PAGE1), STORE) == DOC_PAGE1
    assert resolve(evidence(DOC, len(DOC_PAGE1) + 1, len(DOC_TEXT), PAGE2), STORE) == "Payment received on 2026-03-14."
    assert resolve(evidence(DOC, 0, len(DOC_PAGE1), {"kind": "block", "block": 0}), STORE) == DOC_PAGE1
    body_start = MAIL.parts["body"][0]
    assert resolve(evidence(MAIL, body_start, len(MAIL.text), {"kind": "message_part", "message_part": "body"}), STORE) == MAIL_BODY
    assert check_citation({"evidence": evidence(DOC, 0, len(DOC_PAGE1), PAGE1), "quote": "1250.50"}, STORE) == DOC_PAGE1


@pytest.mark.criterion(4)
@pytest.mark.criterion(15)
def test_offsets_are_unicode_characters_so_any_language_resolves_the_same_in_every_client():
    start = DUTCH_TEXT.index("支払い")
    assert resolve(evidence(DOCNL, start, start + 5), STORE) == "支払い期限"
    assert check_citation({"evidence": evidence(DOCNL, 0, 14), "quote": "Totaal bedrag"}, STORE).startswith("Totaal")


@pytest.mark.criterion(4)
@pytest.mark.parametrize(
    ("make", "reason"),
    [
        (lambda: {**evidence(DOC, 0, 10), "version_sha256": "0" * 64}, "stale"),
        (lambda: {**evidence(DOC, 0, 10), "source_id": "missing01"}, "unresolvable"),
        (lambda: {**evidence(DOC, 0, 10), "source_type": "mail"}, "type_mismatch"),
        (lambda: evidence(DOC, 0, len(DOC_TEXT) + 5), "out_of_range"),
        (lambda: evidence(DOC, 5, 5), "out_of_range"),
        (lambda: evidence(DOC, 0, len(DOC_PAGE1) + 10, PAGE1), "out_of_range"),  # crosses into page 2
        (lambda: evidence(DOC, 0, 10, {"kind": "page", "page": 3}), "locator_mismatch"),
        (lambda: evidence(DOC, 0, 10, {"kind": "message_part", "message_part": "body"}), "locator_mismatch"),
    ],
)
def test_a_citation_that_does_not_hold_fails_closed(make, reason):
    with pytest.raises(CitationError) as error:
        resolve(make(), STORE)
    assert error.value.reason == reason


@pytest.mark.criterion(4)
def test_a_changed_source_makes_every_old_citation_stale_and_a_wrong_quote_fails():
    ref = evidence(DOC, 0, len(DOC_PAGE1), PAGE1)
    changed = FixtureStore([StoredSource(DOC.source_id, DOC.source_type, DOC_TEXT + " (edited)", page_starts=DOC.page_starts)])
    with pytest.raises(CitationError) as stale:
        resolve(ref, changed)
    assert stale.value.reason == "stale"
    with pytest.raises(CitationError) as quote:
        check_citation({"evidence": ref, "quote": "not in the source"}, STORE)
    assert quote.value.reason == "quote_mismatch"


@pytest.mark.criterion(4)
def test_an_answer_with_a_failed_citation_is_replaced_by_a_plain_refusal(tmp_path):
    for mode in ("bad_quote", "stale", "not_retrieved"):
        w = World(tmp_path / mode, [grant("documents")]) if (tmp_path / mode).mkdir() is None else None
        assert w is not None
        w.model.mode = mode
        record = w.run_new(request())
        answer = w.service.answer(record["task_id"])
        assert (record["state"], record["terminal_reason"]) == ("failed", "citation_failed"), mode
        assert answer["verification"]["status"] == "failed" and answer["verification"]["citation_failures"] == [0]
        assert "1250.50" not in answer["answer"]


@pytest.mark.criterion(5)
def test_a_figure_not_in_the_cited_text_is_not_emitted_as_verified(tmp_path):
    w = World(tmp_path, [grant("documents")])
    w.model.mode = "extra_figure"
    record = w.run_new(request())
    answer = w.service.answer(record["task_id"])
    assert record["state"] == "partially_completed"
    assert answer["verification"]["status"] == "partially_verified" and answer["verification"]["unproven_figures"] == [777.77]
    assert "figures_unproven" in answer["limitations"]


@pytest.mark.criterion(5)
def test_a_figure_that_is_in_the_cited_text_is_verified():
    item = _item("The total due is 1250.50 euro.", [{"evidence": evidence(DOC, 0, len(DOC_PAGE1), PAGE1), "quote": "1250.50"}])
    envelope = build_envelope(item, STORE)
    assert envelope["verification"] == {"status": "verified", "unproven_figures": [], "unproven_dates": [], "citation_failures": []}


@pytest.mark.criterion(5)
def test_numeric_dates_are_checked_too_and_an_uncited_answer_is_never_verified(tmp_path):
    w = World(tmp_path, [grant("documents")])
    w.model.mode = "dates"
    record = w.run_new(request())
    verification = w.service.answer(record["task_id"])["verification"]
    assert verification["unproven_dates"] == ["2026-05-05"] and verification["status"] == "partially_verified"
    w2 = World(tmp_path / "two", [grant("documents")]) if (tmp_path / "two").mkdir() is None else None
    assert w2 is not None
    w2.model.mode = "no_citation"
    plain = w2.service.answer(w2.run_new(request())["task_id"])
    assert plain["verification"]["status"] == "unverified" and plain["verification"]["unproven_figures"] == [1250.5]


@pytest.mark.criterion(15)
def test_language_is_never_claimed_as_supported_until_it_is_measured():
    cited = [{"evidence": evidence(DOC, 0, len(DOC_PAGE1), PAGE1), "quote": "1250.50"}]
    default = build_envelope(_item("The total due is 1250.50 euro.", cited, language=LanguageIn("nl", "nl", 0.9)), STORE)
    assert default["language"]["support_status"] == "unmeasured" and "language_unmeasured" in default["limitations"]
    measured_rules = Rules({**load_rules().raw, "language": {"measured": ["nl"], "low_confidence_below": 0.5}})
    measured = build_envelope(_item("The total due is 1250.50 euro.", cited, language=LanguageIn("nl", "nl", 0.9)), STORE, measured_rules)
    assert measured["language"]["support_status"] == "measured" and "language_unmeasured" not in measured["limitations"]


@pytest.mark.criterion(15)
@pytest.mark.parametrize(
    ("language", "limitation"),
    [(LanguageIn("ja", "ja", 0.9, path_unsupported=True), "language_unsupported"), (LanguageIn("nl", "nl", 0.2), "low_confidence")],
)
def test_an_unsupported_path_or_low_confidence_is_surfaced_and_caps_the_verification(language, limitation):
    cited = [{"evidence": evidence(DOC, 0, len(DOC_PAGE1), PAGE1), "quote": "1250.50"}]
    envelope = build_envelope(_item("The total due is 1250.50 euro.", cited, language=language), STORE)
    assert envelope["language"]["support_status"] == "unsupported" and limitation in envelope["limitations"]
    assert envelope["verification"]["status"] == "partially_verified"
    validate("AnswerEnvelope", envelope)


@pytest.mark.criterion(9)
def test_the_model_being_unavailable_is_a_plain_failure_not_a_completed_task(tmp_path):
    w = World(tmp_path, [grant("documents")])
    w.model.mode = "unavailable"
    record = w.run_new(request())
    errors = [e["error"] for e in w.store.events_after(record["task_id"], 0) if e["type"] == "error"]
    assert (record["state"], record["terminal_reason"]) == ("failed", "model_unavailable")
    assert errors[0]["code"] == "model_unavailable" and errors[0]["retryable"] is True


@pytest.mark.criterion(9)
def test_only_a_verified_answer_completes_and_anything_less_is_partial_or_failed(tmp_path):
    states = {}
    for mode in ("ok", "extra_figure", "no_citation", "bad_quote"):
        w = World(tmp_path / mode, [grant("documents")]) if (tmp_path / mode).mkdir() is None else None
        assert w is not None
        w.model.mode = mode
        states[mode] = w.run_new(request())["state"]
    assert states == {"ok": "completed", "extra_figure": "partially_completed", "no_citation": "partially_completed", "bad_quote": "failed"}


@pytest.mark.criterion(9)
def test_context_truncation_and_partial_work_are_disclosed_never_silent():
    decision, token = PolicyEngine(__import__("atlas_core.policy", fromlist=["InMemoryGrants"]).InMemoryGrants([grant("documents")])).decide(
        ["documents"], __import__("conftest").T0
    )
    assert token is not None and decision["decision"] == "allow"
    tiny = Rules({**load_rules().raw, "limits": {**load_rules().raw["limits"], "context_chars": 20}})
    from conftest import T0, passage

    context = ContextBuilder(tiny).build(token, "q", [passage(DOC, 0, 10, PAGE1), passage(DOC, 0, len(DOC_PAGE1), PAGE1)], T0)
    assert context.truncated and len(context.passages) == 1
    envelope = build_envelope(_item("answer", [], truncated=True, partial=True), STORE)
    assert {"context_truncated", "partial_work"} <= set(envelope["limitations"])


@pytest.mark.criterion(9)
def test_a_denied_task_answers_in_plain_words_that_nothing_was_searched(tmp_path):
    w = World(tmp_path, [])
    answer = w.service.answer(w.run_new(request(["documents", "mail"]))["task_id"])
    assert answer["answer"].startswith("Nothing was searched") and {n["source_type"] for n in answer["not_searched"]} == {"documents", "mail"}
