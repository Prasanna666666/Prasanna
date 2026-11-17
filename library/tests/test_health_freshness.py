"""Health says how old the latest report is, never colours an old report green, never says 'all within range', and says when no medicine records were found (review item P-1)."""

from pathlib import Path

HEALTH = (Path(__file__).resolve().parents[1] / "src" / "library" / "static" / "healthtravel.js").read_text(encoding="utf-8")
DESIGN = (Path(__file__).resolve().parents[2] / "design" / "design.css").read_text(encoding="utf-8")


def test_an_old_report_is_neutral_but_a_result_outside_its_range_keeps_its_warning():
    assert "`hero healthhero ${out ? 'warn' : stale ? 'stale' : 'good'}`" in HEALTH
    assert "STALE_MONTHS = 3" in HEALTH
    assert ".healthhero.stale" in DESIGN


def test_wording_is_neutral_and_gives_the_report_age():
    assert "inside the printed ranges" in HEALTH and "outside the printed range" in HEALTH
    assert "All within range" not in HEALTH and "to look at" not in HEALTH
    assert "(${ago(age)})" in HEALTH


def test_missing_medicine_records_are_said_so():
    assert "no medicine records found" in HEALTH
