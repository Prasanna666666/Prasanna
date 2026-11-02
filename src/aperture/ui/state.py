"""Process-wide context and small helpers shared by all views."""

from __future__ import annotations

import subprocess
import sys

import streamlit as st

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


def start_export_job(ctx: AppContext, job_id: str) -> None:
    subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "aperture", "export-job", job_id],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
    )  # fmt: skip
