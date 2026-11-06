"""Documents parsed by the isolated parser (PDF, CSV, text). READ-ONLY for the assistant: it can search and read,
never create, change or delete. Text inside documents is untrusted data and is never treated as instructions."""

from __future__ import annotations

import json
import re

from kit.module import Module

from ..tagging import rule_tags

MIGRATIONS = (
    """
    CREATE TABLE documents (
        id INTEGER PRIMARY KEY,
        sha256 TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        kind TEXT NOT NULL,
        text TEXT NOT NULL,
        tags TEXT NOT NULL DEFAULT '',
        parsed_at TEXT,
        created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    ALTER TABLE documents ADD COLUMN area TEXT NOT NULL DEFAULT '';   -- 'finance' for files from the finance folder
    ALTER TABLE documents ADD COLUMN data TEXT NOT NULL DEFAULT '';   -- structured rows (CSV) or reconstructed lines (PDF), as JSON
    """,
    """
    ALTER TABLE documents ADD COLUMN facts TEXT NOT NULL DEFAULT '';  -- what the Documents service said this is (kind, who, when, how much), already verified, as JSON
    """,
)
KINDS = {"text", "csv", "pdf", "image", "sheet", "doc", "html", "email", "json"}
MAX_JSON = 30_000_000
_SHA = re.compile(r"^[0-9a-f]{64}$")


def store_from_library(conn, doc: dict) -> int:
    """Keep one document the Documents service handed over (1 if it is new). The service has already read and checked it; here it is only validated and stored."""
    if not (
        isinstance(doc.get("sha256"), str)
        and _SHA.match(doc["sha256"])
        and isinstance(doc.get("name"), str)
        and 0 < len(doc["name"]) <= 255
        and doc.get("file_kind") in KINDS
        and isinstance(doc.get("text"), str)
        and isinstance(doc.get("facts"), dict)
    ):
        return 0
    people = [dict(r) for r in conn.execute("SELECT name FROM people")]
    tags = ",".join(rule_tags(f"{doc['name']} {doc['text'][:5000]}", people))
    area = doc["area"] if doc.get("area") in ("finance", "mail") else ""
    cur = conn.execute(
        "INSERT OR IGNORE INTO documents (sha256, name, kind, text, tags, area, data, facts) VALUES (?,?,?,?,?,?,?,?)",
        (doc["sha256"], doc["name"], doc["file_kind"], doc["text"], tags, area, str(doc.get("data") or ""), json.dumps(doc["facts"]) if doc["facts"] else ""),
    )
    conn.commit()
    return cur.rowcount


MODULE = Module("documents", MIGRATIONS)  # the documents the Documents part handed over; searching them is that part's tool
