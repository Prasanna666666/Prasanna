"""Indexing status and controls."""

from __future__ import annotations

import time

import streamlit as st

from ... import library as lib
from ...bootstrap import AppContext
from ...indexing.progress import ScanLock, read_progress
from ..components import connection
from ..state import caption_running, start_captions, start_scan


def maybe_autostart(ctx: AppContext) -> None:
    """Resume indexing once per browser session when enabled in Settings."""
    if ctx.settings.auto_scan and ctx.settings.photo_dir and not st.session_state.get("autostarted"):
        st.session_state["autostarted"] = True
        start_scan(ctx)


def _stage(label: str, done: int, total: int, hint: str) -> None:
    with st.container(border=True):
        st.markdown(f"**{label}**")
        st.progress(min(done / total, 1.0) if total else 0.0, text=f"{done:,} of {total:,}")
        st.caption(hint)


def _captions(ctx: AppContext) -> None:
    with connection(ctx) as conn:
        done = conn.execute("SELECT COUNT(*) FROM captions").fetchone()[0]
        images = conn.execute("SELECT COUNT(*) FROM items WHERE missing=0 AND kind='image'").fetchone()[0]
    with st.container(border=True):
        st.markdown("**4. Describe every photo (optional)**")
        st.progress(min(done / images, 1.0) if images else 0.0, text=f"{done:,} of {images:,}")
        st.caption(
            "A small vision model writes a sentence for each photo, so you can search by what is in it. "
            "Slow (a few seconds per photo), runs quietly in the background and can be stopped any time."
        )
        if caption_running():
            st.info("Describing photos in the background.", icon=":material/visibility:")
        elif st.button("Describe all photos", icon=":material/visibility:") and not start_captions(ctx):
            st.info("Wait until indexing has finished.")


@st.fragment(run_every=3)
def _live(ctx: AppContext) -> None:
    lock = ScanLock(ctx.paths)
    prog = read_progress(ctx.paths) or {}
    with connection(ctx) as conn:
        cov = lib.coverage(conn)
    if lock.running():
        eta = prog.get("eta")
        eta_text = (
            f" - about {time.strftime('%H:%M:%S', time.gmtime(eta))} left" if isinstance(eta, (int, float)) and eta > 0 else ""
        )
        st.info(f"Working on: {prog.get('stage') or 'starting'}{eta_text}. {prog.get('current') or ''}", icon=":material/sync:")
        if st.button("Pause", icon=":material/pause:"):
            lock.stop()
    else:
        state = prog.get("state", "never run")
        st.caption(
            "Idle. The last run stopped early; press Start to continue." if state == "error" else f"Idle. Last run: {state}."
        )
    images = max(1, cov.total)
    a, b, c = st.columns(3)
    with a:
        _stage(
            "1. Read photos",
            cov.indexed,
            cov.total,
            "Dates, places, previews and the visual index. Search works as this grows.",
        )
    with b:
        _stage("2. Find faces", cov.faces_done, images, "Lets you search and group by person.")
    with c:
        _stage("3. Read text", cov.ocr_done, images, "Finds words in screenshots, receipts and PDFs.")
    _captions(ctx)
    if cov.failed:
        st.warning(f"{cov.failed:,} files could not be read. They are skipped and never altered.")


def body(ctx: AppContext) -> None:
    if not ctx.settings.photo_dir:
        st.info("Choose the photo folder in Settings first.")
        return
    st.caption(f"Reading `{ctx.settings.photo_dir}` (never modified). Progress is saved, so you can stop and resume any time.")
    c1, c2, c3 = st.columns([2, 1, 1])
    if c1.button("Start or resume", type="primary", icon=":material/play_arrow:") and not start_scan(ctx):
        st.info("Indexing is already running.")
    if c2.button("Retry failed files", icon=":material/refresh:"):
        start_scan(ctx, "--retry-errors")
    if c3.button("Regroup faces", icon=":material/group_work:"):
        start_scan(ctx, "--regroup-faces")
    _live(ctx)
