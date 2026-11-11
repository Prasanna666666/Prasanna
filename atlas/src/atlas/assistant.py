"""The one assistant, over all of the person's data.

There is one model and one conversation. Every part of the app (money, documents and mail, pictures, and whatever comes next) publishes the tools it has,
and this assistant can use any of them in any order inside one answer: the dates on a ticket, then what was spent on those days, then the pictures taken
on them. The model decides what to look up and in what order; the tools do all the looking, counting and adding; and every figure in the answer is checked
against what the tools returned before it is shown. When the model is not running the answer says so; nothing is guessed from words."""

from __future__ import annotations

import http.client
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from urllib.parse import urlsplit

from kit import consent
from kit.audit import unproven_figures
from kit.llm import KEEP

from .registry import Module
from .upstream import Upstreams

CALL_SECONDS = 90.0
WARM_SECONDS = 120.0
MAX_TEXT = 2000
MAX_TURNS = 8
MAX_STEPS = 8
MAX_PICKED = 10  # tools the model may carry into one answer: the window is small, and the index of every tool would not fit beside the conversation
INDEX_LINE_CHARS = 80
TOOL_RESULT_CHARS = 2500  # the model's window is 4096 tokens: a long result would push the question out of it
HISTORY_TURNS = 6
HISTORY_CHARS = 600
TOOLS_CACHED_SECONDS = 60.0
KEEP_LOADED = KEEP  # the same value every app sends, so the model server never reloads the model because two parts disagree
NUM_CTX = 4096  # the apps send the same value; a different one makes the model server reload the model every time
SEPARATOR = "__"


def clean_history(raw: Any) -> list[list[str]]:
    """The last few turns as [role, text] pairs; anything else is dropped."""
    turns: list[list[str]] = []
    for entry in raw if isinstance(raw, list) else []:
        if isinstance(entry, (list, tuple)) and len(entry) == 2 and entry[0] in ("user", "assistant") and isinstance(entry[1], str):
            turns.append([entry[0], entry[1][:MAX_TEXT]])
    return turns[-MAX_TURNS:]


@dataclass
class ModelClient:
    """The shared local model (Ollama): one call at a time, never raising."""

    url: str
    _model: str = field(default="", init=False)

    def _call(self, method: str, path: str, body: dict[str, Any] | None, timeout: float) -> Any:
        parts = urlsplit(self.url)
        conn = http.client.HTTPConnection(parts.hostname or "127.0.0.1", parts.port or 11434, timeout=timeout)
        payload = json.dumps(body).encode() if body is not None else None
        try:
            conn.request(method, path, body=payload, headers={"Host": f"127.0.0.1:{parts.port or 11434}", "Content-Type": "application/json"})
            response = conn.getresponse()
            data = response.read(2_000_000)
            return json.loads(data) if response.status == 200 else None
        except (OSError, http.client.HTTPException, ValueError):
            return None
        finally:
            conn.close()

    def warm(self) -> None:
        """Load the model in the background so the first question does not wait for it (the same context size as the apps, so nothing reloads)."""
        if self.url and self.model():
            self.chat("Reply with one word.", [{"role": "user", "content": "hi"}], WARM_SECONDS, max_tokens=1)

    def model(self) -> str:
        if self._model:
            return self._model
        tags = self._call("GET", "/api/tags", None, 3.0) or {}
        names = [str(m.get("name", "")) for m in tags.get("models", []) if isinstance(m, dict) and m.get("name")]
        self._model = next((n for n in names if n.startswith("ministral")), names[0] if names else "")
        return self._model

    def _request(
        self, messages: list[dict[str, Any]], timeout: float, max_tokens: int, tools: list[dict[str, Any]] | None = None, schema: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        if not self.url or not self.model():
            return None
        request: dict[str, Any] = {
            "model": self.model(),
            "stream": False,
            "messages": messages,
            "keep_alive": KEEP_LOADED,
            "options": {"temperature": 0.1, "num_ctx": NUM_CTX, "num_predict": max_tokens},
        }
        if tools:
            request["tools"] = tools
        if schema:
            request["format"] = schema
            request["options"]["temperature"] = 0
        out = self._call("POST", "/api/chat", request, timeout)
        message = out.get("message") if isinstance(out, dict) else None
        return message if isinstance(message, dict) else None

    def chat(self, system: str, messages: list[dict[str, str]], timeout: float, max_tokens: int = 400) -> str | None:
        """The model's reply, or None when it is not running or too slow."""
        message = self._request([{"role": "system", "content": system}, *messages], timeout, max_tokens)
        text = message.get("content") if message else None
        return str(text).strip() if text else None

    def pick(self, system: str, user: str, schema: dict[str, Any], timeout: float = CALL_SECONDS) -> dict[str, Any] | None:
        """A short answer forced into a shape (Ollama's constrained output): the parsed JSON, or None when the model is not running or does not comply."""
        message = self._request([{"role": "system", "content": system}, {"role": "user", "content": user}], timeout, 200, schema=schema)
        try:
            data = json.loads((message or {}).get("content") or "")
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    def step(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], timeout: float = CALL_SECONDS) -> dict[str, Any] | None:
        """One turn of the assistant loop: the model's message (text and/or tool calls), or None when it is not running or too slow."""
        return self._request(messages, timeout, 700, tools)


