"""The one assistant. A question is routed to the app (or apps) it is about, each answers with its own tools and its own checks, and the answers are put
together. Plain conversation is answered by the shared model directly.

Every question is understood and answered by the model: it decides which app a question is about and what to show, and each app's own model-driven
agent answers. The model never produces a figure on its own: figures come from the apps' tools and are checked there. When the model is not running,
the answer says so; nothing is guessed from words."""

from __future__ import annotations

import http.client
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from .registry import Module
from .upstream import Upstreams

ROUTE_SECONDS = 8.0
CHAT_SECONDS = 45.0
WARM_SECONDS = 120.0
MAX_TEXT = 2000
MAX_TURNS = 8
NUM_CTX = 4096  # the apps send the same value; a different one makes the model server reload the model every time


def clean_history(raw: Any) -> list[list[str]]:
    """The last few turns as [role, text] pairs; anything else is dropped."""
    turns: list[list[str]] = []
    for entry in raw if isinstance(raw, list) else []:
        if isinstance(entry, (list, tuple)) and len(entry) == 2 and entry[0] in ("user", "assistant") and isinstance(entry[1], str):
            turns.append([entry[0], entry[1][:MAX_TEXT]])
    return turns[-MAX_TURNS:]


@dataclass
class ModelClient:
    """The shared local model (Ollama): one short call at a time, never raising."""

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

    def chat(self, system: str, messages: list[dict[str, str]], timeout: float, max_tokens: int = 400, json_mode: bool = False) -> str | None:
        """The model's reply, or None when it is not running or too slow."""
        if not self.url or not self.model():
            return None
        request: dict[str, Any] = {
            "model": self.model(),
            "stream": False,
            "messages": [{"role": "system", "content": system}, *messages],
            "options": {"temperature": 0, "num_ctx": NUM_CTX, "num_predict": max_tokens},
        }
        if json_mode:
            request["format"] = "json"
        out = self._call("POST", "/api/chat", request, timeout)
        text = ((out or {}).get("message") or {}).get("content") if isinstance(out, dict) else None
        return str(text).strip() if text else None


@dataclass(frozen=True)
class Plan:
    """What a message needs: the apps to ask, whether it is plain conversation, what to show, and how this was decided ("model", or "down" when the model could not plan)."""

    apps: list[Module]
    chat: bool
    show: dict[str, bool]
    how: str
    search: tuple[str, ...] = ()  # how the model would look for it in files and emails: the user's words, synonyms, and the Dutch or English equivalents


class Assistant:
    def __init__(self, modules: dict[str, Module], upstreams: Upstreams, model_url: str) -> None:
        self.modules = modules
        self.upstreams = upstreams
        self.model = ModelClient(model_url)

    def _askable(self) -> list[Module]:
        return [m for m in self.modules.values() if m.ask]

    # ---- 1. understand the message: which part it is about, and whether the user wants to SEE pictures or documents ----------
    def plan(self, text: str, history: list[list[str]]) -> Plan:
        """The model reads the message (with the conversation so far) and decides. If it is not running or does not answer in the expected shape,
        the plan says so ("down") and nothing is guessed."""
        if not self._askable():
            return Plan([], True, {"photos": False, "documents": False}, "chat")
        planned = self.model_plan(text, history)
        return planned if planned is not None else Plan([], False, {"photos": False, "documents": False}, "down")

    def model_plan(self, text: str, history: list[list[str]]) -> Plan | None:
        """The model's plan, or None when it is not running or does not answer in the expected shape."""
        apps = self._askable()
        if not apps:
            return None
        parts = "; ".join(f"{m.id} = {m.tagline or m.name}" for m in apps)
        system = (
            "You are the planner of a private personal assistant. Read the user's last message, with the conversation so far, and decide what it needs. "
            f"Parts of the app: {parts}. "
            'Reply with JSON only, in this shape: {"apps": [names of the parts the message is about, or an empty list], '
            '"chat": true if it is a greeting or general conversation about none of the parts, '
            '"show": {"photos": true only if the user asks to SEE pictures, "documents": true only if the user asks to SEE files, documents or emails}, '
            '"search": up to 4 short phrases to look for in files and emails about this request: the user\'s own words, synonyms, and the same words in Dutch or English}. '
            "Questions, counts and summaries are not requests to see anything, so show stays false for them. "
            'A follow-up such as "show me those" refers to the conversation so far.'
        )
        context = "\n".join(f"{role}: {turn[:300]}" for role, turn in history[-4:])
        said = self.model.chat(
            system, [{"role": "user", "content": f"Conversation so far:\n{context or '(none)'}\n\nMessage: {text}"}], ROUTE_SECONDS, 120, True
        )
        return self._parse_plan(said, apps) if said else None

    @staticmethod
    def _parse_plan(said: str, apps: list[Module]) -> Plan | None:
        """The model's plan, checked: only known app names, only real booleans. Anything else means it did not follow the instruction (None)."""
        try:
            data = json.loads(said)
        except ValueError:
            return None
        if not isinstance(data, dict):
            return None
        named = data.get("apps")
        if not isinstance(named, list):
            return None
        raw_show = data.get("show")
        shown: dict[str, Any] = raw_show if isinstance(raw_show, dict) else {}
        chosen = [m for m in apps if m.id in named]
        show = {"photos": shown.get("photos") is True, "documents": shown.get("documents") is True}
        raw_search = data.get("search")
        search = tuple(x.strip()[:80] for x in raw_search if isinstance(x, str) and x.strip())[:4] if isinstance(raw_search, list) else ()
        return Plan(chosen, data.get("chat") is True or not chosen, show, "model", search)

    # ---- 2. the answer -----------------------------------------------------------------------------------------------
    def _chat_only(self, text: str, history: list[list[str]]) -> dict[str, Any]:
        topics = "; ".join(f"{m.name}: {m.tagline}" for m in self._askable())
        system = (
            "You are Atlas, a private assistant that lives on the user's own computer. In this reply you cannot see any of their data. "
            f"If they want something done or looked up, tell them to ask about it, for example: {topics}. Chat briefly and warmly."
        )
        turns = [{"role": r, "content": t} for r, t in history]
        reply = self.model.chat(system, [*turns, {"role": "user", "content": text}], CHAT_SECONDS)
        if reply is None:
            return {"module": "atlas", "name": "Atlas", "ok": False, "error": "The AI model is not running. Start Ollama and ask again."}
        return {"module": "atlas", "name": "Atlas", "ok": True, "text": reply, "items": [], "notes": []}

    def answer(self, text: str, conv: str, history: list[list[str]]) -> dict[str, Any]:
        """Understand the message, ask each chosen app (side by side), and return their answers as labelled parts."""
        text = text.strip()[:MAX_TEXT]
        plan = self.plan(text, history)
        if plan.how == "down":
            msg = "The AI model is not running. Start Ollama and ask again."
            return {"how": plan.how, "routed": [], "show": plan.show, "parts": [{"module": "atlas", "name": "Atlas", "ok": False, "error": msg}]}
        if not plan.apps:
            return {"how": plan.how, "routed": [], "show": plan.show, "parts": [self._chat_only(text, history)]}
        with ThreadPoolExecutor(max_workers=len(plan.apps)) as pool:
            results = list(pool.map(lambda m: self.upstreams.ask(m, text, conv, history, show=plan.show, search=list(plan.search)), plan.apps))
        parts = [{"module": m.id, "name": m.name, "show": plan.show, **r} for m, r in zip(plan.apps, results, strict=True)]
        return {"how": plan.how, "routed": [m.id for m in plan.apps], "show": plan.show, "parts": parts}
