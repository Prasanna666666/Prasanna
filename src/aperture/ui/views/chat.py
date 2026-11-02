"""Conversational agent view."""

from __future__ import annotations

import streamlit as st

from ...bootstrap import AppContext
from ...export import create_job, read_job
from ..components import photo_grid
from ..state import start_export_job
from .organize import move_card

KEY = "chat:messages"


def _history() -> list[dict]:  # type: ignore[type-arg]
    return st.session_state.setdefault(KEY, [])


def _explain(msg: dict) -> None:  # type: ignore[type-arg]
    reply = msg["reply"]
    for text in reply.warnings:
        st.warning(text)
    for text in reply.notes:
        st.info(text)
    if reply.reports:
        with st.expander("How I searched"):
            for r in reply.reports:
                st.markdown(
                    f"- **{r.label}** - {r.matched:,} matched, {r.remaining:,} remaining" + (f" ({r.note})" if r.note else "")
                )


@st.fragment(run_every=2)
def _job_status(ctx: AppContext, job_id: str) -> None:
    job = read_job(ctx.paths, job_id)
    if not job:
        st.warning("Export job not found.")
        return
    state, done, total = job.get("state"), int(str(job.get("done") or 0)), max(1, int(str(job.get("total") or 1)))
    if state in ("queued", "running"):
        st.progress(min(done / total, 1.0), text=f"Copying {done:,} of {total:,}...")
    elif state == "done":
        st.success(f"Copied {job.get('copied', 0)} photos to `{job.get('folder', '')}` (originals untouched).")
    else:
        st.error(f"Export {state}: {job.get('error', 'see the log on the drive')}")


def _export_card(ctx: AppContext, idx: int, msg: dict) -> None:  # type: ignore[type-arg]
    reply = msg["reply"]
    if not ctx.settings.export_dir:
        st.warning("Choose an export folder in Settings first.")
        return
    jobs = st.session_state.setdefault("chat:jobs", {})
    if idx in jobs:
        _job_status(ctx, jobs[idx])
        return
    folder = st.text_input("Folder name", value=reply.folder_name or "Aperture export", key=f"folder:{idx}")
    if st.button(f"Copy {len(reply.ids):,} photos to the export folder", key=f"export:{idx}", type="primary"):
        jobs[idx] = job_id = create_job(ctx.paths, reply.ids.tolist(), folder)
        start_export_job(ctx, job_id)
        st.rerun()


def _render_message(ctx: AppContext, idx: int, msg: dict) -> None:  # type: ignore[type-arg]
    with st.chat_message(msg["role"]):
        st.markdown(msg["text"])
        reply = msg.get("reply")
        if reply is None:
            return
        _explain(msg)
        if reply.kind == "export" and len(reply.ids):
            _export_card(ctx, idx, msg)
        if reply.kind in ("results", "export") and len(reply.ids):
            move_card(ctx, reply.ids.tolist(), key=f"chatmove:{idx}")
            photo_grid(ctx, reply.ids, key=f"chat:{idx}")


def render(ctx: AppContext) -> None:
    st.title("Ask Aperture")
    st.caption("Describe what you want in your own words: subjects, text in photos, people, places, dates, or a combination.")
    history = _history()
    cols = st.columns([1, 6])
    if history and cols[0].button("Clear chat", icon=":material/delete_sweep:"):
        history.clear()
        st.rerun()
    for idx, msg in enumerate(history):
        _render_message(ctx, idx, msg)
    prompt = st.chat_input("e.g. photos of Anna at the beach in summer 2021, or documents mentioning 'invoice'")
    if not prompt:
        return
    previous = next((m["reply"].ids for m in reversed(history) if m.get("reply") is not None and len(m["reply"].ids)), None)
    history.append({"role": "user", "text": prompt})
    with st.spinner("Thinking..."):
        reply = ctx.agent().ask(prompt, previous)
    history.append({"role": "assistant", "text": reply.text, "reply": reply})
    st.rerun()
