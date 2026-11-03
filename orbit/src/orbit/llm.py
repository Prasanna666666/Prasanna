"""Local model access (Ollama). No cloud model is used anywhere in Orbit."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any

from . import netguard

DEFAULT_MODEL = "ministral-3:3b"  # not verifiable from the build sandbox: resolve() falls back if it is not installed
FALLBACKS = ("llama3.2:3b", "qwen2.5:3b")


def host() -> str:
    return os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")


class OllamaClient:
    def __init__(self, base: str | None = None):
        self.base = base or host()
        netguard.allow_local(urllib.parse.urlparse(self.base).hostname or "localhost")

    def _call(self, path: str, body: dict | None = None, timeout: int = 300) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{self.base}{path}", data, {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - local host only (netguard)
                return json.load(r)
        except OSError as e:
            raise RuntimeError(f"Cannot reach the local model server at {self.base} ({e}). Is Ollama running?") from e

    def installed(self) -> list[str]:
        return [m["name"] for m in self._call("/api/tags", timeout=10).get("models", [])]

    def resolve(self, preferred: str) -> str:
        """The preferred model if installed, else the first installed fallback, else a helpful error."""
        names = self.installed()
        have = set(names) | {n.removesuffix(":latest") for n in names}
        for cand in (preferred, *FALLBACKS):
            if cand in have:
                return cand
        raise RuntimeError(f"Model {preferred!r} is not installed (installed: {', '.join(names) or 'none'}). "
                           f"Run:  ollama pull {preferred}")

    def chat(self, model: str, messages: list[dict], tools: list[dict] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"model": model, "messages": messages, "stream": False, "keep_alive": "10m",
                                "options": {"temperature": 0.2, "num_ctx": 4096}}
        if tools:
            body["tools"] = tools
        return self._call("/api/chat", body)["message"]
