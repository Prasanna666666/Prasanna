"""Every common way of phrasing a time is understood the same way, exactly, without asking the model."""

from datetime import date

import pytest

from aperture.agent import phrasebook
from aperture.agent.schema import plan_from_raw
from aperture.search.dates import resolve

TODAY = date(2026, 11, 4)


def span(message):
    hit = phrasebook.match(message)
    assert hit is not None, message
    return resolve(plan_from_raw({"intent": "find", "date": hit[1]})[0].date, TODAY)


@pytest.mark.parametrize(
    "message, expected",
    [
        (
            "Pictures from the last 3 months",
            (date(2026, 8, 4), date(2026, 11, 5)),
        ),  # exactly three months back, up to and including today
        ("pics from the past two weeks", (date(2026, 10, 21), date(2026, 11, 5))),
        ("what did I shoot in the last 10 days", (date(2026, 10, 25), date(2026, 11, 5))),
        ("photos from the last 2 years", (date(2024, 11, 4), date(2026, 11, 5))),
        ("show me photos from 2 months back", (date(2026, 9, 1), date(2026, 10, 1))),  # that one month
        ("a month ago", (date(2026, 10, 1), date(2026, 11, 1))),
        ("pics from three months ago", (date(2026, 8, 1), date(2026, 9, 1))),
        ("a year ago", (date(2025, 1, 1), date(2026, 1, 1))),
        ("photos from last month", (date(2026, 10, 1), date(2026, 11, 1))),
        ("yesterday", (date(2026, 11, 3), date(2026, 11, 4))),
        ("in March 2025", (date(2025, 3, 1), date(2025, 4, 1))),
        ("pictures from 2019", (date(2019, 1, 1), date(2020, 1, 1))),
        ("this year", (date(2026, 1, 1), date(2027, 1, 1))),
    ],
)
def test_known_phrasings_get_their_exact_meaning(message, expected):
    assert span(message) == expected


def test_the_window_and_the_single_period_are_different_things():
    assert span("the last 3 months") != span("3 months ago")


def test_text_without_a_time_matches_nothing_and_the_word_may_is_not_a_month():
    assert phrasebook.match("cats on the sofa") is None
    assert phrasebook.match("I may show you more") is None


def test_an_unknown_phrasing_gets_the_closest_known_phrases_as_examples_for_the_model():
    text = phrasebook.examples_text("anything from the last few weeks please")
    assert "Similar phrases and what they mean" in text and "weeks" in text
    assert phrasebook.examples_text("zzz qqq") == ""


def test_the_date_step_uses_the_phrasebook_before_it_asks_the_model(tmp_path, monkeypatch):
    from aperture.agent.llm import OllamaClient
    from aperture.bootstrap import AppContext
    from aperture.config import Paths

    asked = []
    monkeypatch.setattr(
        OllamaClient,
        "_request",
        lambda self, path, payload=None: asked.append(payload) or {"message": {"content": '{"phrase": ""}'}},
    )
    monkeypatch.setenv("APERTURE_ALLOW_INTERNAL", "1")
    paths = Paths(tmp_path / "Expansion")
    paths.ensure()
    step = AppContext(paths).service()._date_step
    phrase, spec = step("pictures from the last 3 months")
    assert phrase == "the last 3 months" and spec.ago == 3 and spec.unit == "month" and spec.through is True and not asked
