"""The gateway: the only program that talks to the cloud provider, and the only thing the provider ever hears from.

It receives ONE short, already-redacted question over loopback, asks the provider to turn it into a search plan, checks the plan strictly and
returns it. It never opens your photos, your database or your faces (it is not given them), it holds the API key (from the Keychain, passed in
by the launcher), it keeps a monthly spending cap, and it can only reach the provider's host.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.request
from datetime import date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

log = logging.getLogger("aperture.cloud")

PROVIDER_URL = "https://api.anthropic.com/v1/messages"
PROVIDER_HOST = "api.anthropic.com"
DEFAULT_MODEL = "claude-haiku-5-5"
DEFAULT_PRICES = (1.0, 5.0)  # USD per million tokens in / out: a placeholder, set the real figures in your settings
MAX_QUESTION = 400
TOOLS = ("find_photos", "count_photos", "copy_photos", "show_results", "library_overview")
ARGUMENTS = {
    "what": "str", "people": "list", "places": "list", "text_in_photo": "list", "not_what": "list", "not_people": "list", "not_places": "list",
    "year": "int", "month": "int", "season": "str", "relative": "str", "date_from": "date", "date_to": "date", "min_people": "int",
    "max_people": "int", "time_of_day": "str", "day_type": "str", "orientation": "str", "color": "str", "narrow_previous": "bool", "folder": "str", "looks_like": "list",
}
SYSTEM = (
    "You turn a person's request about their photo library into ONE search call. You never see the photos. Reply with ONLY a JSON object: "
    '{"tool": <name>, "arguments": {...}}.\n'
    "Tools: find_photos (show photos), count_photos (how many), copy_photos (copy into a folder; needs folder), show_results (show the photos "
    "already on screen again), library_overview (general facts about the library).\n"
    "Arguments for find_photos, count_photos and copy_photos: use ONLY what the request says and leave everything else out. what = what the picture "
    "shows, a short singular noun phrase; people[]; places[] (cities, countries or folders); text_in_photo[]; year; month (1-12); season "
    "(spring|summer|autumn|winter); relative (today|yesterday|this_week|last_week|this_month|last_month|this_year|last_year); date_from and "
    "date_to (YYYY-MM-DD); not_what[]; not_people[]; not_places[]; min_people; max_people; time_of_day; day_type; orientation; color; "
    "narrow_previous (true only when the request refers to the photos already on screen); looks_like[] = when 'what' is an activity, event or "
    "place type, up to 4 short, concrete descriptions of how it would look in a photo, in plain visual words (for 'hockey game': 'ice hockey players on "
    "a rink', 'a crowd in an arena watching a game', 'players with sticks on a pitch'). Only describe what the request itself asks for.\n"
    "Several places mean ANY of them. Words like <PERSON_1> and <PLACE_1> stand for real names: copy them exactly into people or places. "
    "'The last 3 months' means from 3 months before today until today; '2 months back' means that one month. "
    "A request that is only conversation, or that you cannot turn into a search, is {\"tool\": \"none\"}."
)


CHAT_SYSTEM = (
    "You are Lumo, a warm, quick-witted assistant inside a private photo app on the person's Mac. You cannot see their photos and you are not searching "
    "anything in this reply, so never claim to have found or looked at any. Chat naturally in one to three short sentences of plain text, no lists or "
    "emojis. For small talk, be genuinely friendly and curious; for general questions, answer correctly and briefly; and when it fits, invite them to "
    "describe photos they would like to find. Words like <PERSON_1> and <PLACE_1> stand for real names: you may use them as written."
)
MAX_TURNS = 4


class GatewayError(RuntimeError):
    pass


def _month_key(today: date | None = None) -> str:
    return (today or date.today()).strftime("%Y-%m")


class Usage:
    """Tokens and estimated spend this month, kept in a small file outside the library."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            data = {}
        if data.get("month") != _month_key():
            data = {"month": _month_key(), "tokens_in": 0, "tokens_out": 0, "spent_usd": 0.0}
        return data

    def spent(self) -> float:
        with self._lock:
            return float(self._load()["spent_usd"])

    def add(self, tokens_in: int, tokens_out: int, prices: tuple[float, float]) -> float:
        with self._lock:
            data = self._load()
            data["tokens_in"] += tokens_in
            data["tokens_out"] += tokens_out
            data["spent_usd"] = round(data["spent_usd"] + tokens_in * prices[0] / 1e6 + tokens_out * prices[1] / 1e6, 6)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data))
            try:
                self.path.chmod(0o600)
            except OSError:
                pass
            return float(data["spent_usd"])


