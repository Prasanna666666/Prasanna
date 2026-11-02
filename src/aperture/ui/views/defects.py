"""Label badly taken photos (blurry, too dark, blank...) and manage the labels."""

from __future__ import annotations

import streamlit as st

from ... import library as lib
from ... import quality
from ...bootstrap import AppContext
from ..components import connection, pager, photo_grid, show_thumb
from .organize import move_card

SEL = "defects:unselected"


def _toggle(item_id: int) -> None:
    unselected: set[int] = st.session_state.setdefault(SEL, set())
    unselected.symmetric_difference_update({item_id})


def _analyze(ctx: AppContext) -> None:
    bar = st.progress(0.0, text="Measuring photo quality...")
    with connection(ctx) as conn:
        quality.ensure_quality(
            conn, ctx.paths, None, lambda d, t: bar.progress(d / max(1, t), text=f"Measured {d:,} of {t:,} photos")
        )
    bar.empty()


def _suggestions(ctx: AppContext) -> None:
    c1, c2 = st.columns([2, 3])
    sensitivity = c1.select_slider("Sensitivity", list(quality.SENSITIVITY), value="medium", help="Higher flags more photos.")
    if c2.button("Measure new photos", icon=":material/straighten:"):
        _analyze(ctx)
    with connection(ctx) as conn:
        measured = conn.execute("SELECT COUNT(*) FROM items WHERE sharp IS NOT NULL AND missing=0").fetchone()[0]
        found = quality.suggest_defects(conn, sensitivity)
    if measured == 0:
        st.info("No photos measured yet. Press 'Measure new photos' (reads only Aperture's own previews, so it is fast).")
        return
    st.caption(f"{measured:,} photos measured. Photos you already reviewed are not suggested again.")
    if not found:
        st.success("Nothing suspicious found.")
        return
    reasons = dict(found)
    unselected: set[int] = st.session_state.setdefault(SEL, set())
    chosen = [(i, r) for i, r in found if i not in unselected]
    by_reason: dict[str, int] = {}
    for _, r in found:
        by_reason[r] = by_reason.get(r, 0) + 1
    st.markdown(f"**{len(found):,}** suggestions - " + ", ".join(f"{n:,} {r}" for r, n in by_reason.items()))
    st.caption("Untick any photo that is actually fine (a dark night shot, for example), then apply.")

    page = pager("defects", len(found), ctx.settings.page_size)
    page_ids = [i for i, _ in found[page.start : page.end]]
    with connection(ctx) as conn:
        items = lib.items_by_ids(conn, page_ids)
    shown = [items[i] for i in page_ids if i in items]
    for start in range(0, len(shown), 6):
        for cell, item in zip(st.columns(6), shown[start : start + 6], strict=False):
            with cell:
                show_thumb(ctx, item)
                st.checkbox(
                    f"{reasons[item.id]}",
                    value=item.id not in unselected,
                    key=f"defects:cb:{item.id}",
                    on_change=_toggle,
                    args=(item.id,),
                    help=f"Label {item.name} as a defect photo",
                )
    st.divider()
    a, b = st.columns(2)
    if a.button(f"Label {len(chosen):,} as defect photos", type="primary", disabled=not chosen, icon=":material/flag:"):
        with connection(ctx) as conn:
            quality.set_defects(conn, chosen)
            quality.mark_ok(conn, [i for i, _ in found if i in unselected])  # reviewed and fine: never suggest again
        st.session_state[SEL] = set()
        st.rerun()
    if b.button("These are all fine, stop suggesting them", disabled=not found):
        with connection(ctx) as conn:
            quality.mark_ok(conn, [i for i, _ in found])
        st.session_state[SEL] = set()
        st.rerun()


def _marked(ctx: AppContext) -> None:
    with connection(ctx) as conn:
        ids = quality.defect_ids(conn)
    if len(ids) == 0:
        st.info("No photos are labelled as defects yet.")
        return
    st.markdown(
        f"**{len(ids):,}** photos are labelled as defects. They stay where they are; hide them in the Library or search for them by asking for 'defect photos'."
    )
    c1, c2 = st.columns(2)
    if c1.button("Remove all labels", icon=":material/flag_circle:", help="Unlabel every defect photo (nothing is moved)"):
        with connection(ctx) as conn:
            quality.unmark(conn, ids.tolist())
        st.rerun()
    with c2:
        move_card(ctx, ids.tolist(), key="defects:move")
    photo_grid(ctx, ids, key="defects:marked")


def render(ctx: AppContext) -> None:
    st.title("Defect photos")
    st.caption("Label blurry, too dark, too bright or blank shots. Labels are notes in Aperture's database: no file is touched.")
    suggestions, marked = st.tabs(["Suggestions", "Labelled defects"])
    with suggestions:
        _suggestions(ctx)
    with marked:
        _marked(ctx)
