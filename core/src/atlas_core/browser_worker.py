"""The browser worker process (see `browser_engine`): reads JSON lines on stdin, drives one isolated Chromium, answers on stdout. It imports nothing of the Core's state and receives no secret."""

from __future__ import annotations

import json
import sys
from typing import Any

from .browser_engine import BrowserBlocked, PlaywrightBrowser


def main() -> int:
    config = json.loads(sys.stdin.readline())
    engine = PlaywrightBrowser(config["hosts"], config["schemes"], config.get("executable"), bool(config.get("no_sandbox")))
    handlers: dict[str, Any] = {
        "ready": lambda: None,
        "open": lambda url: list(engine.open(url)),
        "fill": engine.fill,
        "press": engine.press,
        "close": lambda: None,
    }
    try:
        for line in sys.stdin:
            request = json.loads(line)
            try:
                result = handlers[request["op"]](*request["args"])
                reply: dict[str, Any] = {"id": request["id"], "ok": True, "result": result}
            except BrowserBlocked as blocked:
                reply = {"id": request["id"], "ok": False, "code": blocked.code}
            except Exception:  # noqa: BLE001  (a failure is a code; its text could carry page content)
                reply = {"id": request["id"], "ok": False, "code": "worker_error"}
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()
            if request["op"] == "close":
                break
    finally:
        engine.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