def _clean_value(kind: str, value: Any) -> Any:
    """One argument, checked strictly: anything odd is dropped, never passed on."""
    if kind == "str" and isinstance(value, str) and value.strip():
        return value.strip()[:120]
    if kind == "list" and isinstance(value, list):
        items = [v.strip()[:120] for v in value if isinstance(v, str) and v.strip()][:8]
        return items or None
    if kind == "int" and isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 3000:
        return value
    if kind == "bool" and value is True:
        return True
    if kind == "date" and isinstance(value, str):
        try:
            datetime.strptime(value[:10], "%Y-%m-%d")
            return value[:10]
        except ValueError:
            return None
    return None


def clean_plan(data: Any) -> dict[str, Any] | None:
    """The provider's answer as a safe search plan, or None when it is not one."""
    if not isinstance(data, dict):
        return None
    tool = str(data.get("tool") or "")
    if tool not in TOOLS:
        return None
    arguments = data.get("arguments") if isinstance(data.get("arguments"), dict) else {}
    clean = {}
    for key, kind in ARGUMENTS.items():
        value = _clean_value(kind, arguments.get(key))
        if value is not None and not (key == "folder" and tool != "copy_photos"):
            clean[key] = value
    return {"tool": tool, "arguments": clean}


class Gateway:
    def __init__(self, key: str, usage: Usage, model: str = DEFAULT_MODEL, cap_usd: float = 5.0, prices: tuple[float, float] = DEFAULT_PRICES,
                 provider_url: str = PROVIDER_URL, opener: Any = urllib.request.urlopen) -> None:
        self._key, self._usage, self.model, self.cap_usd, self.prices = key, usage, model, cap_usd, prices
        self._url, self._open = provider_url, opener

    def status(self) -> dict[str, Any]:
        return {"model": self.model, "spent_usd": round(self._usage.spent(), 4), "cap_usd": self.cap_usd, "month": _month_key()}

    def _call(self, system: str, content: str, max_tokens: int) -> str:
        """One request to the provider; spending is counted and refused over the cap. Returns the provider's text."""
        if self._usage.spent() >= self.cap_usd:
            raise GatewayError(f"the monthly cap of ${self.cap_usd:.2f} is reached")
        body = json.dumps({"model": self.model, "max_tokens": max_tokens, "temperature": 0.6 if system is CHAT_SYSTEM else 0, "system": system,
                           "messages": [{"role": "user", "content": content}]}).encode()
        request = urllib.request.Request(self._url, data=body, headers={"content-type": "application/json", "x-api-key": self._key,
                                                                          "anthropic-version": "2023-06-01"})
        try:
            with self._open(request, timeout=20) as response:
                reply = json.loads(response.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            hints = {400: "the request was refused (check the model name)", 401: "the API key was refused (check the key)", 403: "the API key is not allowed to use this model",
                     404: "the model name was not found (set a valid one with cloud_model)", 429: "rate limit or no credit left at the provider"}
            raise GatewayError(f"the provider answered HTTP {exc.code}: {hints.get(exc.code, 'see the provider dashboard')}") from exc
        except Exception as exc:
            raise GatewayError(f"the provider could not be reached: {type(exc).__name__}") from exc
        usage = reply.get("usage") or {}
        self._usage.add(int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0), self.prices)
        return "".join(block.get("text", "") for block in reply.get("content", []) if isinstance(block, dict))

    def chat(self, question: str, earlier: list[str], today: str) -> str:
        """A conversational reply to the (already redacted) message. Only the person's own recent words are sent, never results or library facts."""
        question = " ".join(str(question).split())[:MAX_QUESTION]
        if not question:
            raise GatewayError("empty question")
        recent = [" ".join(str(e).split())[:MAX_QUESTION] for e in earlier[-MAX_TURNS:] if str(e).strip()]
        content = json.dumps({"today": today, "their_earlier_messages": recent, "their_message": question})
        return self._call(CHAT_SYSTEM, content, 250).strip()

    def interpret(self, question: str, has_previous: bool, today: str) -> dict[str, Any] | None:
        question = " ".join(str(question).split())[:MAX_QUESTION]
        if not question:
            raise GatewayError("empty question")
        if self._usage.spent() >= self.cap_usd:
            raise GatewayError(f"the monthly cap of ${self.cap_usd:.2f} is reached")
        body = json.dumps({
            "model": self.model, "max_tokens": 400, "temperature": 0, "system": SYSTEM,
            "messages": [{"role": "user", "content": json.dumps({"today": today, "photos_already_on_screen": bool(has_previous), "request": question})}],
        }).encode()
        request = urllib.request.Request(self._url, data=body, headers={"content-type": "application/json", "x-api-key": self._key,
                                                                          "anthropic-version": "2023-06-01"})
        try:
            with self._open(request, timeout=20) as response:
                reply = json.loads(response.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            hints = {400: "the request was refused (check the model name)", 401: "the API key was refused (check the key)", 403: "the API key is not allowed to use this model",
                     404: "the model name was not found (set a valid one with cloud_model)", 429: "rate limit or no credit left at the provider"}
            raise GatewayError(f"the provider answered HTTP {exc.code}: {hints.get(exc.code, 'see the provider dashboard')}") from exc  # no body, no key
        except Exception as exc:
            raise GatewayError(f"the provider could not be reached: {type(exc).__name__}") from exc  # never echo anything that could hold the key
        usage = reply.get("usage") or {}
        self._usage.add(int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0), self.prices)
        text = "".join(block.get("text", "") for block in reply.get("content", []) if isinstance(block, dict))
        try:
            from ..agent.jsonutil import extract_json

            return clean_plan(extract_json(text))
        except Exception:
            return None


