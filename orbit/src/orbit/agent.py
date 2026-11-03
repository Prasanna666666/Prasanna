"""The assistant: a local model (Ollama) plus the module tools, in a plain tool-calling loop.

The model can only call registered tools; every result is returned to it as data. `client` is injectable
so the loop is testable without a model.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from typing import Any

from . import llm
from .db import get_setting
from .modules import ALL, tools as registry

MAX_STEPS = 8


def system_prompt(conn: sqlite3.Connection, today: date | None = None) -> str:
    today = today or date.today()
    return (
        "You are Orbit, the user's private personal assistant, running fully on their own computer. You manage "
        "tasks and reminders, notes, money and family (including parents) through tools backed by a local database.\n"
        f"Today is {today.strftime('%A')} {today.isoformat()}. Currency: {get_setting(conn, 'currency', 'INR')}."
        "\n"
        "Rules: use tools for every fact about the user's data - never guess or invent records. Resolve relative "
        "dates ('tomorrow', 'next Friday') into YYYY-MM-DD yourself. If a person is mentioned, call list_people first "
        "and link by id; add them if missing. You are offline and have no internet access: if asked for live "
        "information (weather, news, prices) say you cannot look it up. Do what was asked in one go; ask only if a required detail is truly missing. Delete only when explicitly asked. Be brief and warm."
    )


def _coerce(tool, args: dict[str, Any]) -> dict[str, Any]:
    """Small local models often send numbers as strings; fix by the declared type."""
    out = dict(args)
    for k, v in args.items():
        t = tool.properties.get(k, {}).get("type")
        try:
            if t == "integer" and isinstance(v, (str, float)):
                out[k] = int(float(v))
            elif t == "number" and isinstance(v, str):
                out[k] = float(v.replace(",", ""))
        except ValueError:
            pass
    return out


def run_tool(conn: sqlite3.Connection, name: str, args: dict[str, Any] | str) -> tuple[str, bool]:
    tool = registry(ALL).get(name)
    if tool is None:
        return json.dumps({"error": f"unknown tool {name}"}), True
    try:
        if isinstance(args, str):
            args = json.loads(args or "{}")
        return json.dumps(tool.fn(conn, _coerce(tool, args)), default=str), False
    except Exception as e:  # reported to the model so it can correct itself
        conn.rollback()
        return json.dumps({"error": f"{type(e).__name__}: {e}"}), True


def chat(conn: sqlite3.Connection, history: list[dict], user_text: str, client=None, model: str | None = None,
         today: date | None = None) -> str:
    """Append the user turn, run the tool loop, append all turns to `history`, return the final text."""
    client = client or llm.OllamaClient(get_setting(conn, "ollama_host", "") or None)
    model = model or get_setting(conn, "model", llm.DEFAULT_MODEL)
    schemas = [t.schema() for t in registry(ALL).values()]
    history.append({"role": "user", "content": user_text})
    for _ in range(MAX_STEPS):
        msg = client.chat(model, [{"role": "system", "content": system_prompt(conn, today)}, *history], schemas)
        history.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": msg.get("tool_calls") or []})
        calls = msg.get("tool_calls") or []
        if not calls:
            return (msg.get("content") or "").strip()
        for c in calls:
            fn = c["function"]
            out, _err = run_tool(conn, fn["name"], fn.get("arguments") or {})
            history.append({"role": "tool", "tool_name": fn["name"], "content": out})
    return "I got stuck partway - please try rephrasing or doing it in smaller steps."
