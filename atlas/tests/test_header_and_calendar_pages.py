"""Review items F7 and F8: the header shows one summary chip instead of one chip per app (which wrapped and pushed 'Read new files' out of view), and an empty calendar month is one line with a jump to the next month that has something."""

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "src" / "atlas" / "static"
JS = (STATIC / "atlas.js").read_text(encoding="utf-8")
CSS = (STATIC / "atlas.css").read_text(encoding="utf-8")


def test_the_header_has_one_summary_chip_for_the_apps():
    assert "parts not running" in JS and "All parts running" in JS
    assert "'chip ' + statusClass(module), module.name" not in JS


def test_chips_and_the_update_button_never_wrap_or_shrink():
    chip = CSS.split(".chip {", 1)[1].split("}", 1)[0]
    update = CSS.split(".update {", 1)[1].split("}", 1)[0]
    assert "white-space: nowrap" in chip and "flex: none" in update


def test_an_empty_calendar_month_is_a_line_with_a_jump_not_a_grid():
    assert "Nothing dated this month." in JS
    assert "const inMonth" in JS and "Next: " in JS