def make_handler(gateway: Gateway, port: int) -> type[BaseHTTPRequestHandler]:
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:  # the question must not end up in a log line
            pass

        def _json(self, obj: Any, status: int = 200) -> None:
            body = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.headers.get("Host", "") not in hosts:
                return self._json({"error": "unknown host"}, int(HTTPStatus.FORBIDDEN))
            self._json(gateway.status() if self.path == "/status" else {"ok": True})

        def do_POST(self) -> None:  # noqa: N802
            if self.headers.get("Host", "") not in hosts or self.path not in ("/interpret", "/chat"):
                return self._json({"error": "not found"}, int(HTTPStatus.NOT_FOUND))
            if self.path == "/chat":
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    return self._chat(json.loads(self.rfile.read(min(size, 4096))))
                except (ValueError, TypeError):
                    return self._json({"error": "bad request"}, int(HTTPStatus.BAD_REQUEST))
            try:
                size = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(min(size, 4096)))
                plan = gateway.interpret(str(body.get("question", "")), bool(body.get("has_previous")), str(body.get("today") or date.today().isoformat()))
            except GatewayError as exc:
                return self._json({"error": str(exc)}, int(HTTPStatus.SERVICE_UNAVAILABLE))
            except (ValueError, TypeError):
                return self._json({"error": "bad request"}, int(HTTPStatus.BAD_REQUEST))
            self._json({"plan": plan})

        def _chat(self, body: dict[str, Any]) -> None:
            try:
                reply = gateway.chat(str(body.get("question", "")), [str(x) for x in (body.get("earlier") or [])][:MAX_TURNS],
                                     str(body.get("today") or date.today().isoformat()))
            except GatewayError as exc:
                return self._json({"error": str(exc)}, int(HTTPStatus.SERVICE_UNAVAILABLE))
            self._json({"reply": reply})

    return Handler


def serve(gateway: Gateway, port: int) -> int:
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(gateway, port))
    log.info("cloud gateway on 127.0.0.1:%d (model %s, cap $%.2f)", port, gateway.model, gateway.cap_usd)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
