"""Process-wide context and small helpers shared by all views."""

from __future__ import annotations

import subprocess
import sys

import streamlit as st

from .. import library as lib
from ..bootstrap import AppContext
from ..config import default_paths
from ..indexing.progress import ScanLock
from ..safety import drive_problem


@st.cache_resource(show_spinner=False)
def get_context() -> AppContext:
    paths = default_paths()
    paths.ensure()
    ctx = AppContext(paths)
    ctx.warm_up()
    return ctx


def drive_ok(ctx: AppContext) -> str:
    """Empty string when the external drive is usable, else a user-facing problem."""
    return drive_problem(ctx.paths.drive) or ""


def start_scan(ctx: AppContext, *extra: str) -> bool:
    """Launch the resumable scanner as a separate low-priority process."""
    if ScanLock(ctx.paths).running():
        return False
    subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "aperture", "scan", *extra],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
    )  # fmt: skip
    return True


def caption_running() -> bool:
    out = subprocess.run(["/usr/bin/pgrep", "-f", "aperture caption"], capture_output=True, text=True, check=False)
    return bool(out.stdout.split())


def start_captions(ctx: AppContext) -> bool:
    """Describe every photo in the background at low priority (slow; searchable text for each photo)."""
    if caption_running() or ScanLock(ctx.paths).running():
        return False
    subprocess.Popen(
        [sys.executable, "-m", "aperture", "caption"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
    )  # fmt: skip
    return True


def start_export_job(ctx: AppContext, job_id: str) -> None:
    subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "aperture", "export-job", job_id],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
    )  # fmt: skip


# Counting the whole library on every click is slow on an external disk. These numbers may be up to a minute old: that is fine.
@st.cache_data(ttl=20, show_spinner=False)
def cached_coverage(_ctx: AppContext, db_key: str) -> lib.Coverage:
    conn = _ctx.db.connect()
    try:
        return lib.coverage(conn)
    finally:
        conn.close()


@st.cache_data(ttl=60, show_spinner=False)
def welcome_numbers(_ctx: AppContext, db_key: str) -> tuple[lib.Coverage, int, int, list[str]]:
    from .suggestions import suggest_prompts

    conn = _ctx.db.connect()
    try:
        cov = lib.coverage(conn)
        people = conn.execute("SELECT COUNT(DISTINCT person_id) FROM faces WHERE person_id IS NOT NULL").fetchone()[0]
        places = conn.execute("SELECT COUNT(DISTINCT place) FROM items WHERE place IS NOT NULL AND missing=0").fetchone()[0]
        return cov, int(people), int(places), (suggest_prompts(conn) if cov.indexed else [])
    finally:
        conn.close()


def pause_scan_for_chat(ctx: AppContext) -> bool:
    """Interactive work comes first: ask a running scan to pause (it resumes where it stopped). Returns True if it was running."""
    lock = ScanLock(ctx.paths)
    if lock.running():
        lock.stop()
        st.session_state["paused_for_chat"] = True
        return True
    return False
