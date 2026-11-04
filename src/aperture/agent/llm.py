"""Local LLM access through Ollama's HTTP API (loopback only).

Only the standard library is used, so there is no extra dependency and the
offline guard sees a plain 127.0.0.1 connection.
"""

from __future__ import annotations

import json
import logging
import time
from contextvars import ContextVar
import urllib.error
import urllib.request
from typing import Any, Protocol


log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """The model answered, but not usefully (missing model, bad request...)."""


class LLMUnavailable(LLMError):
    """The model server cannot be reached at all."""


class LLMClient(Protocol):
    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> str:
        """Return the model's raw text, constrained to ``schema`` when supported."""


# ONE context size for every request (text, plans, photo description, photo checks). Ollama reloads the model whenever
# num_ctx changes, even for the same model; with a single shared Ministral that would mean a ~3 GB reload on every switch
# between a search and a photo description (slow, and it makes an 8 GB Mac hang). Do not give any call its own value.
NUM_CTX = 4096

# While a request is being answered the web app sets this to an empty list; every model call then records what it was given and
# what it returned. That is the "How I answered" panel: nothing is hidden about what the model saw.
CALL_LOG: ContextVar[list[dict[str, Any]] | None] = ContextVar("aperture_llm_log", default=None)


def _record(model: str, payload: dict[str, Any] | None, output: str, tool_calls: list[dict[str, Any]] | None = None) -> None:
    log = CALL_LOG.get()
    if log is None or not isinstance(payload, dict) or "messages" not in payload:
        return
    messages = payload["messages"]
    system = next((str(m.get("content", "")) for m in messages if m.get("role") == "system"), "")
    log.append({
        "model": model,
        "system": system[:4000],
        "messages": [{"role": m.get("role"), "text": str(m.get("content", ""))[:600]} for m in messages if m.get("role") != "system"][-8:],
        "tools": [t["function"]["name"] for t in payload.get("tools") or []],
        "output": output[:2000],
        "tool_calls": tool_calls or [],
    })


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: float = 180.0, keep_alive: str = "30m") -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.keep_alive = keep_alive  # 30 min: a reload costs seconds on every first question. Indexing pauses while you search and unloads the model when it starts

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
                "The AI engine (Ollama) isn't running. Open the Ollama app, wait a few seconds, and try again."
            ) from exc
        except ValueError as exc:
            raise LLMError("Ollama sent an unreadable response") from exc
        if isinstance(body, dict):
            message = body.get("message")
            _record(self.model, payload, str(message.get("content", "")) if isinstance(message, dict) else "")
        return body if isinstance(body, dict) else {}

    def unload(self) -> None:
        """Free the model's memory now (called before indexing starts, so the two never compete for RAM)."""
        try:
            self._request("/api/generate", {"model": self.model, "prompt": "", "keep_alive": 0, "stream": False})
        except LLMError:
            pass

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

    def complete_json(self, system: str, user: str, schema: dict[str, Any], max_tokens: int | None = None) -> str:
        options: dict[str, Any] = {"temperature": 0, "num_ctx": NUM_CTX}
        if max_tokens:
            options["num_predict"] = max_tokens

        def call(fmt: Any) -> str:
            body = self._request(
                "/api/chat",
                {
                    "model": self.model,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    "stream": False,
                    "format": fmt,
                    "keep_alive": self.keep_alive,
                    "options": options,
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

    def complete_chat(self, system: str, messages: list[dict[str, str]], max_tokens: int = 400) -> str:
        """A normal multi-turn conversational reply (free text, no JSON, no photos)."""
        body = self._request(
            "/api/chat",
            {
                "model": self.model,
                "messages": [{"role": "system", "content": system}, *messages],
                "stream": False,
                "keep_alive": self.keep_alive,
                "options": {"temperature": 0.3, "num_ctx": NUM_CTX, "num_predict": max_tokens},
            },
        )
        message = body.get("message")
        return str(message.get("content", "")).strip() if isinstance(message, dict) else ""

    def _stream_chunks(self, payload: dict[str, Any], timeout: float | None = None):
        """POST a streaming chat request and yield each parsed chunk as the model produces it."""
        request = urllib.request.Request(
            self.base_url + "/api/chat", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
        )
        parts: list[str] = []
        calls: list[dict[str, Any]] = []
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                for raw in response:
                    line = raw.strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except ValueError as exc:
                        raise LLMError("Ollama sent an unreadable response") from exc
                    if isinstance(chunk, dict):
                        message = chunk.get("message")
                        if isinstance(message, dict):
                            parts.append(str(message.get("content") or ""))
                            for call in message.get("tool_calls") or []:
                                function = call.get("function") if isinstance(call, dict) else None
                                if isinstance(function, dict):
                                    calls.append({"name": function.get("name"), "arguments": function.get("arguments")})
                        yield chunk
                        if chunk.get("done"):
                            self._log_timing(chunk)
                            return
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise LLMError(f"Model '{self.model}' is not installed. Run: ollama pull {self.model}") from exc
            detail = exc.read().decode("utf-8", "replace")[:200].replace("\n", " ")  # Ollama says why (out of memory, runner stopped ...)
            raise LLMError(f"Ollama returned HTTP {exc.code}" + (f": {detail}" if detail else "")) from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            raise LLMUnavailable(
                "The AI engine (Ollama) isn't running. Open the Ollama app, wait a few seconds, and try again."
            ) from exc
        finally:
            _record(self.model, payload, "".join(parts), calls)

    def _chat_payload(self, system: str, messages: list[dict[str, str]], max_tokens: int, tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "stream": True,
            "keep_alive": self.keep_alive,
            "options": {"temperature": 0.3, "num_ctx": NUM_CTX, "num_predict": max_tokens},
        }
        if tools:
            payload["tools"] = tools
        return payload

    def stream_chat(self, system: str, messages: list[dict[str, str]], max_tokens: int = 400):
        """Yield the reply piece by piece as the model writes it, so the first words show up in about a second."""
        for chunk in self._stream_chunks(self._chat_payload(system, messages, max_tokens)):
            message = chunk.get("message")
            text = str(message.get("content", "")) if isinstance(message, dict) else ""
            if text:
                yield text

    @staticmethod
    def _log_timing(chunk: dict[str, Any]) -> None:
        """Where the model's time went (Ollama reports it): loading the model, reading the prompt, writing the answer."""
        def seconds(key: str) -> float:
            return float(chunk.get(key) or 0) / 1e9

        log.info("model timing: load %.1fs, read prompt %d tokens in %.1fs, wrote %d tokens in %.1fs",
                 seconds("load_duration"), int(chunk.get("prompt_eval_count") or 0), seconds("prompt_eval_duration"),
                 int(chunk.get("eval_count") or 0), seconds("eval_duration"))

    def _chunks_with_retry(self, payload: dict[str, Any], timeout: float | None = None):
        """A server error before the first word (the model runner restarting, memory pressure) is retried once after a short pause."""
        for attempt in (1, 2):
            started = False
            try:
                for chunk in self._stream_chunks(payload, timeout):
                    started = True
                    yield chunk
                return
            except LLMError as exc:
                if attempt == 2 or started or "HTTP 5" not in str(exc):
                    raise
                time.sleep(2.0)

    def chat_events(self, system: str, messages: list[dict[str, str]], tools: list[dict[str, Any]], max_tokens: int = 400,
                    timeout: float | None = None):
        """One streaming call where the model chooses: yield ("delta", text) while it talks, or ("tool", {name, arguments}) when it
        decides to use one of the tools. This is the heart of an agent: the model decides, our code only carries it out."""
        for chunk in self._chunks_with_retry(self._chat_payload(system, messages, max_tokens, tools), timeout):
            message = chunk.get("message")
            if not isinstance(message, dict):
                continue
            for call in message.get("tool_calls") or []:
                function = call.get("function") if isinstance(call, dict) else None
                function = function if isinstance(function, dict) else {}
                arguments = function.get("arguments")
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except ValueError:
                        arguments = {}
                yield "tool", {"name": str(function.get("name", "")), "arguments": arguments if isinstance(arguments, dict) else {}}
            text = str(message.get("content") or "")
            if text:
                yield "delta", text

    def complete_text(self, system: str, user: str) -> str:
        """Plain-text answer (no JSON), for conversational replies grounded in supplied facts."""
        body = self._request(
            "/api/chat",
            {
                "model": self.model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "stream": False,
                "keep_alive": self.keep_alive,
                "options": {"temperature": 0.2, "num_ctx": NUM_CTX, "num_predict": 300},
            },
        )
        message = body.get("message")
        return str(message.get("content", "")) if isinstance(message, dict) else ""


class Vision(Protocol):
    def extract(self, image: bytes, prompt: str, schema: dict[str, Any], max_tokens: int = 700) -> str:
        """Ask the vision model about one picture and get an answer that follows `schema` (JSON)."""
        import base64

        body = self._request(
            "/api/chat",
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt, "images": [base64.b64encode(image).decode()]}],
                "stream": False,
                "format": schema,
                "keep_alive": self.keep_alive,
                "options": {"temperature": 0.1, "num_ctx": NUM_CTX, "num_predict": max_tokens},
            },
        )
        message = body.get("message")
        return str(message.get("content", "")) if isinstance(message, dict) else ""

    def judge(self, image: bytes, question: str) -> tuple[bool, str]:
        """Look at one image and answer a yes/no question: (answer, short reason)."""


