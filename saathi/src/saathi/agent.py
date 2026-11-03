"""The assistant: Claude plus the module tools, in a plain tool-use loop.

The model never touches the database directly - it can only call registered tools, and every result
is returned to it as data. `client` is injectable so the loop is testable without network.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import date
from typing import Any

from .db import get_setting
from .modules import ALL, tools as registry

DEFAULT_MODEL = "claude-sonnet-5-5"
MAX_STEPS = 8


def system_prompt(conn: sqlite3.Connection, today: date | None = None) -> str:
    today = today or date.today()
    return (
        "You are Saathi, the user's private personal assistant. You manage their tasks and reminders, notes, "
        "money, and family (including parents) through tools backed by a local database.\n"
        f"Today is {today.strftime('%A')} {today.isoformat()}. Currency: {get_setting(conn, 'currency', 'INR')}.\n"
        "Rules: use tools for every fact about the user's data - never guess or invent records. Resolve relative "
        "dates ('tomorrow', 'next Friday') yourself into YYYY-MM-DD. If a person is mentioned, call list_people first "
        "and link by id; add them if missing. Do what was asked in one go; ask a question only if a required detail "
        "is truly missing. Deletions only when explicitly asked. Reply briefly and warmly; amounts with currency."
    )


def make_client(api_key: str | None = None):
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("Set ANTHROPIC_API_KEY to chat with Saathi. The other pages work without it.")
    import anthropic  # optional dependency

    return anthropic.Anthropic(api_key=key)


def run_tool(conn: sqlite3.Connection, name: str, args: dict[str, Any]) -> tuple[str, bool]:
    tool = registry(ALL).get(name)
    if tool is None:
        return json.dumps({"error": f"unknown tool {name}"}), True
    try:
        return json.dumps(tool.fn(conn, args), default=str), False
    except Exception as e:  # report to the model so it can correct itself
        conn.rollback()
        return json.dumps({"error": f"{type(e).__name__}: {e}"}), True


def chat(conn: sqlite3.Connection, history: list[dict], user_text: str, client=None, model: str | None = None,
         today: date | None = None) -> str:
    """Append the user turn, run the tool loop, append all turns to `history`, return the final text."""
    client = client or make_client()
    model = model or get_setting(conn, "model", DEFAULT_MODEL)
    schemas = [t.schema() for t in registry(ALL).values()]
    history.append({"role": "user", "content": user_text})
    for _ in range(MAX_STEPS):
        resp = client.messages.create(model=model, max_tokens=1500, system=system_prompt(conn, today),
                                      tools=schemas, messages=history)
        blocks = [b.model_dump() if hasattr(b, "model_dump") else b for b in resp.content]
        history.append({"role": "assistant", "content": blocks})
        calls = [b for b in blocks if b["type"] == "tool_use"]
        if not calls:
            return "".join(b["text"] for b in blocks if b["type"] == "text").strip()
        results = []
        for c in calls:
            out, is_err = run_tool(conn, c["name"], c["input"])
            results.append({"type": "tool_result", "tool_use_id": c["id"], "content": out, "is_error": is_err})
        history.append({"role": "user", "content": results})
    return "I got stuck partway - please try rephrasing or doing it in smaller steps."
