"""Indexing status and controls."""

from __future__ import annotations

import time

import streamlit as st

from ... import library as lib
from ...bootstrap import AppContext
from ...indexing.progress import ScanLock, read_progress
from ..components import connection
from ..state import start_scan


def maybe_autostart(ctx: AppContext) -> None:
    """Resume indexing once per browser session when enabled in Settings."""
    if ctx.settings.auto_scan and ctx.settings.photo_dir and not st.session_state.get("autostarted"):
        st.session_state["autostarted"] = True
        start_scan(ctx)


@st.fragment(run_every=3)
def _live(ctx: AppContext) -> None:
    lock = ScanLock(ctx.paths)
    prog = read_progress(ctx.paths) or {}
    running = lock.running()
    if running:
        total, done = max(1, int(prog.get("total", 1) or 1)), int(prog.get("done", 0) or 0)
        st.progress(min(done / total, 1.0), text=f"{prog.get('stage', '')}: {done:,} of {total:,} - {prog.get('current', '')}")
        eta = prog.get("eta")
        if isinstance(eta, (int, float)) and eta > 0:
            st.caption(f"About {time.strftime('%H:%M:%S', time.gmtime(eta))} remaining")
        if st.button("Pause indexing", icon=":material/pause:"):
            lock.stop()
    else:
        st.caption(f"Idle. Last state: {prog.get('state', 'never run')}")
    with connection(ctx) as conn:
        cov = lib.coverage(conn)
    c = st.columns(5)
    for cell, (label, val) in zip(
        c,
        [
            ("Files", cov.total),
            ("Indexed", cov.indexed),
            ("Visual", cov.embedded),
            ("Faces", cov.faces_done),
            ("Text", cov.ocr_done),
        ],
        strict=True,
    ):
        cell.metric(label, f"{val:,}")
    if cov.failed:
        st.warning(f"{cov.failed:,} files could not be read (they are skipped, never altered).")


def render(ctx: AppContext) -> None:
    st.title("Indexing")
    if not ctx.settings.photo_dir:
        st.info("Choose the photo folder in Settings first.")
        return
    st.caption(f"Reading `{ctx.settings.photo_dir}` (read-only). Progress is saved, so you can stop and resume at any time.")
    c1, c2, c3 = st.columns(3)
    if c1.button("Start or resume", type="primary", icon=":material/play_arrow:"):
        if not start_scan(ctx):
            st.info("Indexing is already running.")
    if c2.button("Retry failed files"):
        start_scan(ctx, "--retry-errors")
    if c3.button("Regroup faces"):
        start_scan(ctx, "--regroup-faces")
    _live(ctx)
