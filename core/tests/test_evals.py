"""WP3.4d: the evaluation set is versioned and locked, runs through the real pipeline, covers EN, NL and non-Latin scripts and every required category, reports retrieval and
answer quality separately, and says plainly what it does NOT measure."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

EVALS = Path(__file__).resolve().parents[1] / "evals"
sys.path.insert(0, str(EVALS))

import harness  # noqa: E402

SET_SHA256 = "bb2984d427c1ecf44d7b3fefa000680ea2cdd350f9b4c3d447895a5f51c5b292"
REQUIRED = {"answerable", "abstention", "contradictory", "stale", "hallucination", "citation", "injection", "cross_domain"}


@pytest.fixture(scope="module")
def report() -> dict:
    return harness.run()


def test_the_set_is_locked_so_a_change_must_be_a_new_version():
    assert harness.set_sha256() == SET_SHA256 and json.loads(harness.SET_FILE.read_text())["version"] == "4"


def test_every_case_behaves_as_specified_through_the_real_pipeline(report):
    assert report["failed_cases"] == [] and report["answer_quality"]["pass_rate"] == 1.0


def test_the_set_covers_english_dutch_and_non_latin_scripts_and_every_required_category(report):
    assert {"en", "nl"} <= set(report["set"]["languages"]) and {"cyrillic", "devanagari", "han_kana"} <= set(report["set"]["scripts"])
    assert set(report["answer_quality"]["by_category"]) >= REQUIRED
    assert report["not_applicable"] and report["not_applicable"][0]["category"] == "tool_selection"


def test_retrieval_and_answer_quality_are_reported_separately_per_language_and_script(report):
    assert set(report["retrieval_quality"]) == {"by_language", "by_script", "top_k"} and "by_category" in report["answer_quality"]
    assert report["retrieval_quality"]["by_language"]["nl"]["recall"] == 1.0 and report["retrieval_quality"]["by_script"]["devanagari"]["recall"] == 1.0


def test_unspaced_japanese_is_retrieved_and_cited_and_no_retrieval_gap_remains(report):
    """UC-L22: Japanese has no spaces between words; indexed as overlapping two-character pieces, the question finds its invoice (set v1 recorded
    this case as a known gap with recall 0)."""
    assert report["known_gaps"] == [] and report["retrieval_quality"]["by_script"]["han_kana"]["recall"] == 1.0


def test_the_report_states_what_it_does_not_measure(report):
    label = report["label"]
    assert "scripted" in label["model"] and "NOT real-model" in label["meaning"] and "target-Mac" in label["meaning"]


def test_injection_hallucination_wrong_quote_and_stale_are_caught_not_presented_as_grounded(report):
    # the outcomes are checked by the cases themselves; here we pin the totals so a weakened check cannot go unnoticed
    assert report["answer_quality"]["outcomes"] == {"grounded": 14, "no_evidence": 0, "ungrounded": 7, "rejected": 1}


CASES = {case["id"]: case for case in json.loads(harness.SET_FILE.read_text(encoding="utf-8"))["cases"]}


def test_a_document_mixing_dutch_and_english_is_found_and_cited_from_either_language(report):
    """UC-L22 (language mix): one meeting note written partly in Dutch and partly in English answers an English and a Dutch question."""
    assert {CASES["mixed-en-q"]["language"], CASES["mixed-nl-q"]["language"]} == {"en", "nl"}
    assert not {row["id"] for row in report["failed_cases"]} & {"mixed-en-q", "mixed-nl-q"}
    assert all(CASES[c]["expect"]["cited"] == ["notulen_mixed.txt"] and CASES[c]["gold"] == ["notulen_mixed.txt"] for c in ("mixed-en-q", "mixed-nl-q"))
    assert all(v["recall"] == 1.0 for v in report["retrieval_quality"]["by_language"].values())  # every language in the set, ja and hi included


def test_names_and_units_are_kept_verbatim_from_source_to_passage_quote_and_answer(report):
    """UC-L22 (preserve original language, names and units): the harness fails a case whose passages, cited quote or answer lose a name with
    diacritics or in its own script, or a unit (kWh, m², ₹ with lakh grouping, full-width yen); and every passage of every case is a verbatim part
    of its source, so nothing is case-folded, NFKC-normalised (m² to m2, １２ to 12) or translated on the way to the model."""
    preserved = {text for case in CASES.values() for text in case["expect"].get("preserved", [])}
    assert {"Zoë Ångström-Müller", "85 m²", "1.234,5 kWh", "श्रीमती अनन्या राव", "₹4,52,000", "山田太郎様", "１２，８００円"} <= preserved
    assert report["failed_cases"] == []


def test_a_figure_in_a_decimal_comma_or_unspaced_language_is_checked_exactly(report):
    """UC-L22 / exact figures: 480,99 against a source of 480,00 and 9999円 written straight after kana are both caught (both passed as grounded
    before kit.audit read decimal commas and figures that follow kana); ₹4,52,000 is proven by the same lakh figure."""
    assert CASES["nl-cent-off"]["expect"] == {"outcome": "ungrounded", "cited": ["factuur_nl.txt"], "unproven_figures": [480.99]}
    assert CASES["ja-wrong-figure"]["expect"]["unproven_figures"] == [9999.0] and CASES["hi-lakh"]["expect"]["outcome"] == "grounded"
    assert not {row["id"] for row in report["failed_cases"]} & {"nl-cent-off", "ja-wrong-figure", "hi-lakh"}


def test_an_amount_whose_integer_part_looks_like_a_year_is_checked_through_the_pipeline(report):
    """UC-L22 (review 6098896232): 2026.50 is an amount, not a year. Cited correctly it is grounded; one cent off it is caught as unproven (before
    the fix the year-like integer part was removed and 2026.51 passed as grounded)."""
    assert CASES["year-like-amount"]["expect"]["outcome"] == "grounded"
    assert CASES["year-like-amount-off"]["expect"] == {"outcome": "ungrounded", "cited": ["invoice_year_en.txt"], "unproven_figures": [2026.51]}
    assert not {row["id"] for row in report["failed_cases"]} & {"year-like-amount", "year-like-amount-off"}
