"""Tidy up: find duplicates, preview the result, move them, undo anytime."""

from __future__ import annotations

import time
from collections.abc import Sequence
from pathlib import Path

import streamlit as st

from ... import library as lib
from ... import organize as org
from ...bootstrap import AppContext
from ...safety import SafetyError
from ..components import connection, pager, show_thumb

GROUPS_PER_PAGE = 5


def _mb(n: int) -> str:
    return f"{n / 1e6:,.1f} MB" if n < 1e9 else f"{n / 1e9:,.2f} GB"


# --------------------------------------------------------------------------
# Shared pieces
# --------------------------------------------------------------------------
def _switch(ctx: AppContext) -> bool:
    """The master switch.  Off by default: until it is on, nothing can move."""
    on = st.toggle(
        "Allow Aperture to move files inside my photo folder",
        value=ctx.settings.allow_moves,
        help="Files are only moved (never deleted or overwritten), every move is logged, and each batch can be undone.",
    )
    if on != ctx.settings.allow_moves:
        ctx.settings.allow_moves = on
        ctx.settings.save(ctx.paths)
        st.rerun()
    if not on:
        st.info("Moving is off, so your photos are exactly as you left them. Turn the switch on to continue.")
    return on


def _report(report: org.MoveReport) -> None:
    if report.moved:
        st.success(f"Moved {report.moved:,} file{'s' if report.moved != 1 else ''}. You can undo this below.")
    for src, why in report.failed[:20]:
        st.warning(f"Not moved: `{Path(src).name}` - {why}")


def _run_move(ctx: AppContext, plan: org.MovePlan, label: str) -> org.MoveReport:
    bar = st.progress(0.0, text="Moving...")
    with connection(ctx) as conn:
        report = org.execute_move(
            conn, ctx.paths, ctx.settings, plan, label,
            lambda done, total: bar.progress(done / max(1, total), text=f"Moved {done:,} of {total:,}"),
        )  # fmt: skip
    bar.empty()
    st.session_state.pop("tidy:groups", None)
    return report


def history(ctx: AppContext) -> None:
    with connection(ctx) as conn:
        batches = org.list_batches(conn)
    st.subheader("History")
    if not batches:
        st.caption("Nothing has been moved yet.")
        return
    for b in batches:
        c1, c2 = st.columns([5, 1])
        when = time.strftime("%d %b %Y %H:%M", time.localtime(b.created))
        c1.markdown(f"**{b.label}** - {b.moved:,} files - {when}" + (" - *undone*" if b.undone else ""))
        if not b.undone and c2.button(
            "Undo", key=f"undo:{b.id}", help=f"Put the {b.moved} files from '{b.label}' back", icon=":material/undo:"
        ):
            try:
                with connection(ctx) as conn:
                    result = org.undo_batch(conn, ctx.paths, ctx.settings, b.id)
            except SafetyError as exc:
                st.error(str(exc))
            else:
                st.success(f"Put {result.moved:,} files back.")
                for path, why in result.failed[:10]:
                    st.warning(f"Could not restore `{Path(path).name}`: {why}")
                st.rerun()


# --------------------------------------------------------------------------
# Move any set of photos (used from the chat)
# --------------------------------------------------------------------------
def move_card(ctx: AppContext, ids: Sequence[int], key: str) -> None:
    """Preview-then-confirm move for any list of photos."""
    with st.expander(f"Move these {len(ids):,} photos to a folder"):
        if not ctx.settings.allow_moves:
            st.info("Moving is off. Switch it on in the Tidy up page first.")
            return
        name = st.text_input("Folder name (created inside your photo folder)", value="Sorted by Aperture", key=f"{key}:dest")
        if not st.button("Preview", key=f"{key}:preview"):
            return
        try:
            with connection(ctx) as conn:
                plan = org.plan_move(
                    conn, ctx.paths, ctx.settings, ids, Path(ctx.settings.photo_dir) / name.strip(), keep_structure=False
                )
        except SafetyError as exc:
            st.error(str(exc))
            return
        st.write(
            f"**{plan.count:,}** files ({_mb(plan.total_bytes)}) will move to `{plan.dest_dir}`; {len(plan.skipped)} skipped."
        )
        st.session_state[f"{key}:plan"] = plan
    plan = st.session_state.get(f"{key}:plan")
    if plan is not None and st.button(f"Confirm: move {plan.count:,} files", key=f"{key}:go", type="primary"):
        _report(_run_move(ctx, plan, f"Chat selection -> {plan.dest_dir.name}"))
        st.session_state.pop(f"{key}:plan", None)


