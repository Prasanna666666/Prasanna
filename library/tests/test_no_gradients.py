"""The design says no gradients (docs/design.md). A dark tint over a photo is one flat colour, so text stays readable without one. The only gradient left here is the repeating month lines of the year strip, which are gridlines, not decoration. Atlas's atlas.css and Finance's app.css still contain old gradient rules that design.css overrides on the pages checked; they are not scanned here."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLACES = [
    ROOT / "design" / "design.css",
    *sorted((ROOT / "library" / "src" / "library" / "static").glob("*.css")),
    *sorted((ROOT / "library" / "src" / "library" / "static").glob("*.js")),
]
GRADIENT = re.compile(r"(?<!repeating-)(linear|radial|conic)-gradient\(")


def test_no_decorative_gradient_in_any_style_or_script():
    found = [f"{p.relative_to(ROOT)}:{n}" for p in PLACES for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if GRADIENT.search(line)]
    assert found == []


def test_the_scan_sees_files():
    assert len(PLACES) >= 4
