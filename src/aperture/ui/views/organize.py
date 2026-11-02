"""Tidy up: find duplicates, preview the result, move them, undo anytime."""

from __future__ import annotations

import time
from collections.abc import Sequence
from pathlib import Path

import streamlit as st

from ... import library as lib
from ... import organize as org
from ... import quality
from ...bootstrap import AppContext
from ...safety import SafetyError
from ...similar import PRESETS, SimilarSettings, find_similar_groups
from ..components import connection, pager, show_thumb

GROUPS_PER_PAGE = 5


def _mb(n: int) -> str:
    return f"{n / 1e6:,.1f} MB" if n < 1e9 else f"{n / 1e9:,.2f} GB"


# --------------------------------------------------------------------------
# Shared pieces
# --------------------------------------------------------------------------
def _switch(ctx: AppContext) -> bool:
    """Moving is always preview-then-confirm, so no separate master switch is needed."""
    ctx.settings.allow_moves = True
    return True


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
def _find_exact(ctx: AppContext) -> None:
    bar = st.progress(0.0, text="Comparing files...")
    with connection(ctx) as conn:
        groups = org.find_exact_duplicates(conn, lambda d, t: bar.progress(d / max(1, t), text=f"Checked {d:,} of {t:,} files"))
    bar.empty()
    st.session_state["tidy:exact"] = groups
    st.session_state["tidy:exact:keep"] = {}


def _find_similar(ctx: AppContext, preset: str) -> None:
    bar = st.progress(0.0, text="Measuring photo quality...")
    with connection(ctx) as conn:
        quality.ensure_quality(
            conn, ctx.paths, None, lambda d, t: bar.progress(d / max(1, t), text=f"Measured {d:,} of {t:,} photos")
        )
        bar.progress(1.0, text="Grouping similar shots...")
        threshold, minutes = PRESETS[preset]
        groups = find_similar_groups(conn, ctx.embedding_index(), SimilarSettings(threshold, minutes))
    bar.empty()
    st.session_state["tidy:similar"] = groups
    st.session_state["tidy:similar:keep"] = {}


def _group_card(
    ctx: AppContext, scope: str, index: int, ids: list[int], default_keep: set[int], items: dict, show_quality: bool
) -> None:  # type: ignore[type-arg]
    """One group, side by side.  Exact copies keep one photo; similar shots may keep several."""
    keep_map: dict[int, set[int]] = st.session_state.setdefault(f"{scope}:keep", {})
    keep = keep_map.get(index, default_keep)
    with st.container(border=True):
        st.markdown(f"**Group {index + 1}** - {len(ids)} photos")
        shown = ids[:6]
        for cell, item_id in zip(st.columns(len(shown)), shown, strict=True):
            item = items[item_id]
            with cell:
                show_thumb(ctx, item)
                st.markdown(":green[**KEEP**]" if item_id in keep else ":red[**MOVE**]")
                detail = item.rel_path
                if show_quality:
                    detail += f" - sharpness {item.sharp:.0f}" if item.sharp is not None else ""
                st.caption(detail)
        if len(ids) > 6:
            st.caption(f"... and {len(ids) - 6} more")
        picked = st.multiselect(
            "Keep",
            ids,
            default=[i for i in ids if i in keep],
            format_func=lambda i: items[i].rel_path,
            key=f"{scope}:pick:{index}",
        )
        if set(picked) != keep and picked:
            keep_map[index] = set(picked)
            st.rerun()


def _review_groups(ctx: AppContext, scope: str, groups: list[list[int]], rule: str, dest: str, label: str, best: bool) -> None:
    with connection(ctx) as conn:
        items = lib.items_by_ids(conn, [i for g in groups for i in g])
        groups = [g for g in ([i for i in g if i in items] for g in groups) if len(g) > 1]
        if best:
            default = {n: {quality.best_of(conn, g)} for n, g in enumerate(groups)}
        else:
            default = {n: {org.choose_keeper([items[i] for i in g], rule)} for n, g in enumerate(groups)}
    keep_state = st.session_state.get(f"{scope}:keep", {})
    keepers = {n: keep_state.get(n, default[n]) for n in range(len(groups))}
    extra = sum(len(g) - len(keepers[n]) for n, g in enumerate(groups))
    st.markdown(f"**{len(groups):,}** groups - **{extra:,}** photos to move")
    try:
        with connection(ctx) as conn:
            plan = org.plan_duplicate_moves(conn, ctx.paths, ctx.settings, groups, keepers, dest)
    except SafetyError as exc:
        st.error(str(exc))
        plan = None
    page = pager(scope, len(groups), GROUPS_PER_PAGE)
    for n in range(page.start, page.end):
        _group_card(ctx, scope, n, groups[n], default[n], items, best)
    if plan is None:
        return
    st.divider()
    st.markdown(
        f"Ready to move **{plan.count:,}** files ({_mb(plan.total_bytes)}) to `{plan.dest_dir}`; their folder layout is kept inside it."
    )
    for _, why in plan.skipped[:5]:
        st.caption(f"Skipped: {why}")
    if st.checkbox("I have looked at the groups and want to go ahead", key=f"{scope}:ok") and st.button(
        f"Move {plan.count:,} files", key=f"{scope}:go", type="primary", disabled=plan.count == 0
    ):
        _report(_run_move(ctx, plan, label.format(plan.dest_dir.name)))
        st.session_state.pop(scope, None)


def render(ctx: AppContext) -> None:
    st.title("Tidy up")
    st.caption(
        "Find duplicates and similar shots, see what would happen, then move the extras to a folder. Nothing is ever deleted, and every batch can be undone."
    )
    if not _switch(ctx):
        history(ctx)
        return
    if not ctx.settings.photo_dir:
        st.info("Choose the photo folder in Settings first.")
        return
    dest = st.text_input(
        "Move the extra photos to", value=org.default_move_dir(ctx.settings), help="Must be inside your photo folder."
    )
    exact_tab, similar_tab = st.tabs(["Exact copies", "Similar shots"])

    with exact_tab:
        rule = st.selectbox("Which copy to keep", list(org.KEEP_RULES), format_func=org.KEEP_RULES.get)
        if st.button("Find exact copies", type="primary", icon=":material/content_copy:"):
            _find_exact(ctx)
        groups = st.session_state.get("tidy:exact")
        if groups is None:
            st.caption("Lists files with byte-identical content.")
        elif not groups:
            st.success("No exact copies found.")
        else:
            _review_groups(ctx, "tidy:exact", groups, rule, dest, "Exact copies -> {}", best=False)

    with similar_tab:
        st.caption(
            "Bursts, retakes and near-identical frames. The sharpest, best-exposed photo is suggested as the one to keep; you can keep more than one."
        )
        preset = st.select_slider("How alike", list(PRESETS), value="Same scene")
        if st.button("Find similar shots", type="primary", icon=":material/burst_mode:"):
            _find_similar(ctx, preset)
        groups = st.session_state.get("tidy:similar")
        if groups is None:
            st.caption("Press the button. The first run measures sharpness of every photo; later runs are quick.")
        elif not groups:
            st.success("No similar shots found. Try a looser setting.")
        else:
            _review_groups(ctx, "tidy:similar", groups, "", dest, "Similar shots -> {}", best=True)
    st.divider()
    history(ctx)
