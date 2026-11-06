"""Running one tool for the one assistant: the arguments are coerced to the declared types (small models send numbers as strings), a failure comes back
as data the model can read, and the tools no AI may run are named here."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .modules import ALL
from .modules import tools as registry

NEVER_BY_AI = frozenset({"delete_transaction"})  # your imported payments are the record: no assistant may delete one, whatever it is told


def _coerce(tool, args: dict[str, Any]) -> dict[str, Any]:
    """Small local models often send numbers as strings; fix by the declared type."""
    out = dict(args)
    for k, v in args.items():
        t = tool.properties.get(k, {}).get("type")
        try:
            if t == "integer" and isinstance(v, (str, float)):
                out[k] = int(float(v))
            elif t == "number" and isinstance(v, str):
                out[k] = float(v.replace(",", ""))
        except ValueError:
            pass
    return out


def run_tool(conn: sqlite3.Connection, name: str, args: dict[str, Any] | str, allowed: frozenset[str] | None = None) -> tuple[str, bool]:
    tool = registry(ALL).get(name)
    if tool is None or (allowed is not None and name not in allowed):
        return json.dumps({"error": f"tool {name!r} is not available"}), True
    try:
        parsed: dict[str, Any] = json.loads(args or "{}") if isinstance(args, str) else args
        return json.dumps(tool.fn(conn, _coerce(tool, parsed)), default=str), False
    except Exception as e:  # noqa: BLE001 - any tool failure is reported to the model so it can correct itself
        conn.rollback()
        return json.dumps({"error": f"{type(e).__name__}: {e}"}), True
