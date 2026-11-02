"""Streamlit entry point (``aperture ui``)."""

from __future__ import annotations

import streamlit as st

from aperture.ui.state import drive_ok, get_context
from aperture.ui.views import chat, defects, library, organize, people, search, settings, status

st.set_page_config(page_title="Aperture", page_icon=":material/photo_camera:", layout="wide")


def main() -> None:
    ctx = get_context()
    problem = drive_ok(ctx)
    if problem:
        st.error(f"The external drive is not ready: {problem}")
        st.caption("Connect the drive and press R to reload. Nothing is stored anywhere else.")
        st.stop()
    pages = [
        st.Page(lambda: chat.render(ctx), title="Ask", icon=":material/chat:", url_path="ask", default=True),
        st.Page(lambda: library.render(ctx), title="Library", icon=":material/photo_library:", url_path="library"),
        st.Page(lambda: people.render(ctx), title="People", icon=":material/face:", url_path="people"),
        st.Page(lambda: organize.render(ctx), title="Tidy up", icon=":material/cleaning_services:", url_path="tidy"),
        st.Page(lambda: defects.render(ctx), title="Defect photos", icon=":material/flag:", url_path="defects"),
        st.Page(lambda: search.render(ctx), title="Search", icon=":material/search:", url_path="search"),
        st.Page(lambda: status.render(ctx), title="Indexing", icon=":material/sync:", url_path="indexing"),
        st.Page(lambda: settings.render(ctx), title="Settings", icon=":material/settings:", url_path="settings"),
    ]
    status.maybe_autostart(ctx)
    st.navigation(pages).run()


main()
