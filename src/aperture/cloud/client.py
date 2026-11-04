"""The in-app side of the cloud option: redact the question, ask the gateway (loopback), restore the names in the plan.

Everything here is best effort: if the gateway is not running, the cap is reached, the provider is down or the answer is not a usable plan,
it returns None and the local model decides instead. Nothing about the library is ever put in the request: only the redacted question, whether
photos are already on screen, and today's date.
"""

from __future__ import annotations

import json
import re
import urllib.request
from collections.abc import Callable
from datetime import date
from typing import Any

from ..agent.llm import _time_left
from .redact import Redactor

_PLACEHOLDER = re.compile(r"<(?:PERSON|PLACE)_\d+>")


def _drop_unknown_placeholders(value: Any) -> Any:
    """A placeholder the provider invented (one we never sent) must not reach the search."""
    if isinstance(value, str):
        return None if _PLACEHOLDER.search(value) else value
    if isinstance(value, list):
        kept = [v for v in (_drop_unknown_placeholders(x) for x in value) if v is not None]
        return kept or None
    if isinstance(value, dict):
        return {k: v for k, v in ((k, _drop_unknown_placeholders(x)) for k, x in value.items()) if v is not None}
    return value


class CloudInterpreter:
    def __init__(self, port: int, people: Callable[[], list[str]], places: Callable[[], list[str]], opener: Any = urllib.request.urlopen) -> None:
        self._port, self._people, self._places, self._open = port, people, places, opener

    def __call__(self, request: str, has_previous: bool) -> dict[str, Any] | None:
        try:
            redactor = Redactor(self._people(), self._places())
            question = redactor.redact(request)
            body = json.dumps({"question": question, "has_previous": bool(has_previous), "today": date.today().isoformat()}).encode()
            http = urllib.request.Request(f"http://127.0.0.1:{self._port}/interpret", data=body, headers={"Content-Type": "application/json"})
            with self._open(http, timeout=_time_left(12.0)) as response:
                plan = json.loads(response.read().decode("utf-8", "replace")).get("plan")
            if not isinstance(plan, dict) or not plan.get("tool"):
                return None
            arguments = _drop_unknown_placeholders(redactor.restore(plan.get("arguments") or {})) or {}
            return {"name": str(plan["tool"]), "arguments": arguments}
        except Exception:
            return None  # any problem at all: the local model takes over
