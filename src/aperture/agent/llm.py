"""Local LLM access through Ollama's HTTP API (loopback only).

Only the standard library is used, so there is no extra dependency and the
offline guard sees a plain 127.0.0.1 connection.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Protocol


class LLMError(RuntimeError):
    """The model answered, but not usefully (missing model, bad request...)."""


class LLMUnavailable(LLMError):
    """The model server cannot be reached at all."""


class LLMClient(Protocol):
    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> str:
        """Return the model's raw text, constrained to ``schema`` when supported."""


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: float = 180.0, keep_alive: str = "5m") -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.keep_alive = keep_alive  # 5 min: long enough for a session of questions, short enough to give the 8 GB back

    # ------------------------------------------------------------------
    def _request(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(self.base_url + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            if exc.code == 404:
                raise LLMError(f"Model '{self.model}' is not installed. Run: ollama pull {self.model}") from exc
            raise LLMError(f"Ollama returned HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            raise LLMUnavailable(
                f"Ollama is not reachable at {self.base_url}. Start it with `ollama serve` (or open the Ollama app)."
            ) from exc
        except ValueError as exc:
            raise LLMError("Ollama sent an unreadable response") from exc
        return body if isinstance(body, dict) else {}

    def warm(self) -> None:
        """Load the model into memory now, so the first question does not pay for it."""
        self._request("/api/generate", {"model": self.model, "prompt": "", "keep_alive": self.keep_alive, "stream": False})

    def list_models(self) -> list[str]:
        body = self._request("/api/tags")
        return sorted(str(m.get("name", "")) for m in body.get("models", []) if isinstance(m, dict) and m.get("name"))

    def health(self) -> tuple[bool, str]:
        try:
            models = self.list_models()
        except LLMError as exc:
            return False, str(exc)
        if self.model not in models and f"{self.model}:latest" not in models:
            return False, f"Model '{self.model}' is not installed. Installed: {', '.join(models) or 'none'}"
        return True, f"Ollama OK ({self.model})"

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> str:
        def call(fmt: Any) -> str:
            body = self._request(
                "/api/chat",
                {
                    "model": self.model,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    "stream": False,
                    "format": fmt,
                    "keep_alive": self.keep_alive,
                    "options": {"temperature": 0, "num_ctx": 4096},
                },
            )
            message = body.get("message")
            return str(message.get("content", "")) if isinstance(message, dict) else ""

        try:
            return call(schema)  # structured outputs (Ollama >= 0.5)
        except LLMError as exc:
            if "HTTP 400" in str(exc):  # older server: fall back to plain JSON mode
                return call("json")
            raise


class Vision(Protocol):
    def judge(self, image: bytes, question: str) -> tuple[bool, str]:
        """Look at one image and answer a yes/no question: (answer, short reason)."""


class OllamaVision(OllamaClient):
    """A local vision-language model (e.g. llava) used to *check* what retrieval found."""

    _SCHEMA = {
        "type": "object",
        "properties": {"answer": {"type": "boolean"}, "reason": {"type": "string"}},
        "required": ["answer", "reason"],
    }

    def judge(self, image: bytes, question: str) -> tuple[bool, str]:
        import base64

        body = self._request(
            "/api/chat",
            {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": f"Look at the photo and answer strictly yes or no. Question: {question}",
                        "images": [base64.b64encode(image).decode()],
                    }
                ],
                "stream": False,
                "format": self._SCHEMA,
                "keep_alive": self.keep_alive,
                "options": {"temperature": 0, "num_ctx": 2048},
            },
        )
        message = body.get("message")
        text = str(message.get("content", "")) if isinstance(message, dict) else ""
        try:
            data = json.loads(text)
        except ValueError:
            return False, "unreadable answer"
        return bool(data.get("answer")) is True, str(data.get("reason", ""))[:160]
