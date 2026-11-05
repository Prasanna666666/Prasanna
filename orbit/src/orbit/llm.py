"""Local model access (Ollama). No cloud model is used anywhere in Orbit."""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import time
import urllib.parse
import urllib.request
from typing import Any

from . import netguard

# The ONLY model Orbit uses (disk space is limited: one model, no fallbacks). The exact tag could not be verified from
# the build sandbox; resolve() also accepts a single installed model whose name starts with "ministral".
DEFAULT_MODEL = "ministral-3:3b"


def is_local_host(name: str) -> bool:
    """True only for this computer or its private network: loopback, a private IP, localhost, or a docker-style `.internal` / `ollama` name.
    The model server is never allowed to be anywhere else, so what you type can never be sent over the internet."""
    name = (name or "").strip().lower().strip("[]")
    try:
        ip = ipaddress.ip_address(name)
        return ip.is_loopback or ip.is_private
    except ValueError:
        return name in {"localhost", "ollama", "host.docker.internal"} or name.endswith(".internal")


def host() -> str:
    return os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")


KEEP = "2m"  # the same value Aperture sends, so one loaded model is shared on an 8 GB Mac


class Slow(RuntimeError):
    """The model did not answer within the time allowed for this reply."""


class OllamaClient:
    deadline: float | None = None  # a time.monotonic() moment; calls made after it fail at once, and no call may run past it

    def __init__(self, base: str | None = None):
        self.base = base or host()
        name = urllib.parse.urlparse(self.base).hostname or ""
        if urllib.parse.urlparse(self.base).scheme not in ("http", "https") or not is_local_host(name):
            raise ValueError(f"The model server must be on this computer or its private network, not {name or self.base!r}")
        netguard.allow_local(urllib.parse.urlparse(self.base).hostname or "localhost")

    def _call(self, path: str, body: dict | None = None, timeout: int = 300) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{self.base}{path}", data, {"Content-Type": "application/json"})
        if self.deadline is not None:
            left = self.deadline - time.monotonic()
            if left <= 0.5:
                raise Slow("out of time")
            timeout = min(timeout, left)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except OSError as e:
            if self.deadline is not None and isinstance(e, TimeoutError | socket.timeout) or "timed out" in str(e):
                raise Slow("out of time") from e
            raise RuntimeError(f"Cannot reach the local model server at {self.base} ({e}). Is Ollama running?") from e

    def installed(self) -> list[str]:
        return [m["name"] for m in self._call("/api/tags", timeout=10).get("models", [])]

    def resolve(self, preferred: str) -> str:
        """The configured model if installed; else the one installed Ministral model; else a helpful error."""
        names = self.installed()
        have = set(names) | {n.removesuffix(":latest") for n in names}
        if preferred in have:
            return preferred
        same_family = [n for n in names if n.lower().startswith(preferred.split(":")[0].split("-")[0].lower())]
        if len(same_family) == 1:
            return same_family[0]
        if same_family:
            raise RuntimeError(f"Several {preferred.split(':')[0]} models are installed ({', '.join(same_family)}): "
                               "pick one in Settings.")
        raise RuntimeError(f"Model {preferred!r} is not installed (installed: {', '.join(names) or 'none'}). "
                           f"Run:  ollama pull {preferred}")

    def warm(self, model: str) -> None:
        """Load the model into memory now (so the first message does not wait for it). Failures are ignored: it is only a head start."""
        try:
            self._call("/api/generate", {"model": model, "prompt": "", "stream": False, "keep_alive": KEEP,
                                         "options": {"num_ctx": 4096}}, timeout=120)
        except RuntimeError:
            pass

    def chat(self, model: str, messages: list[dict], tools: list[dict] | None = None, schema: dict | None = None,
             num_ctx: int = 4096) -> dict[str, Any]:
        """`schema` forces the answer to be JSON of that shape (Ollama's constrained output)."""
        body: dict[str, Any] = {"model": model, "messages": messages, "stream": False, "keep_alive": KEEP,
                                "options": {"temperature": 0.0 if schema else 0.2, "num_ctx": num_ctx, "num_predict": 600 if schema else 350}}
        if schema:
            body["format"] = schema
        if tools:
            body["tools"] = tools
        return self._call("/api/chat", body)["message"]
