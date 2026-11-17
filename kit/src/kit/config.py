"""The one place that says which model answers: a module's own setting wins, then ATLAS_MODEL, then the default. Every app asks here, so the model in use is the same unless the owner chose otherwise for one app."""

from __future__ import annotations

import os

from . import llm


def model(override: str | None = None) -> str:
    """The model to use. `override` is what one app was told by its own setting (Finance's Settings page, LIBRARY_MODEL); empty means the shared choice."""
    return (override or "").strip() or os.environ.get("ATLAS_MODEL", "").strip() or llm.DEFAULT_MODEL
