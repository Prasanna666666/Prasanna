"""Finance takes its documents from the Documents service; it does not read files itself.

The Documents service (the library project) reads every file and mail once, says what each is and verifies the amounts and dates. Finance asks it for the
kinds of documents that matter here (invoices, receipts, payslips, statements, tax and insurance papers, contracts, tickets and bookings, and everything
from the finance folder) and keeps its own copy of just those, because Finance's reports and checks work on them. Nothing else is copied: a medical
report stays in the Documents service for the apps that need it.
"""

from __future__ import annotations

import os
import time
import urllib.parse
from collections.abc import Callable
from typing import Any

from kit.http import call_local

from . import db
from .modules import documents

FINANCE_KINDS = ("bank_statement", "payslip", "annual_statement", "invoice", "receipt", "tax", "insurance", "contract", "ticket", "booking")
PAGE = 25
POLL_SECONDS = 2
Fetch = Callable[[str, str], dict[str, Any]]  # (method, path) -> JSON


def base_url() -> str:
    return os.environ.get("LIBRARY_URL", "").rstrip("/")


def _http(method: str, path: str) -> dict[str, Any]:
    return call_local(
        base_url(),
        method,
        path,
        "X-Library",
        "The Documents service is not running, so new files and mail cannot be read yet. Start it and press Read new files again.",
    )


def update(progress: Callable[[str], None] | None = None, fetch: Fetch = _http) -> list[str]:
    """Ask the Documents service to read everything new and wait until it has. Returns the problems it reported."""
    fetch("POST", "/api/scan")
    while True:
        status = fetch("GET", "/api/scan")
        if progress and status.get("progress"):
            progress(str(status["progress"]))
        if not status.get("running"):
            return [str(p) for p in status.get("problems", [])]
        time.sleep(POLL_SECONDS)


def pull(conn, fetch: Fetch = _http) -> dict[str, int]:
    """Take what is new and relevant from the Documents service into Finance's own database."""
    cursor = int(db.get_setting(conn, "library_cursor", "0") or 0)
    kinds = urllib.parse.quote(",".join(FINANCE_KINDS))
    new = known = 0
    while True:
        page = fetch("GET", f"/api/documents?kind={kinds}&area=finance&since={cursor}&limit={PAGE}&full=1&understood=1")["documents"]
        if not page:
            break
        for doc in page:
            added = documents.store_from_library(conn, doc)
            new += added
            known += 1 - added
            cursor = max(cursor, int(doc["ready"]))
        db.set_setting(conn, "library_cursor", str(cursor))
    return {"new": new, "known": known}
