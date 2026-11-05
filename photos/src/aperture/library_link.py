"""Photos asks the Documents service to read new pictures; it does not index them itself.

The picture engine now runs in Documents (one indexer for every picture). Photos opens the same index to show it and to answer questions, and presses
Update through here. Without `APERTURE_LIBRARY_URL` (a native install) Photos indexes by itself as before."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

TIMEOUT = 10


def base_url() -> str:
    return os.environ.get("APERTURE_LIBRARY_URL", "").rstrip("/")


def delegated() -> bool:
    return bool(base_url())


def _call(method: str, path: str) -> dict[str, Any]:
    url = base_url() + path
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "http" or not parts.hostname:
        raise RuntimeError("The Documents service address is not valid.")
    request = urllib.request.Request(
        url, method=method, data=b"{}" if method == "POST" else None, headers={"X-Library": "1", "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            data = json.loads(response.read())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise RuntimeError("The Documents service is not running, so new pictures cannot be read yet.") from exc
    return data if isinstance(data, dict) else {}


def request_scan() -> bool:
    """Ask Documents to read what is new (it reads documents, mail and pictures in one go). True if it started."""
    return bool(_call("POST", "/api/scan").get("started"))


def scan_status() -> dict[str, Any]:
    """{running, progress, summary, problems} from Documents, in the shape every module reports it."""
    s = _call("GET", "/api/scan")
    return {
        "running": bool(s.get("running")),
        "progress": str(s.get("progress") or ""),
        "summary": str(s.get("summary") or ""),
        "problems": [str(p) for p in s.get("problems", [])],
        "needs_check": 0,
    }
