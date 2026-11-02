"""Face groups: name, merge, hide, review and combine people."""

from __future__ import annotations

import streamlit as st

from ...bootstrap import AppContext
from ...people import repository as repo
from ..components import connection, photo_grid


def _cover(ctx: AppContext, crop: str | None, label: str) -> None:
    if crop and (ctx.paths.data / crop).is_file():
        st.image(str(ctx.paths.data / crop), caption=label)
    else:
        st.caption(label)


def render(ctx: AppContext) -> None:
    st.title("People")
    with connection(ctx) as conn:
        people = repo.list_people(conn)
    if not people:
        st.info("No people found yet. Faces appear after the face pass of indexing completes.")
        return
    labels = {p.id: f"{p.label} ({p.photos:,} photos)" for p in people}
    tab_all, tab_manage, tab_together = st.tabs(["Everyone", "Manage a person", "Photos together"])
    with tab_all:
        for start in range(0, len(people), 8):
            for cell, p in zip(st.columns(8), people[start : start + 8], strict=False):
                with cell:
                    _cover(ctx, p.cover, p.label)
                    st.caption(f"{p.photos:,} photos")
    with tab_manage:
        pid = st.selectbox("Person", list(labels), format_func=labels.get)
        with connection(ctx) as conn:
            current = next(p for p in people if p.id == pid)
            name = st.text_input("Name", value=current.name or "", key=f"name:{pid}")
            c1, c2, c3 = st.columns(3)
            if c1.button("Save name", icon=":material/save:") and name.strip():
                repo.rename_person(conn, pid, name.strip())
                st.rerun()
            other = c2.selectbox(
                "Same person as", [None, *[i for i in labels if i != pid]], format_func=lambda i: "-" if i is None else labels[i]
            )
            if c2.button("Merge", disabled=other is None, help="Merge the chosen group into this person"):
                repo.merge_people(conn, pid, other)
                st.rerun()
            if c3.button("Hide this group", icon=":material/visibility_off:", help="Not a real person"):
                repo.hide_person(conn, pid)
                st.rerun()
            st.subheader("Review faces")
            st.caption("Least typical faces first. Remove any that are not this person.")
            for cell, face in zip(st.columns(8), repo.faces_for_review(conn, pid, 16), strict=False):
                with cell:
                    _cover(ctx, face.crop, f"match {face.similarity:.2f}")
                    if st.button("Not them", key=f"rej:{face.face_id}", help=f"Remove face {face.face_id} from {current.label}"):
                        repo.reject_face(conn, face.face_id)
                        st.rerun()
            ids = repo.person_item_ids(conn, [pid])
        st.subheader("Photos")
        photo_grid(ctx, ids, key=f"people:{pid}")
    with tab_together:
        chosen = st.multiselect("People who must all appear", list(labels), format_func=labels.get)
        if len(chosen) >= 2:
            with connection(ctx) as conn:
                ids = repo.items_with_all_people(conn, chosen)
            photo_grid(ctx, ids, key="people:together")
        else:
            st.caption("Pick at least two people.")
