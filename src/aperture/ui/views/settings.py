"""Validated settings form."""

from __future__ import annotations

import streamlit as st

from ...agent.llm import LLMError
from ...bootstrap import AppContext
from ...safety import SafetyError, resolve_export_dir, resolve_photo_dir
from ...search.visual import STRICTNESS


def render(ctx: AppContext) -> None:
    st.title("Settings")
    s = ctx.settings
    with st.form("settings"):
        photo = st.text_input("Photo folder (on the external drive)", s.photo_dir)
        export = st.text_input("Export folder (on the external drive, outside the photo folder)", s.export_dir)
        try:
            models = ctx.llm().list_models()
        except LLMError:
            models = []
        options = models or [s.ollama_model]
        model = st.selectbox(
            "Ollama model for the agent", options, index=options.index(s.ollama_model) if s.ollama_model in options else 0
        )
        strict = st.select_slider(
            "Visual match strictness",
            list(STRICTNESS),
            value=s.visual_strictness if s.visual_strictness in STRICTNESS else "balanced",
        )
        size = st.number_input("Photos per page", 6, 120, s.page_size, step=6)
        auto = st.checkbox("Resume indexing when Aperture opens", s.auto_scan)
        saved = st.form_submit_button("Save", type="primary")
    if not models:
        st.warning("Ollama is not reachable at the configured address. Start it with `ollama serve`.")
    if saved:
        try:
            if photo.strip():
                s.photo_dir = str(resolve_photo_dir(ctx.paths, photo.strip()))
            if export.strip():
                s.export_dir = str(resolve_export_dir(ctx.paths, export.strip(), s.photo_dir))
        except (SafetyError, PermissionError, OSError) as exc:
            st.error(str(exc))
            return
        s.ollama_model, s.visual_strictness, s.page_size, s.auto_scan = model, strict, int(size), auto
        s.save(ctx.paths)
        ctx.reload_settings()
        st.success("Saved.")
    st.divider()
    st.caption(f"Data lives in `{ctx.paths.root}`. Originals are never modified, moved, renamed or deleted.")