# --------------------------------------------------------------------------
# Duplicates page
# --------------------------------------------------------------------------
def _find(ctx: AppContext) -> None:
    bar = st.progress(0.0, text="Comparing files...")
    with connection(ctx) as conn:
        groups = org.find_exact_duplicates(conn, lambda d, t: bar.progress(d / max(1, t), text=f"Checked {d:,} of {t:,} files"))
    bar.empty()
    st.session_state["tidy:groups"] = groups
    st.session_state["tidy:keep"] = {}


def _group_card(ctx: AppContext, index: int, ids: list[int], default_keep: int, items: dict) -> None:  # type: ignore[type-arg]
    keep_map: dict[int, int] = st.session_state.setdefault("tidy:keep", {})
    keep = keep_map.get(index, default_keep)
    with st.container(border=True):
        st.markdown(f"**Group {index + 1}** - {len(ids)} identical files, {_mb(items[ids[0]].size)} each")
        for cell, item_id in zip(st.columns(min(len(ids), 6)), ids[:6], strict=False):
            item = items[item_id]
            with cell:
                show_thumb(ctx, item)
                st.markdown(":green[**KEEP**]" if item_id == keep else ":red[**MOVE**]")
                st.caption(item.rel_path)
        if len(ids) > 6:
            st.caption(f"... and {len(ids) - 6} more")
        choice = st.selectbox(
            "Keep this one",
            ids,
            index=ids.index(keep),
            format_func=lambda i: items[i].rel_path,
            key=f"tidy:pick:{index}",
        )
        if choice != keep:
            keep_map[index] = choice
            st.rerun()


def render(ctx: AppContext) -> None:
    st.title("Tidy up")
    st.caption(
        "Find exact duplicates, see what would happen, then move them to a folder. Nothing is ever deleted, and every batch can be undone."
    )
    if not _switch(ctx):
        history(ctx)
        return
    if not ctx.settings.photo_dir:
        st.info("Choose the photo folder in Settings first.")
        return

    c1, c2 = st.columns(2)
    rule = c1.selectbox("Which copy to keep", list(org.KEEP_RULES), format_func=org.KEEP_RULES.get)
    dest = c2.text_input(
        "Move the other copies to", value=org.default_move_dir(ctx.settings), help="Must be inside your photo folder."
    )
    if st.button("Find duplicates", type="primary", icon=":material/content_copy:"):
        _find(ctx)

    groups: list[list[int]] | None = st.session_state.get("tidy:groups")
    if groups is None:
        st.caption(
            "Press 'Find duplicates'. Only files with identical content are listed; similar-looking photos are never touched."
        )
    elif not groups:
        st.success("No exact duplicates found.")
    else:
        with connection(ctx) as conn:
            items = lib.items_by_ids(conn, [i for g in groups for i in g])
        groups = [[i for i in g if i in items] for g in groups]
        groups = [g for g in groups if len(g) > 1]
        default_keep = {n: org.choose_keeper([items[i] for i in g], rule) for n, g in enumerate(groups)}
        keepers = {n: st.session_state.get("tidy:keep", {}).get(n, default_keep[n]) for n in range(len(groups))}
        extra = sum(len(g) - 1 for g in groups)
        freed = sum(items[g[0]].size * (len(g) - 1) for g in groups)
        st.markdown(
            f"**{len(groups):,}** groups - **{extra:,}** extra copies - **{_mb(freed)}** that would leave your library folders"
        )

        try:
            with connection(ctx) as conn:
                plan = org.plan_duplicate_moves(conn, ctx.paths, ctx.settings, groups, keepers, dest)
        except SafetyError as exc:
            st.error(str(exc))
            plan = None
        page = pager("tidy", len(groups), GROUPS_PER_PAGE)
        for n in range(page.start, page.end):
            _group_card(ctx, n, groups[n], default_keep[n], items)

        if plan is not None:
            st.divider()
            st.markdown(f"Ready to move **{plan.count:,}** files to `{plan.dest_dir}` (their folder layout is kept inside it).")
            for _, why in plan.skipped[:5]:
                st.caption(f"Skipped: {why}")
            if st.checkbox("I have looked at the groups and want to go ahead", key="tidy:ok") and st.button(
                f"Move {plan.count:,} files", type="primary", disabled=plan.count == 0
            ):
                _report(_run_move(ctx, plan, f"Duplicates -> {plan.dest_dir.name}"))
    st.divider()
    history(ctx)
