"""Every app serves the same look: the copies of design.css next to each app's stylesheet must be the one in design/."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_every_app_serves_the_one_design_file():
    source = (ROOT / "design" / "design.css").read_text()
    for copy in ("atlas/src/atlas/static", "finance/src/finance/static", "library/src/library/static"):
        assert (ROOT / copy / "design.css").read_text() == source, f"run scripts/sync-design.sh: {copy}/design.css differs"
    for page in ("atlas/src/atlas/static/index.html", "finance/src/finance/static/index.html", "library/src/library/static/index.html"):
        assert "design.css" in (ROOT / page).read_text(), f"{page} does not load design.css"
