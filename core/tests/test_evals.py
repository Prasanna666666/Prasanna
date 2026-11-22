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

SET_SHA256 = "0937684f694d527d2d8b6d833eb59b2b1ee174b3ae96b1a90dda6b6cfc0a48f7"
REQUIRED = {"answerable", "abstention", "contradictory", "stale", "hallucination", "citation", "injection", "cross_domain"}


@pytest.fixture(scope="module")
def report() -> dict:
    return harness.run()


def test_the_set_is_locked_so_a_change_must_be_a_new_version():
    assert harness.set_sha256() == SET_SHA256 and json.loads(harness.SET_FILE.read_text())["version"] == "1"


def test_every_case_behaves_as_specified_through_the_real_pipeline(report):
    assert report["failed_cases"] == [] and report["answer_quality"]["pass_rate"] == 1.0


def test_the_set_covers_english_dutch_and_non_latin_scripts_and_every_required_category(report):
    assert {"en", "nl"} <= set(report["set"]["languages"]) and {"cyrillic", "devanagari", "han_kana"} <= set(report["set"]["scripts"])
    assert set(report["answer_quality"]["by_category"]) >= REQUIRED
    assert report["not_applicable"] and report["not_applicable"][0]["category"] == "tool_selection"


def test_retrieval_and_answer_quality_are_reported_separately_per_language_and_script(report):
    assert set(report["retrieval_quality"]) == {"by_language", "by_script", "top_k"} and "by_category" in report["answer_quality"]
    assert report["retrieval_quality"]["by_language"]["nl"]["recall"] == 1.0 and report["retrieval_quality"]["by_script"]["devanagari"]["recall"] == 1.0


def test_a_known_retrieval_gap_is_reported_not_hidden_and_the_case_still_passes_as_a_gap(report):
    assert [g["id"] for g in report["known_gaps"]] == ["ja-total"]
    assert report["retrieval_quality"]["by_script"]["han_kana"]["recall"] == 0.0  # the gap shows in the retrieval numbers, apart from answer quality


def test_the_report_states_what_it_does_not_measure(report):
    label = report["label"]
    assert "scripted" in label["model"] and "NOT real-model" in label["meaning"] and "target-Mac" in label["meaning"]


def test_injection_hallucination_wrong_quote_and_stale_are_caught_not_presented_as_grounded(report):
    # the outcomes are checked by the cases themselves; here we pin the totals so a weakened check cannot go unnoticed
    assert report["answer_quality"]["outcomes"] == {"grounded": 8, "no_evidence": 1, "ungrounded": 4, "rejected": 1}
