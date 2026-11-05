"""The assistant: a router plus specialist agents (agents.py), each a local-model tool-calling loop.

The model can only call tools its agent is allowed to use (enforced here, not just suggested in the prompt);
every result is returned to it as data. `client` is injectable so everything is testable without a model.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from datetime import date
from typing import Any

from . import agents, answers, llm
from .db import get_setting
from .modules import ALL
from .modules import tools as registry

MAX_STEPS = 8
REPLY_SECONDS = 30  # how long the agent may work on one answer; change it in Settings (reply_seconds)


def reply_seconds(conn) -> int:
    try:
        return max(10, min(180, int(get_setting(conn, "reply_seconds", str(REPLY_SECONDS)))))
    except ValueError:
        return REPLY_SECONDS


def system_prompt(conn: sqlite3.Connection, today: date | None = None, role: str = "") -> str:
    today = today or date.today()
    return (
        "You are Orbit, the user's private personal assistant, running fully on their own computer. "
        + (role + " " if role else "You can use every tool. ")
        + "You work through tools backed by a local database.\n"
        f"Today is {today.strftime('%A')} {today.isoformat()}. Currency: {get_setting(conn, 'currency', 'EUR')}.\n"
        "Rules: use tools for every fact about the user's data - never guess or invent records. Resolve relative "
        "dates ('tomorrow', 'next Friday') into YYYY-MM-DD yourself. If a person is mentioned, call list_people first "
        "and link by id. You are offline and have no internet access: if asked for live information (weather, news, "
        "prices) say you cannot look it up. Do what was asked in one go; ask only if a required detail is truly "
        "missing. Delete only when explicitly asked. Be brief and warm."
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


def run_tool(conn: sqlite3.Connection, name: str, args: dict[str, Any] | str,
             allowed: frozenset[str] | None = None) -> tuple[str, bool]:
    tool = registry(ALL).get(name)
    if tool is None or (allowed is not None and name not in allowed):
        return json.dumps({"error": f"tool {name!r} is not available"}), True
    try:
        if isinstance(args, str):
            args = json.loads(args or "{}")
        return json.dumps(tool.fn(conn, _coerce(tool, args)), default=str), False
    except Exception as e:  # reported to the model so it can correct itself
        conn.rollback()
        return json.dumps({"error": f"{type(e).__name__}: {e}"}), True


def _classifier(client, model: str):
    def classify(text: str, names: list[str]) -> str:
        msg = client.chat(model, [
            {"role": "system", "content": "Reply with exactly one word: " + ", ".join(names) + ", chat (greetings, thanks, small talk or a "
             "general question that needs none of the user's data), or general (a request that spans several areas or fits none). No other text."},
            {"role": "user", "content": text}])
        return msg.get("content") or ""
    return classify


def chat(conn: sqlite3.Connection, history: list[dict], user_text: str, client=None, model: str | None = None,
         today: date | None = None, trace: list | None = None) -> str:
    """Route to a specialist, run its tool loop, append every turn to `history`, return the final text.

    `trace` (optional) receives {'agent': name, 'tools': [names]} so the UI can show who answered.
    """
    start = len(history)
    try:
        client = client or llm.OllamaClient(get_setting(conn, "ollama_host", "") or None)
        model = model or get_setting(conn, "model", llm.DEFAULT_MODEL)
        if hasattr(client, "resolve"):
            model = client.resolve(model)
        client.deadline = time.monotonic() + reply_seconds(conn)  # the agent gets this long
        reply = _chat(conn, history, user_text, client, model, today, trace)
    except (llm.Slow, RuntimeError) as exc:  # too slow, or the model is not running
        return _fallback(conn, history, start, user_text, trace, exc)
    finally:
        if client is not None:
            client.deadline = None
    problems, notes = answers.audit(conn, reply, history[start:])  # every answer is checked against your data before you see it
    if problems:
        return _fallback(conn, history, start, user_text, trace, None, problems)
    if trace is not None and trace:
        trace[0]["tools"].append("checked")
    return reply + ("\n\n" + " ".join(notes) if notes else "")


def _fallback(conn, history, start, user_text, trace, exc, problems=()):
    """The agent could not finish, or its answer failed a check. Code gives the exact answer for a common question - itself checked - else says plainly why not."""
    del history[start:]
    used: list[str] = []
    quick = answers.answer(conn, user_text, used)
    if quick:
        bad, notes = answers.audit(conn, quick, [], used)  # the code answer is held to the ledger tie-out and the data-health note as well
        if not bad:
            reply = quick + ("\n\n" + " ".join(notes) if notes else "")
            history.extend([{"role": "user", "content": user_text}, {"role": "assistant", "content": reply}])
            if trace is not None:
                trace.append({"agent": "instant", "tools": ["checked"]})
            return reply
        problems = [*problems, *bad]
    if isinstance(exc, RuntimeError) and not isinstance(exc, llm.Slow):
        raise exc  # the model is not running and this is not a question code can answer: say so plainly
    if problems:
        reply = "I can't give you that figure with confidence: " + problems[0] + ". Open Money > Files to see what needs a check."
    else:
        reply = f"This needs more thinking than I can do in {reply_seconds(conn)} seconds. Try a shorter question, such as \"How much did I spend last month?\"."
    history.extend([{"role": "user", "content": user_text}, {"role": "assistant", "content": reply}])
    return reply


def _chat(conn, history, user_text, client, model, today, trace):
    name = agents.route(user_text, _classifier(client, model))
    spec = agents.BY_NAME.get(name)
    allowed = frozenset() if name == "chat" else (spec.tools if spec else None)  # chat = no tools; None = general: every tool
    schemas = [t.schema() for t in registry(ALL).values() if allowed is None or t.name in allowed]
    used: list[str] = []
    if trace is not None:
        trace.append({"agent": name, "tools": used})
    history.append({"role": "user", "content": user_text})
    for _ in range(MAX_STEPS):
        if name == "chat":  # no tools, a short prompt: this is what keeps "Hi" fast
            system = ("You are Orbit, the user's private personal assistant, running on their own computer. Chat briefly and warmly. "
                      "You cannot see their data in this reply; if they want something done, tell them to ask for it.")
        else:
            system = system_prompt(conn, today, spec.role if spec else "")
        msg = client.chat(model, [{"role": "system", "content": system}, *history], schemas)
        calls = msg.get("tool_calls") or []
        history.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        if not calls:
            return (msg.get("content") or "").strip()
        for c in calls:
            fn = c["function"]
            used.append(fn["name"])
            if fn["name"].startswith("delete_") and (allowed is None or fn["name"] in allowed) and not re.search(r"\b(delete|remove|erase|clear|get rid)\b", user_text.lower()):
                # text inside a document must never be able to make the agent delete your data: only your own words can
                out, _err = json.dumps({"error": "refused: deleting needs you to ask for it in your own words"}), True
            else:
                out, _err = run_tool(conn, fn["name"], fn.get("arguments") or {}, allowed)
            history.append({"role": "tool", "tool_name": fn["name"], "content": out})
    return "I got stuck partway - please try rephrasing or doing it in smaller steps."
