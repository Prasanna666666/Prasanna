"""Streamlit entry point (``aperture ui``)."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from aperture import library as lib
from aperture.indexing.progress import ScanLock
from aperture.ui import theme
from aperture.ui.components import connection
from aperture.ui.state import drive_ok, get_context
from aperture.ui.views import chat, defects, library, organize, people, search, settings, status

st.set_page_config(page_title="Lumo", page_icon=":material/photo_camera:", layout="wide", initial_sidebar_state="expanded")


def _sidebar_status(ctx) -> None:
    chips = [theme.chip("Drive connected", "ok")]
    if ScanLock(ctx.paths).running():
        chips.append(theme.chip("Indexing", "warn"))
    with connection(ctx) as conn:
        cov = lib.coverage(conn)
    if cov.total:
        chips.append(theme.chip(f"{cov.total:,} files", "ok"))
    healthy, _ = ctx.llm().health()
    chips.append(theme.chip("AI ready" if healthy else "AI offline", "ok" if healthy else "bad"))
    with st.sidebar:
        st.divider()
        st.html("".join(chips))


def main() -> None:
    ctx = get_context()
    theme.inject(ctx.settings.high_contrast)
    problem = drive_ok(ctx)
    if problem:
        theme.hero("Your drive is not connected", problem)
        st.caption("Connect the drive and reload this page. Nothing is stored anywhere else.")
        st.stop()
    st.logo(str(Path(__file__).parent / "assets" / "logo.svg"), size="large")
    pages = {
        "Find": [
            st.Page(lambda: chat.render(ctx), title="Ask", icon=":material/auto_awesome:", url_path="ask", default=True),
            st.Page(lambda: library.render(ctx), title="Library", icon=":material/photo_library:", url_path="library"),
            st.Page(lambda: people.render(ctx), title="People", icon=":material/face:", url_path="people"),
            st.Page(lambda: search.render(ctx), title="Search", icon=":material/search:", url_path="search"),
        ],
        "Organise": [
            st.Page(lambda: organize.render(ctx), title="Tidy up", icon=":material/cleaning_services:", url_path="tidy"),
            st.Page(lambda: defects.render(ctx), title="Defect photos", icon=":material/flag:", url_path="defects"),
        ],
        "System": [
            st.Page(lambda: status.render(ctx), title="Indexing", icon=":material/sync:", url_path="indexing"),
            st.Page(lambda: settings.render(ctx), title="Settings", icon=":material/settings:", url_path="settings"),
        ],
    }
    status.maybe_autostart(ctx)
    _sidebar_status(ctx)
    st.navigation(pages).run()


main()
