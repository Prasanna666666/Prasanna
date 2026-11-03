"""Validated settings form and health checks."""

from __future__ import annotations

import streamlit as st

from ...agent.llm import LLMError
from ...bootstrap import AppContext
from ...config import DENSITY_COLUMNS
from ...diagnostics import run_checks
from ...safety import SafetyError, resolve_export_dir, resolve_photo_dir
from ...search.visual import STRICTNESS
from . import status


def _health(ctx: AppContext) -> None:
    for check in run_checks(ctx):
        icon = ":material/check_circle:" if check.ok else (":material/error:" if check.required else ":material/info:")
        color = "green" if check.ok else ("red" if check.required else "orange")
        st.markdown(f":{color}[{icon}] **{check.label}** - {check.detail}")


def render(ctx: AppContext) -> None:
    st.title("Settings")
    _form(ctx)
    st.subheader("Indexing")
    status.body(ctx)
    with st.expander("Health check"):
        _health(ctx)


def _form(ctx: AppContext) -> None:
    s = ctx.settings
    try:
        models = ctx.llm().list_models()
    except LLMError:
        models = []
    with st.form("settings"):
        st.subheader("Folders")
        photo = st.text_input("Photo folder (on the external drive)", s.photo_dir)
        export = st.text_input("Export folder (on the external drive, outside the photo folder)", s.export_dir)
        advanced = st.expander("Advanced: AI models and display")
        with advanced:
            options = models or [s.ollama_model]
            model = st.selectbox(
                "Model that understands your requests",
                options,
                index=options.index(s.ollama_model) if s.ollama_model in options else 0,
            )
            vision_options = models or [s.vision_model]
            vision = st.selectbox(
                "Vision model that double-checks results",
                vision_options,
                index=vision_options.index(s.vision_model) if s.vision_model in vision_options else 0,
            )
            agentic = st.toggle(
                "Let the AI work step by step (agent mode)",
                s.agentic,
                help="Lets the model search, look at results, verify and retry. Off = one-shot planning.",
            )
            strict = st.select_slider(
                "Default visual match strictness",
                list(STRICTNESS),
                value=s.visual_strictness if s.visual_strictness in STRICTNESS else "balanced",
            )
            density = st.segmented_control(
                "Photos per row",
                list(DENSITY_COLUMNS),
                default=s.ui_density,
                format_func=lambda d: f"{d.title()} ({DENSITY_COLUMNS[d]})",
            )
            size = st.number_input("Photos per page", 6, 120, s.page_size, step=6)
            contrast = st.toggle("High contrast", s.high_contrast, help="Stronger borders and text for easier reading.")
        auto = st.checkbox("Resume indexing when Lumo opens", s.auto_scan)
        smart = st.checkbox("Use the tool-using agent (experimental)", s.brain == "tools",
                            help="The AI itself decides when to search, count or just talk, using tools and facts from your library. Off = the older fixed pipeline.")
        fast = st.checkbox("Skip the AI for simple one-subject searches (fastest)", s.fast_search,
                           help="'dogs' or 'birthday cake' go straight to the image search. Searches with names, places, dates or filters still use the AI.")
        quick = st.checkbox("Show instant photo matches while the AI thinks", s.quick_preview,
                            help="Image search answers in milliseconds, before the AI has finished. Only confident matches show.")
        saved = st.form_submit_button("Save", type="primary")
    if not models:
        st.warning("Ollama is not reachable. Start it with `ollama serve` (or open the Ollama app).")
    if saved:
        try:
            if photo.strip():
                s.photo_dir = str(resolve_photo_dir(ctx.paths, photo.strip()))
            if export.strip():
                s.export_dir = str(resolve_export_dir(ctx.paths, export.strip(), s.photo_dir))
        except (SafetyError, PermissionError, OSError) as exc:
            st.error(str(exc))
            return
        s.ollama_model, s.vision_model, s.agentic, s.visual_strictness = model, vision, agentic, strict
        s.page_size, s.auto_scan, s.high_contrast, s.ui_density = int(size), auto, contrast, density or s.ui_density
        s.quick_preview, s.fast_search = quick, fast
        s.brain = "tools" if smart else "classic"
        s.save(ctx.paths)
        ctx.reload_settings()
        st.success("Saved.")
        st.rerun()
    st.caption(f"Your data lives in `{ctx.paths.root}`. Originals are never modified, renamed or deleted.")