@dataclass
class Turn:
    """What happened while answering one question: the text asked, the tools that exist, which parts were used, what the tools returned, what to show."""

    text: str
    by_name: dict[str, Tool]
    id: str = field(default_factory=lambda: uuid.uuid4().hex)  # names this question: a change prepared in it can only be confirmed in a later one
    messages: list[dict[str, Any]] = field(default_factory=list)
    used: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    items: list[dict[str, str]] = field(default_factory=list)
    show: bool = False  # the model judged that the person asked to SEE pictures or files; then every tool that can show them is told to
    nudged: bool = False
    asked_to_show: bool = False  # the model asked for pictures or files to be shown (whether or not any were found)
    notes: list[str] = field(default_factory=list)  # things the person must be told next to a figure (a month that is not proven, files waiting for a check)


@dataclass(frozen=True)
class Tool:
    """One tool of one part of the app, as the model sees it."""

    module: Module
    name: str
    description: str
    parameters: dict[str, Any]

    @property
    def public(self) -> str:
        return f"{self.module.id}{SEPARATOR}{self.name}"

    @property
    def line(self) -> str:
        """One short line for the index the model chooses from: the name and the start of what it does."""
        return f"{self.public}: {' '.join(self.description.split())[:INDEX_LINE_CHARS]}"

    def schema(self) -> dict[str, Any]:
        return {"type": "function", "function": {"name": self.public, "description": self.description[:600], "parameters": self.parameters}}


def system_prompt(today: date) -> str:
    return (
        "You are Atlas, the user's private personal assistant. You run on their own computer and can reach all of their data through tools: money, files and "
        "mail, pictures. Use the tools for anything about their data; never state a figure, date or fact about them that a tool did not return. Chain tools "
        "when a question needs it (for example: find the dates of a trip in the tickets, then look up what was spent on those days, then the pictures taken "
        "on them). Only use the tools that the question needs. Show pictures or files (the tools' show argument) ONLY when the user asks to see them; "
        'a count or a question is answered in words. Answer briefly in the user\'s language, in plain words. Greetings and general questions need no tool, but any question about their own data MUST call a tool first; a follow-up ("show me those") '
        "repeats the earlier tool with the same details and show true. "
        f"Today is {today.isoformat()}."
    )


