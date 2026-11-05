"""Headless smoke tests of every Streamlit page (skipped without streamlit)."""

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

PAGES = ["chat", "library", "people", "settings", "organize"]


def _script(page: str) -> None:  # executed by AppTest in its own namespace
    import importlib

    import streamlit as st

    from aperture.ui.state import get_context

    st.set_page_config(layout="wide")
    importlib.import_module(f"aperture.ui.views.{page}").render(get_context())


@pytest.fixture
def ctx_env(scanned, monkeypatch):
    monkeypatch.setenv("APERTURE_DRIVE", str(scanned.paths.drive))
    from aperture.ui import state

    state.get_context.clear()
    return scanned


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_without_exception(ctx_env, page):
    app = AppTest.from_function(_script, args=(page,), default_timeout=30).run()
    assert not app.exception, [e.value for e in app.exception]


def test_library_grid_is_paginated(ctx_env):
    app = AppTest.from_function(_script, args=("library",), default_timeout=30).run()
    assert any("1-5 of 5" in c.value or "of 5" in c.value for c in app.caption)


def test_tidy_page_full_flow(ctx_env):
    ctx_env.settings.allow_moves = True
    ctx_env.settings.save(ctx_env.paths)
    from aperture.ui import state

    state.get_context.clear()
    app = AppTest.from_function(_script, args=("organize",), default_timeout=30).run()
    assert not app.exception, [e.value for e in app.exception]
    next(b for b in app.button if b.label == "Find exact copies").click().run()
    assert not app.exception, [e.value for e in app.exception]
    assert any("No exact copies" in s.value for s in app.success)


def test_tidy_moves_duplicates_and_undo(ctx_env, library):
    import shutil

    shutil.copy2(library / "Family" / "blue_0.jpg", library / "blue_copy.jpg")
    from aperture.indexing.runner import Scanner
    from aperture.ui import state

    from .conftest import fake_services

    Scanner(ctx_env.paths, ctx_env.settings, ctx_env.db, fake_services).run()
    ctx_env.settings.allow_moves = True
    ctx_env.settings.save(ctx_env.paths)
    state.get_context.clear()
    app = AppTest.from_function(_script, args=("organize",), default_timeout=30).run()
    next(b for b in app.button if b.label == "Find exact copies").click().run()
    assert any("MOVE" in m.value for m in app.markdown)
    app.checkbox(key="tidy:exact:ok").check().run()
    next(b for b in app.button if b.label.startswith("Move 1 file")).click().run()
    assert not app.exception, [e.value for e in app.exception]
    assert sum(1 for p in library.rglob("*.jpg") if "moved duplicates" in str(p)) == 1
    next(b for b in app.button if b.label == "Undo").click().run()
    assert not any("moved duplicates" in str(p) for p in library.rglob("*.jpg"))


def test_defects_page_label_flow(ctx_env):
    from aperture.ui import state

    state.get_context.clear()
    app = AppTest.from_function(_script, args=("organize",), default_timeout=30).run()  # defects live in a tab of Tidy up
    next(b for b in app.button if b.label == "Measure new photos").click().run()
    assert not app.exception, [e.value for e in app.exception]
    next(b for b in app.button if b.label.startswith("Label 5 as defect")).click().run()
    assert not app.exception, [e.value for e in app.exception]
    conn = ctx_env.db.connect()
    assert conn.execute("SELECT COUNT(*) FROM flags WHERE status='defect'").fetchone()[0] == 5


def test_similar_shots_tab_runs(ctx_env):
    from aperture.ui import state

    ctx_env.settings.allow_moves = True
    ctx_env.settings.save(ctx_env.paths)
    state.get_context.clear()
    app = AppTest.from_function(_script, args=("organize",), default_timeout=30).run()
    conn = ctx_env.db.connect()
    conn.execute("UPDATE items SET taken_at='2024-05-01 10:00:00'")
    conn.commit()
    next(b for b in app.button if b.label == "Find similar shots").click().run()
    assert not app.exception, [e.value for e in app.exception]
    assert any("KEEP" in m.value for m in app.markdown) and any("KEEP" in m.value for m in app.markdown)


def _move_script() -> None:
    import streamlit as st

    from aperture import library as lib
    from aperture.ui.components import connection
    from aperture.ui.state import get_context
    from aperture.ui.views.organize import move_card

    ctx = get_context()
    with connection(ctx) as conn:
        ids = [int(i) for i in lib.item_ids(conn)]
    st.session_state["ids_seen"] = len(ids)
    move_card(ctx, ids, key="t")


def test_move_card_preview_then_confirm_really_moves(ctx_env):
    """Regression: Confirm used to do nothing because the page returned early on the second run."""
    from pathlib import Path

    app = AppTest.from_function(_move_script, default_timeout=30).run()
    assert not app.exception, [e.value for e in app.exception]
    app.text_input(key="t:dest").set_value("Moved here").run()
    next(b for b in app.button if b.label == "Preview").click().run()
    assert not app.exception, [e.value for e in app.exception]
    confirm = next(b for b in app.button if b.label.startswith("Confirm"))
    confirm.click().run()
    assert not app.exception, [e.value for e in app.exception]
    assert any("Moved" in s.value for s in app.success), [s.value for s in app.success]
    dest = Path(ctx_env.settings.photo_dir) / "Moved here"
    assert dest.is_dir() and any(dest.iterdir())
