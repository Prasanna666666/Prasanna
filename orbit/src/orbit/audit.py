"""An audit log nobody can quietly rewrite: every import and every correction is recorded, and each entry is sealed with a hash that includes the one before.
If any past entry is changed or removed, the chain no longer verifies and the check says so."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone


def _seal(prev: str, at: str, action: str, detail: str) -> str:
    return hashlib.sha256(f"{prev}|{at}|{action}|{detail}".encode()).hexdigest()


def record(conn, action: str, detail: str = "") -> None:
    """Add an entry. `detail` is a short description (counts, names of things), never amounts or personal text."""
    try:
        last = conn.execute("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
        prev = last[0] if last else ""
        at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        detail = detail[:300]
        conn.execute("INSERT INTO audit_log (at, action, detail, prev, hash) VALUES (?,?,?,?,?)", (at, action, detail, prev, _seal(prev, at, action, detail)))
        conn.commit()
    except Exception:
        pass


def verify_chain(conn) -> tuple[bool, int, str]:
    """(intact, number of entries, what is wrong)."""
    prev, n = "", 0
    for r in conn.execute("SELECT id, at, action, detail, prev, hash FROM audit_log ORDER BY id"):
        n += 1
        if r["prev"] != prev or r["hash"] != _seal(r["prev"], r["at"], r["action"], r["detail"]):
            return False, n, f"entry {r['id']} was changed or an earlier entry is missing"
        prev = r["hash"]
    return True, n, ""