class Assistant:
    def __init__(self, modules: dict[str, Module], upstreams: Upstreams, model_url: str) -> None:
        self.modules = modules
        self.upstreams = upstreams
        self.model = ModelClient(model_url)
        self._tools: tuple[float, list[Tool]] | None = None
        self._lock = threading.Lock()

    def tools(self) -> list[Tool]:
        """Every tool of every part that is running (listed again every minute, so a part that starts later joins in)."""
        with self._lock:
            if self._tools and time.monotonic() - self._tools[0] < TOOLS_CACHED_SECONDS:
                return self._tools[1]
        found = [
            Tool(m, str(spec["name"]), str(spec.get("description", "")), spec["parameters"])
            for m in self.modules.values()
            if m.tool
            for spec in self.upstreams.tool_specs(m)
        ]
        with self._lock:
            if found:
                self._tools = (time.monotonic(), found)
        return found

    @staticmethod
    def _allowed(tool: Tool, text: str) -> bool:
        """A tool that deletes is offered only when the person's own words call for it (a change to their pictures is never made by a tool: the person confirms it in a window)."""
        if tool.name.startswith("delete_"):
            return consent.says(consent.DELETE, text)
        return True

    def choose(self, text: str, history: list[list[str]], tools: list[Tool]) -> tuple[list[Tool], bool] | None:
        """Which tools this message may need (at most MAX_PICKED), chosen by the model from a one-line index of all of them; none for plain conversation.
        Also whether the person asked to SEE pictures or files. None if the model is not running. Only the chosen tools are described in full afterwards, so any number of tools fits the small window."""
        if not tools:
            return [], False
        names = [t.public for t in tools]

        def shape(at_least: int) -> dict[str, Any]:
            return {
                "type": "object",
                "properties": {
                    "about_their_data": {"type": "boolean"},  # decided first: is it about their money, files, mail, pictures, trips?
                    "wants_to_see": {
                        "type": "boolean"
                    },  # do they ask to SEE pictures, documents or mail (show, give me, I want to see), not just count or ask?
                    "tools": {"type": "array", "items": {"type": "string", "enum": names}, "minItems": at_least, "maxItems": MAX_PICKED},
                },
                "required": ["about_their_data", "wants_to_see", "tools"],
            }

        system = (
            "You choose which tools an assistant needs to answer the user's last message. Choose every tool the answer may need, including a tool that must run "
            "after another (for example one that finds the dates of a trip, and then ones that use those dates). Choose none ONLY for a greeting or a general "
            "question about the world that needs no data of theirs. Anything about their money, payments, bills, files, mail, documents, pictures, trips or "
            'saving, and any follow-up to such a question ("and the month before?", "show me those"), needs tools: when unsure, choose them. Choose from EVERY kind of data the question touches (money, files and mail, pictures): a trip and what it cost needs both. '
            f" At most {MAX_PICKED}. The tools:\n" + "\n".join(t.line for t in tools)
        )
        context = "\n".join(f"{role}: {turn[:300]}" for role, turn in history[-4:])
        question = f"Conversation so far:\n{context or '(none)'}\n\nMessage: {text}"
        picked = self.model.pick(system, question, shape(0))
        if picked is None:
            return None
        if (picked.get("about_their_data") is True or picked.get("wants_to_see") is True) and not picked.get(
            "tools"
        ):  # wanting to see something is about their data too: ask once more, now that a tool is required
            picked = self.model.pick(system, question, shape(1)) or picked
        chosen = picked.get("tools")
        wanted = {n for n in chosen if isinstance(n, str)} if isinstance(chosen, list) else set()
        return [t for t in tools if t.public in wanted], picked.get("wants_to_see") is True

    def answer(self, text: str, conv: str, history: list[list[str]]) -> dict[str, Any]:
        """One question: the model uses whichever tools of whichever parts it needs, then answers. Returns the answer as one labelled part."""
        text = text.strip()[:MAX_TEXT]
        tools = [t for t in self.tools() if self._allowed(t, text)]
        chosen = self.choose(text, history, tools)
        if chosen is None:
            return self._reply(False, "The AI model is not running. Start Ollama and ask again.", Turn(text, {}))
        tools, wants_to_see = chosen
        turn = Turn(text, {t.public: t for t in tools}, show=wants_to_see)
        turn.messages = [
            {"role": "system", "content": system_prompt(datetime.now().astimezone().date())},
            *({"role": r, "content": t[:HISTORY_CHARS]} for r, t in history[-HISTORY_TURNS:]),
            {"role": "user", "content": text},
        ]
        for _ in range(MAX_STEPS):
            message = self.model.step(turn.messages, [t.schema() for t in tools])
            if message is None:
                return self._reply(False, "The AI model is not running. Start Ollama and ask again.", turn)
            calls = message.get("tool_calls") or []
            turn.messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": calls})
            if not calls:
                nudge = self._nudge(turn)
                if nudge:  # answering without the data it was given tools for, or leaving out a kind of data the question touches: told once, then it answers
                    turn.messages.append({"role": "user", "content": nudge})
                    continue
                return self._checked(str(message.get("content") or "").strip(), turn)
            for call in calls:
                self._run(call, turn)
        return self._reply(False, "That needed more steps than I can take in one go. Try asking in smaller pieces.", turn)

    def _run(self, call: Any, turn: Turn) -> None:
        function = call.get("function") if isinstance(call, dict) else None
        name = str((function or {}).get("name", ""))
        tool = turn.by_name.get(name)
        raw_args = (function or {}).get("arguments") or {}
        args = raw_args if isinstance(raw_args, dict) else {}
        if turn.show and tool is not None and "show" in tool.parameters.get("properties", {}):
            args = {**args, "show": True}  # decided once, by the model, for the whole question: a small model forgets the argument
        if tool is None:
            result: dict[str, Any] = {"ok": False, "error": f"tool {name!r} is not available"}
        else:
            result = self.upstreams.call_tool(tool.module, tool.name, args, turn.text, turn.id)
            if tool.module.id not in turn.used:
                turn.used.append(tool.module.id)
            turn.notes.extend(n for n in result.get("notes") or [] if n not in turn.notes)
            turn.asked_to_show = turn.asked_to_show or args.get("show") is True
            for item in result.get("items") or []:
                # a change waiting for the person is always shown (it needs them); pictures and files only when the model says the person asked to see them
                if item["kind"] == "confirm" or args.get("show") is True:
                    turn.items.append({**item, "module": tool.module.id})
        body = json.dumps({"error": result["error"]} if not result.get("ok") else result.get("data"), default=str)[:TOOL_RESULT_CHARS]
        turn.outputs.append(body)
        turn.messages.append({"role": "tool", "tool_name": name, "content": body})

    def _checked(self, reply: str, turn: Turn) -> dict[str, Any]:
        """Every figure in the answer must have come from a tool. If one did not, the model is told once and answers again; if it still invents one,
        the answer is refused instead of shown."""
        unproven = unproven_figures(reply, turn.outputs)
        if unproven:
            note = (
                "These figures were not returned by any tool: "
                + ", ".join(f"{n:g}" for n in unproven)
                + ". Answer again using only figures the tools returned."
            )
            again = self.model.step([*turn.messages, {"role": "user", "content": note}], [])
            reply = str((again or {}).get("content") or "").strip()
            unproven = unproven_figures(reply, turn.outputs) if reply else unproven
            if unproven or not reply:
                return self._reply(
                    False, "I can't give you that figure with confidence: figures not returned by any tool: " + ", ".join(f"{n:g}" for n in unproven), turn
                )
        return self._reply(True, reply or "I have nothing to add.", turn)

    @staticmethod
    def _nudge(turn: Turn) -> str:
        """One reminder per question, when the model is about to answer without having used its tools, or without a part of the app the question touches."""
        if turn.nudged or not turn.by_name:
            return ""
        turn.nudged = True
        if not turn.used:
            return "You have tools for this. Call the right tool now to get the data; do not answer from memory."
        unused = [t.public for t in turn.by_name.values() if t.module.id not in turn.used][:4]
        if unused:
            return "If the question also asks for data from another part, call one of these now: " + ", ".join(unused) + ". If not, answer."
        return ""

    @staticmethod
    def _reply(ok: bool, text: str, turn: Turn) -> dict[str, Any]:
        used, items = turn.used, turn.items
        show = {
            "photos": any(i["kind"] == "photo" for i in items),
            "documents": any(i["kind"] == "document" for i in items),
        }
        part: dict[str, Any] = {"module": "atlas", "name": "Atlas", "ok": ok, "show": show}
        part.update({"text": text, "items": items, "notes": turn.notes[:3]} if ok else {"error": text})
        return {"how": "agent" if ok else "down", "routed": used, "show": show, "asked_to_show": turn.asked_to_show, "parts": [part]}