class Describer(Protocol):
    def describe(self, image: bytes, question: str = "") -> str:
        """Look at one image and answer in plain text: a description, or the answer to ``question``."""


class OllamaVision(OllamaClient):
    """A local vision-language model (e.g. llava) used to *check* what retrieval found."""

    _SCHEMA = {
        "type": "object",
        "properties": {"answer": {"type": "boolean"}, "reason": {"type": "string"}},
        "required": ["answer", "reason"],
    }

    def describe(self, image: bytes, question: str = "") -> str:
        import base64

        prompt = question.strip() or (
            "Describe this photo in two or three short sentences: the main subjects, the setting and anything unusual. "
            "Do not guess names of people."
        )
        body = self._request(
            "/api/chat",
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt, "images": [base64.b64encode(image).decode()]}],
                "stream": False,
                "keep_alive": self.keep_alive,
                "options": {"temperature": 0.2, "num_ctx": NUM_CTX, "num_predict": 200},
            },
        )
        message = body.get("message")
        return str(message.get("content", "")).strip() if isinstance(message, dict) else ""

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
                "options": {"temperature": 0, "num_ctx": NUM_CTX},
            },
        )
        message = body.get("message")
        text = str(message.get("content", "")) if isinstance(message, dict) else ""
        try:
            data = json.loads(text)
        except ValueError:
            return False, "unreadable answer"
        return bool(data.get("answer")) is True, str(data.get("reason", ""))[:160]
