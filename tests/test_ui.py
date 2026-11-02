"""Headless smoke tests of every Streamlit page (skipped without streamlit)."""

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

PAGES = ["chat", "library", "people", "search", "status", "settings"]


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
