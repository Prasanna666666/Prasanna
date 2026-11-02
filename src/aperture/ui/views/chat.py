"""Conversational agent view."""

from __future__ import annotations

import html
import json

import streamlit as st

from ... import library as lib
from ...agent.service import AgentReply
from ...bootstrap import AppContext
from ...export import create_job, read_job
from ...search.quick import quick_ids
from .. import theme
from ..components import connection, photo_grid
from ..state import start_export_job
from ..suggestions import suggest_prompts
from .onboarding import render_checklist
from .organize import move_card

KEY = "chat:messages"
PENDING = "chat:pending"
TOOL_LABEL = {
    "plan_search": "Searched the library",
    "search_visual": "Searched by what the photos show",
    "combine": "Combined results",
    "inspect": "Looked at a few photos",
    "verify_visually": "Double-checked a sample with the vision model",
    "filter_visually": "Checked every photo with the vision model",
    "suggest_defects": "Looked for badly taken photos",
    "library_overview": "Looked at what is in the library",
    "ask_user": "Asked a question",
    "finish": "Finished",
}


def _history() -> list[dict]:  # type: ignore[type-arg]
    return st.session_state.setdefault(KEY, [])


def _trace(reply) -> None:
    if not reply.trace and not reply.reports:
        return
    with st.expander("How I found this"):
        steps = []
        for step in reply.trace:
            observation = html.escape(step["observation"][:500])
            show_args = step["tool"] not in ("finish", "ask_user")
            args = f"<code>{html.escape(_pretty(step['args']))}</code>" if show_args else ""
            steps.append(
                f'<div class="ap-step"><b>{html.escape(TOOL_LABEL.get(step["tool"], step["tool"]))}</b>'
                f"<i>{html.escape(step['thought'])}</i>{args}" + (f"<code>{observation}</code>" if show_args else "") + "</div>"
            )
        if steps:
            st.html(f'<div class="ap-trace">{"".join(steps)}</div>')
        for r in reply.reports:
            st.markdown(f"- **{r.label}**: {r.matched:,} matched, {r.remaining:,} left" + (f" ({r.note})" if r.note else ""))


def _pretty(args_json: str) -> str:
    try:
        return json.dumps(json.loads(args_json), ensure_ascii=False)[:400]
    except ValueError:
        return args_json[:400]


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
        st.success(f"Copied {job.get('copied', 0)} photos to `{job.get('folder', '')}`. Your originals are untouched.")
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
    with st.container(border=True):
        folder = st.text_input("Copy into a folder named", value=reply.folder_name or "Aperture export", key=f"folder:{idx}")
        if st.button(f"Copy {len(reply.ids):,} photos", key=f"export:{idx}", type="primary", icon=":material/file_copy:"):
            jobs[idx] = job_id = create_job(ctx.paths, reply.ids.tolist(), folder)
            start_export_job(ctx, job_id)
            st.rerun()


def _render_message(ctx: AppContext, idx: int, msg: dict) -> None:  # type: ignore[type-arg]
    avatar = ":material/person:" if msg["role"] == "user" else ":material/auto_awesome:"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["text"])
        reply = msg.get("reply")
        if reply is None:
            return
        for text in reply.warnings:
            st.warning(text)
        for text in reply.notes:
            st.info(text)
        _trace(reply)
        if reply.kind == "export" and len(reply.ids):
            _export_card(ctx, idx, msg)
        if reply.kind in ("results", "export", "count") and len(reply.ids):
            if reply.kind != "count":
                move_card(ctx, reply.ids.tolist(), key=f"chatmove:{idx}")
            photo_grid(ctx, reply.ids, key=f"chat:{idx}")


_REPLIES: dict[tuple[str, int, str], AgentReply] = {}


def _cache_key(ctx: AppContext, prompt: str, previous: object) -> tuple[str, int, str] | None:
    """The same question on an unchanged library gets the same answer instantly."""
    if previous is not None:
        return None
    with connection(ctx) as conn:
        version = lib.coverage(conn).indexed + int(conn.execute("SELECT COALESCE(MAX(id),0) FROM items").fetchone()[0])
    return (" ".join(prompt.lower().split()), version, f"{ctx.settings.ollama_model}|{ctx.settings.agentic}")


def _preview(ctx: AppContext, prompt: str) -> None:
    """Show instant matches while the AI works out what was meant."""
    try:
        with connection(ctx) as conn:
            ids = quick_ids(conn, prompt, ctx.embedding_index, ctx.search_embedder, ctx.settings.visual_strictness)
    except Exception:
        return
    if len(ids):
        st.caption(f"Quick matches ({len(ids):,}) while the AI checks your request...")
        photo_grid(ctx, ids, key="quick")


def _welcome(ctx: AppContext) -> None:
    theme.hero(
        "What are you looking for?",
        "Describe it in your own words: what it shows, who is in it, where, when, or text written on it.",
    )
    with connection(ctx) as conn:
        cov = lib.coverage(conn)
        people = conn.execute("SELECT COUNT(DISTINCT person_id) FROM faces WHERE person_id IS NOT NULL").fetchone()[0]
        places = conn.execute("SELECT COUNT(DISTINCT place) FROM items WHERE place IS NOT NULL AND missing=0").fetchone()[0]
        ideas = suggest_prompts(conn) if cov.indexed else []
    if cov.total:
        theme.stats(
            [
                ("Photos and files", f"{cov.total:,}"),
                ("Indexed", f"{cov.indexed / cov.total:.0%}"),
                ("People found", f"{people:,}"),
                ("Places", f"{places:,}"),
            ]
        )
    render_checklist(ctx)
    if ideas:
        st.caption("Try asking")
        for cell, idea in zip(st.columns(3), ideas, strict=False):
            if cell.button(idea, key=f"idea:{idea}", use_container_width=True):
                st.session_state[PENDING] = idea
                st.rerun()


def render(ctx: AppContext) -> None:
    history = _history()
    if not history:
        _welcome(ctx)
    else:
        st.title("Ask Lumo")
        if st.button("New conversation", icon=":material/add_comment:", type="tertiary"):
            history.clear()
            st.rerun()
    for idx, msg in enumerate(history):
        _render_message(ctx, idx, msg)
    prompt = st.chat_input("Ask for anything: 'Anna at the beach last summer', 'night photos near Eindhoven', 'blurry shots'...")
    prompt = prompt or st.session_state.pop(PENDING, None)
    if not prompt:
        return
    previous = next((m["reply"].ids for m in reversed(history) if m.get("reply") is not None and len(m["reply"].ids)), None)
    history.append({"role": "user", "text": prompt})
    key = _cache_key(ctx, prompt, previous)
    reply = _REPLIES.get(key) if key else None
    if reply is None:
        _preview(ctx, prompt)
        with st.status("Checking with the AI...", expanded=False) as status:
            reply = ctx.agent().ask(prompt, previous)
            status.update(label="Done", state="complete" if reply.kind != "error" else "error")
        if key and reply.kind in ("results", "count"):
            _REPLIES[key] = reply
    history.append({"role": "assistant", "text": reply.text, "reply": reply})
    st.rerun()
