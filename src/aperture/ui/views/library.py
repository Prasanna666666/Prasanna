"""Browse the whole library with filters."""

from __future__ import annotations

import streamlit as st

from ... import library as lib
from ...bootstrap import AppContext
from ..components import connection, photo_grid

KINDS = {"Photos": "image", "PDFs": "pdf", "Text files": "text"}


def render(ctx: AppContext) -> None:
    st.title("Library")
    with connection(ctx) as conn:
        years = lib.years_available(conn)
        cov = lib.coverage(conn)
    if cov.total == 0:
        st.info("The library is empty. Choose a photo folder in Settings and start indexing.")
        return
    c1, c2, c3, c4 = st.columns(4)
    kinds = c1.multiselect("Show", list(KINDS), default=["Photos"])
    year = c2.selectbox("Year", ["All years", *years])
    name = c3.text_input("File or folder name contains")
    newest = c4.radio("Order", ["Newest first", "Oldest first"], horizontal=True) == "Newest first"
    with connection(ctx) as conn:
        ids = lib.item_ids(conn, tuple(KINDS[k] for k in kinds), None if year == "All years" else int(year), name, newest)
    photo_grid(ctx, ids, key="library")
