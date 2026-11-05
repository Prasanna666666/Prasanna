"""The one assistant. A question is routed to the app (or apps) it is about, each answers with its own tools and its own checks, and the answers are put
together. Plain conversation is answered by the shared model directly.

The model is used for two small jobs only: deciding which app a question is about when its words do not say, and chatting. It never produces a figure:
figures come from the apps' tools and are checked there."""

from __future__ import annotations

import http.client
import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from .registry import Module
from .upstream import Upstreams

ROUTE_SECONDS = 8.0
CHAT_SECONDS = 45.0
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


SHOW_VERBS = re.compile(
    r"\b(show|display|give|send|bring|pull up|let me see|can i see|could i see|open|list|get me|fetch|browse|find me|find all|find the|find some)\b"
)
PHOTO_WORDS = r"photos?|pictures?|pics?|images?|selfies|selfie|albums?|screenshots?"
DOCUMENT_WORDS = r"documents?|docs?|files?|invoices?|payslips?|receipts?|statements?|pdfs?|tickets?|reports?|contracts?|letters?"
QUESTION_START = re.compile(r"^\s*(how many|how much|how often|how long|when|what|which|who|where|why|do i|did i|have i|am i|is there|are there|count)\b")


def wants_to_see(text: str) -> dict[str, bool]:
    """Did the user ask to SEE pictures or documents? Only then are they shown; otherwise the answer is words (with the pictures one tap away).
    "How many photos of Amma do I have?" is a question; "show me photos of Amma" or "pictures from Goa" is a request."""
    low = text.lower()
    asked = bool(SHOW_VERBS.search(low))
    if QUESTION_START.match(low) and not asked:
        return {"photos": False, "documents": False}
    return {
        "photos": bool(re.search(rf"\b({PHOTO_WORDS})\b", low)) and (asked or bool(re.search(rf"\b({PHOTO_WORDS}) (of|from|with|at|in|taken)\b", low))),
        "documents": bool(re.search(rf"\b({DOCUMENT_WORDS})\b", low)) and (asked or bool(re.search(rf"\b({DOCUMENT_WORDS}) (of|from|about|for)\b", low))),
    }


def _words(text: str) -> str:
    return " " + re.sub(r"[^\w€₹£]+", " ", text.lower()) + " "


def match_by_words(text: str, modules: list[Module]) -> list[Module]:
    """The apps whose own keywords appear in the question (whole words or phrases), in menu order."""
    haystack = _words(text)
    return [m for m in modules if any(_words(k) in haystack for k in m.keywords)]


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

    def model(self) -> str:
        if self._model:
            return self._model
        tags = self._call("GET", "/api/tags", None, 3.0) or {}
        names = [str(m.get("name", "")) for m in tags.get("models", []) if isinstance(m, dict) and m.get("name")]
        self._model = next((n for n in names if n.startswith("ministral")), names[0] if names else "")
        return self._model

    def chat(self, system: str, messages: list[dict[str, str]], timeout: float, max_tokens: int = 400) -> str | None:
        """The model's reply, or None when it is not running or too slow."""
        if not self.url or not self.model():
            return None
        out = self._call(
            "POST",
            "/api/chat",
            {
                "model": self.model(),
                "stream": False,
                "messages": [{"role": "system", "content": system}, *messages],
                "options": {"temperature": 0, "num_ctx": NUM_CTX, "num_predict": max_tokens},
            },
            timeout,
        )
        text = ((out or {}).get("message") or {}).get("content") if isinstance(out, dict) else None
        return str(text).strip() if text else None


class Assistant:
    def __init__(self, modules: dict[str, Module], upstreams: Upstreams, model_url: str) -> None:
        self.modules = modules
        self.upstreams = upstreams
        self.model = ModelClient(model_url)

    def _askable(self) -> list[Module]:
        return [m for m in self.modules.values() if m.ask]

    # ---- 1. which app is this about? Words first (instant), the model only when the words do not say ------------------
    def route(self, text: str) -> tuple[list[Module], str]:
        """(apps to ask, how it was decided). An empty list with 'chat' means plain conversation; with 'unsure' it means we could not tell."""
        apps = self._askable()
        hit = match_by_words(text, apps)
        if hit:
            return hit, "words"
        if not apps:
            return [], "chat"
        names = ", ".join(f"{m.id} = {m.tagline or m.name}" for m in apps)
        system = (
            f"Decide which part of a private personal app a message is about. Parts: {names}. "
            f"Answer with the part names separated by commas, or the single word chat when it is a greeting or a general question about neither part. "
            "Answer with nothing else."
        )
        said = self.model.chat(system, [{"role": "user", "content": text}], ROUTE_SECONDS, max_tokens=12)
        if said is None:
            return [], "unsure"
        return self._parse_route(said, apps)

    @staticmethod
    def _parse_route(said: str, apps: list[Module]) -> tuple[list[Module], str]:
        """Accept only a short answer made of app names (or "both"/"chat"). A rambling reply means the model did not follow the instruction: treat it as chat."""
        ids = {m.id for m in apps}
        tokens = re.findall(r"[a-z]+", said.lower())
        if len(said) > 40 or not tokens or any(t not in ids | {"chat", "both", "and", "none"} for t in tokens):
            return [], "chat"
        chosen = apps if "both" in tokens else [m for m in apps if m.id in tokens]
        return (chosen, "model") if chosen else ([], "chat")

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
        """Route the question, ask each chosen app (side by side), and return their answers as labelled parts."""
        text = text.strip()[:MAX_TEXT]
        show = wants_to_see(text)
        targets, how = self.route(text)
        if how == "unsure":
            msg = "I could not tell whether that is about " + " or ".join(m.name.lower() for m in self._askable()) + ". Try saying which."
            return {"how": how, "routed": [], "show": show, "parts": [{"module": "atlas", "name": "Atlas", "ok": False, "error": msg}]}
        if not targets:
            return {"how": how, "routed": [], "show": show, "parts": [self._chat_only(text, history)]}
        with ThreadPoolExecutor(max_workers=len(targets)) as pool:
            results = list(pool.map(lambda m: self.upstreams.ask(m, text, conv, history, show), targets))
        parts = [{"module": m.id, "name": m.name, "show": show, **r} for m, r in zip(targets, results, strict=True)]
        return {"how": how, "routed": [m.id for m in targets], "show": show, "parts": parts}
