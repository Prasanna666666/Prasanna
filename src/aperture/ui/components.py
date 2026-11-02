"""Reusable, accessible Streamlit components (grid, pager, detail dialog)."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager

import numpy as np
import streamlit as st

from .. import library
from ..bootstrap import AppContext
from ..config import DENSITY_COLUMNS
from ..models import Item
from ..paging import Page, make_page, page_slice, page_window
from ..people.repository import faces_in_item


@contextmanager
def connection(ctx: AppContext) -> Iterator:  # type: ignore[type-arg]
    """A per-render SQLite connection that is always closed."""
    conn = ctx.db.connect()
    try:
        yield conn
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Pager
# --------------------------------------------------------------------------
def _go(key: str, number: int) -> None:
    st.session_state[f"{key}:page"] = number


def pager(key: str, total: int, size: int) -> Page:
    """Render page controls and return the (valid) current page.

    Works for any result size; the page number is clamped, so a shrinking
    result set can never leave the user on a page that no longer exists."""
    page = make_page(total, size, st.session_state.get(f"{key}:page", 1))
    st.session_state[f"{key}:page"] = page.number
    if page.pages > 1:
        with st.container(horizontal=True, vertical_alignment="center"):
            st.button("Previous", key=f"{key}:prev", disabled=not page.has_prev, on_click=_go, args=(key, page.number - 1),
                      icon=":material/chevron_left:", help="Previous page")  # fmt: skip
            for n in page_window(page):
                if n is None:
                    st.write("...")
                else:
                    st.button(str(n), key=f"{key}:n{n}", type="primary" if n == page.number else "secondary",
                              on_click=_go, args=(key, n), help=f"Go to page {n}")  # fmt: skip
            st.button("Next", key=f"{key}:next", disabled=not page.has_next, on_click=_go, args=(key, page.number + 1),
                      icon=":material/chevron_right:", icon_position="right", help="Next page")  # fmt: skip
    st.caption(f"{page.label} - page {page.number} of {page.pages}")
    return page


# --------------------------------------------------------------------------
# Grid
# --------------------------------------------------------------------------
def show_thumb(ctx: AppContext, item: Item) -> None:
    if item.thumb and (ctx.paths.data / item.thumb).is_file():
        st.image(str(ctx.paths.data / item.thumb), caption=item.caption)
    else:
        st.caption(f"{item.caption} - preview not ready yet")


def photo_grid(
    ctx: AppContext, ids: Sequence[int] | np.ndarray, key: str, *, snippets: Callable[[list[int]], dict[int, str]] | None = None
) -> None:
    """Paginated grid of photos.  Only the current page is fetched and rendered."""
    id_list = np.asarray(ids)
    if len(id_list) == 0:
        st.info("No photos to show.")
        return
    page = pager(key, len(id_list), ctx.settings.page_size)
    page_ids = [int(i) for i in page_slice(id_list, page)]
    with connection(ctx) as conn:
        items = library.items_by_ids(conn, page_ids)
    ordered = [items[i] for i in page_ids if i in items]
    notes = snippets(page_ids) if snippets else {}
    per_row = DENSITY_COLUMNS.get(ctx.settings.ui_density, 6)
    for start in range(0, len(ordered), per_row):
        row = ordered[start : start + per_row]
        for cell, item in zip(st.columns(per_row), row, strict=False):
            with cell, st.container(key=f"tile-{key}-{item.id}"):
                show_thumb(ctx, item)
                if item.id in notes:
                    st.markdown(highlight(notes[item.id]), unsafe_allow_html=True)
                if st.button(
                    "Open",
                    key=f"{key}:open:{item.id}",
                    type="tertiary",
                    icon=":material/open_in_full:",
                    help=f"Open details for {item.name}",
                ):
                    item_dialog(ctx, item.id)


def highlight(snippet: str) -> str:
    """Escape OCR text, then turn the match markers into <mark> (safe HTML)."""
    import html

    safe = html.escape(snippet).replace("\x02", "<mark>").replace("\x03", "</mark>")
    return f"<small>{safe}</small>"


# --------------------------------------------------------------------------
# Detail dialog
# --------------------------------------------------------------------------
@st.dialog("Photo details", width="large")
def item_dialog(ctx: AppContext, item_id: int) -> None:
    with connection(ctx) as conn:
        item = library.get_item(conn, item_id)
        if item is None:
            st.warning("This photo is no longer in the library.")
            return
        left, right = st.columns([3, 2])
        with left:
            preview = ctx.paths.data / item.preview if item.preview else None
            if preview and preview.is_file():
                st.image(str(preview), caption=item.caption)
            else:
                st.info("Preview not available yet.")
        with right:
            st.subheader(item.name)
            facts = {
                "Date": item.date_label,
                "Camera": item.camera or "-",
                "Place": item.place or "-",
                "Size": f"{item.size / 1e6:.1f} MB" if item.size else "-",
                "Dimensions": f"{item.width} x {item.height}" if item.width and item.height else "-",
                "Type": item.kind,
            }
            for label, value in facts.items():
                st.markdown(f"**{label}:** {value}")
            st.caption(f"`{item.path}`")
            st.caption("The original is read-only: Lumo never modifies, moves or deletes it.")
            if st.button("Show in Finder", key=f"reveal:{item.id}", icon=":material/folder_open:"):
                subprocess.run(["open", "-R", item.path], check=False)  # noqa: S603, S607
            if item.notes:
                st.caption(f"Note: {item.notes}")
        people = faces_in_item(conn, item.id)
        if people:
            st.markdown("**People in this photo**")
            for cell, (crop, label) in zip(st.columns(max(1, min(len(people), 6))), people[:6], strict=False):
                with cell:
                    if crop and (ctx.paths.data / crop).is_file():
                        st.image(str(ctx.paths.data / crop), caption=label)
                    else:
                        st.caption(label)
        text = library.item_text(conn, item.id)
        if text:
            with st.expander("Text found in this file"):
                st.text(text)
        index = ctx.embedding_index()
        similar_ids, _ = index.most_similar(item.id, k=6)
        if len(similar_ids):
            st.markdown("**Similar photos**")
            similar = library.items_by_ids(conn, similar_ids.tolist())
            for cell, sid in zip(st.columns(6), similar_ids.tolist(), strict=False):
                if sid in similar:
                    with cell:
                        show_thumb(ctx, similar[sid])
