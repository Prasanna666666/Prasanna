"""Local model access (Ollama). No cloud model is used anywhere in Saathi."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any

from . import netguard

DEFAULT_MODEL = "llama3.2:3b"


def host() -> str:
    return os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")


class OllamaClient:
    def __init__(self, base: str | None = None):
        self.base = base or host()
        netguard.allow_local(urllib.parse.urlparse(self.base).hostname or "localhost")

    def chat(self, model: str, messages: list[dict], tools: list[dict]) -> dict[str, Any]:
        body = json.dumps({"model": model, "messages": messages, "tools": tools, "stream": False,
                           "options": {"temperature": 0.2, "num_ctx": 4096}, "keep_alive": "10m"}).encode()
        req = urllib.request.Request(f"{self.base}/api/chat", body, {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:  # noqa: S310 - loopback/local host only
                return json.load(r)["message"]
        except OSError as e:
            raise RuntimeError(f"Cannot reach the local model at {self.base} ({e}). Is Ollama running, "
                               f"and did you `ollama pull {model}`?") from e
