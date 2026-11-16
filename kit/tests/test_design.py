"""Every app serves the same look: the copies of design.css next to each app's stylesheet must be the one in design/."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_every_app_serves_the_one_design_file():
    source = (ROOT / "design" / "design.css").read_text()
    for copy in ("atlas/src/atlas/static", "finance/src/finance/static", "library/src/library/static"):
        assert (ROOT / copy / "design.css").read_text() == source, f"run scripts/sync-design.sh: {copy}/design.css differs"
    shared = (ROOT / "design" / "common.js").read_text()
    for copy in ("atlas/src/atlas/static", "finance/src/finance/static", "library/src/library/static"):
        assert (ROOT / copy / "common.js").read_text() == shared, f"run scripts/sync-design.sh: {copy}/common.js differs"
    for page in ("atlas/src/atlas/static/index.html", "finance/src/finance/static/index.html", "library/src/library/static/index.html"):
        assert "design.css" in (ROOT / page).read_text(), f"{page} does not load design.css"
        assert "common.js" in (ROOT / page).read_text(), f"{page} does not load common.js"


def _luminance(hex_colour: str) -> float:
    channels = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_text_colours_are_readable_on_every_background_in_both_themes():
    """WCAG AA: body text needs a contrast of 4.5 to 1. Checked on the tokens, so no page can pick a colour that fails."""
    import re

    css = (ROOT / "design" / "design.css").read_text()
    blocks = {
        "light": re.search(r":root \{(.*?)\n\}", css, re.S).group(1),
        "dark": re.search(r":root\[data-theme='dark'\] \{(.*?)\n\}", css, re.S).group(1),
    }
    for theme, block in blocks.items():
        tokens = dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", block))
        for text in ("fg", "muted", "faint"):
            for ground in ("bg", "card", "surface-2"):
                assert _contrast(tokens[text], tokens[ground]) >= 4.5, f"{theme}: --{text} on --{ground} is too faint to read"


def test_every_page_keeps_a_visible_keyboard_focus_and_respects_reduced_motion():
    css = (ROOT / "design" / "design.css").read_text()
    assert ":focus-visible" in css and "prefers-reduced-motion: reduce" in css


def test_no_rule_hides_the_surfaces_every_page_is_made_of():
    """A cleanup once left `.card, .stat { display: none !important }` behind: every card in every app disappeared and no test noticed."""
    import re

    css = (ROOT / "design" / "design.css").read_text()
    surfaces = {".card", ".stat", ".hero", ".panel", ".tripcard", ".medcard", ".labtile", ".yearstrip", ".healthhero", ".travelhero", ".hero-next"}
    for selectors, block in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        names = {s.strip() for s in selectors.split(",")}
        if names & surfaces and re.search(r"display\s*:\s*none", block):
            raise AssertionError(f"a rule hides a page surface: {sorted(names & surfaces)}")
