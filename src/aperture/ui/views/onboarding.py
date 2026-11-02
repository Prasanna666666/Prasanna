"""First-run checklist: what is left to do before Aperture is useful."""

from __future__ import annotations

import html

import streamlit as st

from ... import library as lib
from ...bootstrap import AppContext
from ...diagnostics import run_checks
from ..components import connection
from ..state import start_scan


def _row(done: bool, title: str, detail: str) -> str:
    mark = "&#10003;" if done else ""
    return f'<div class="ap-check"><div class="ap-tick {"done" if done else ""}" aria-hidden="true">{mark}</div><div><b>{html.escape(title)}</b><small>{html.escape(detail)}</small></div></div>'


def render_checklist(ctx: AppContext) -> bool:
    """Show the setup card and return True when everything essential is ready."""
    checks = {c.label.split(" (")[0]: c for c in run_checks(ctx)}
    with connection(ctx) as conn:
        cov = lib.coverage(conn)
    steps = [
        (checks["Photo folder"].ok, "Choose your photo folder", "Settings -> Photo folder (on the external drive)"),
        (
            cov.total > 0,
            "Index your library",
            f"{cov.indexed:,} of {cov.total:,} files done. Runs in the background and can be paused.",
        ),
        (checks["AI model"].ok, "Start the AI model", checks["AI model"].detail),
        (checks["Face models"].ok, "Download the offline models once", checks["Face models"].detail),
    ]
    ready = all(done for done, _, _ in steps[:3])
    if all(done for done, _, _ in steps) and cov.indexed > 0:
        return True
    with st.container(border=True):
        st.subheader("Let's get you set up")
        st.html("".join(_row(*s) for s in steps))
        if steps[0][0] and not steps[1][0] and st.button("Start indexing", type="primary", icon=":material/play_arrow:"):
            start_scan(ctx)
            st.rerun()
        if not ready:
            st.caption("Everything stays on your drive and your Mac. Nothing is uploaded.")
    return False
