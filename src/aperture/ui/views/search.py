"""Direct text (OCR/filename) and visual search without the LLM."""

from __future__ import annotations

import streamlit as st

from ...bootstrap import AppContext
from ...search.text import search_text_ids, snippets_for
from ...search.visual import VisualSearch
from ..components import connection, photo_grid


def render(ctx: AppContext) -> None:
    st.title("Search")
    tab_text, tab_visual = st.tabs(["Text in photos and files", "Visual"])
    with tab_text:
        query = st.text_input("Words to find (text read from images, PDFs, file names)", key="q:text")
        if query.strip():
            with connection(ctx) as conn:
                ids = search_text_ids(conn, query)
            st.caption(f"{len(ids):,} matches")

            def snippets(page_ids: list[int]) -> dict[int, str]:
                with connection(ctx) as conn:
                    return snippets_for(conn, page_ids, query)

            photo_grid(ctx, ids, key="search:text", snippets=snippets)
    with tab_visual:
        query = st.text_input("Describe what the photo shows", key="q:visual")
        if query.strip():
            embedder = ctx.search_embedder()
            if embedder is None:
                st.error(ctx.embedder_error or "The visual model is not available.")
                return
            hits = VisualSearch(ctx.embedding_index(), embedder, ctx.settings.visual_strictness).search(query)
            st.caption(f"{len(hits.ids):,} matches at '{ctx.settings.visual_strictness}' strictness")
            photo_grid(ctx, hits.ids, key="search:visual")
