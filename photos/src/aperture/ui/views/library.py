"""Browse the whole library with filters."""

from __future__ import annotations

import streamlit as st
from images import library as lib

from ...albums import build_albums, places_summary
from ...bootstrap import AppContext
from ..components import connection, photo_grid

KINDS = {"Photos": "image", "PDFs": "pdf", "Text files": "text"}


def render(ctx: AppContext) -> None:
    st.title("Photos")
    with connection(ctx) as conn:
        cov = lib.coverage(conn)
    if cov.total == 0:
        st.info("The library is empty. Choose a photo folder in Settings and start indexing.")
        return
    everything, albums, places = st.tabs(["All photos", "Albums", "Places"])
    with everything:
        _all_photos(ctx)
    with albums:
        _albums(ctx)
    with places:
        _places(ctx)


def _all_photos(ctx: AppContext) -> None:
    with connection(ctx) as conn:
        years = lib.years_available(conn)
    c1, c2, c3, c4 = st.columns(4)
    kinds = c1.multiselect("Show", list(KINDS), default=["Photos"])
    year = c2.selectbox("Year", ["All years", *years])
    name = c3.text_input("File or folder name contains")
    newest = c4.radio("Order", ["Newest first", "Oldest first"], horizontal=True) == "Newest first"
    with connection(ctx) as conn:
        ids = lib.item_ids(conn, tuple(KINDS[k] for k in kinds), None if year == "All years" else int(year), name, newest)
    photo_grid(ctx, ids, key="library")


def _albums(ctx: AppContext) -> None:
    with connection(ctx) as conn:
        found = build_albums(conn)
    if not found:
        st.info("Albums appear when you have runs of at least 8 photos taken close together in time.")
        return
    st.caption(f"{len(found):,} albums, made from when and where the photos were taken.")
    labels = {a.title: a for a in found}
    choice = st.selectbox("Album", list(labels), label_visibility="collapsed")
    photo_grid(ctx, labels[choice].ids, key="album")


def _places(ctx: AppContext) -> None:
    with connection(ctx) as conn:
        rows = places_summary(conn)
    if not rows:
        st.info("No photo has a known place yet. Places come from the GPS data in photos.")
        return
    st.caption(f"{len(rows):,} places. Pick one to see its photos.")
    names = [f"{place} ({count:,})" for place, count in rows]
    pick = st.selectbox("Place", names, label_visibility="collapsed")
    place = rows[names.index(pick)][0]
    with connection(ctx) as conn:
        ids = [
            r[0] for r in conn.execute("SELECT id FROM items WHERE missing=0 AND place=? ORDER BY taken_at DESC, id", (place,))
        ]
    photo_grid(ctx, ids, key="place")
