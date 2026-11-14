"""What was NOT read, and why. The reader counts the files in the folders at the start of every full read and notes the ones it will not read; this module turns that,
and the files that could not be read, and the documents set aside as not relevant, into plain sentences for the panel and for the assistant."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

REASONS = {
    "only_in_icloud": "is in iCloud but not downloaded to this Mac yet (in Finder: right-click it, then Download Now)",
    "alias_or_link": "is a shortcut or alias, not the file itself",
    "too_large": "is larger than Atlas reads safely (50 MB)",
    "unreadable": "could not be read (damaged, password-protected or too unclear)",
}
EXAMPLES = 10


def _parsed() -> Path:
    return Path(os.environ.get("ATLAS_PARSED", Path.home() / "AtlasParsed"))


def _json(name: str) -> Any:
    try:
        return json.loads((_parsed() / name).read_text())
    except (OSError, ValueError):
        return None


def unread_counts() -> dict[str, int]:
    """How many files were left unread, by reason (what the last full read found, and what failed in the last round)."""
    found = _json(".found") or {}
    counts = {k: int(v) for k, v in ((found.get("unread") or {}).get("counts") or {}).items()}
    failed = _json(".failed.json")
    if isinstance(failed, list) and failed:
        counts["unreadable"] = len(failed)
    return counts


def summary(conn) -> dict[str, Any]:
    found = _json(".found") or {}
    unread = found.get("unread") or {}
    failed = _json(".failed.json")
    failed = failed if isinstance(failed, list) else []
    counts = unread_counts()
    reasons = []
    for key, meaning in REASONS.items():
        if counts.get(key):
            examples = failed[:EXAMPLES] if key == "unreadable" else (unread.get("examples") or {}).get(key, [])[:EXAMPLES]
            reasons.append({"reason": key, "each_file": meaning, "count": counts[key], "examples": examples})
    no_text = [r[0] for r in conn.execute("SELECT name FROM documents WHERE kind='binary' AND text='' LIMIT ?", (EXAMPLES,))]
    no_text_count = conn.execute("SELECT COUNT(*) FROM documents WHERE kind='binary' AND text=''").fetchone()[0]
    set_aside = {area or "inbox": n for area, n in conn.execute("SELECT area, COUNT(*) FROM documents WHERE judged=2 GROUP BY area")}
    return {
        "not_read": sum(counts.values()),
        "reasons": reasons,
        "kept_by_name_only": {
            "count": no_text_count,
            "each_file": "has no readable text (a video, a recording, a program or an unknown format): only its name is kept, so it can be found by name",
            "examples": no_text,
        },
        "model_could_not_understand": {
            "count": conn.execute("SELECT COUNT(*) FROM documents WHERE judged=3").fetchone()[0],
            "each_file": "was read, but the model gave no usable answer about it (twice); it is not marked as anything and is tried again each time you press Read new files",
        },
        "waiting_for_the_model": conn.execute("SELECT COUNT(*) FROM documents WHERE judged=0").fetchone()[0],
        "set_aside_as_not_relevant": set_aside,
        "note": "Set aside means the document was read and stored but not sent to the model, because it did not look relevant (mostly mail such as newsletters). Files in your category folders are always sent to the model.",
        "as_of": "the last full read" if found else "no full read has run yet",
    }
