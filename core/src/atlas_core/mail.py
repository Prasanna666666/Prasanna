"""The Core-owned Mail source (WP3.3), READ-ONLY and BODY-ONLY, behind the platform seam `Mailbox`.

    Mailbox adapter (Apple Mail later; `InMemoryMailbox` synthetic fixtures now) --guard--> parse (strict, bounded) --> MailIndex (own encrypted SQLite) --> Retriever / SourceStore

* **Nothing is read unless the owner grant AND the platform permission are current.** The adapter is wrapped so that EVERY call (listing, reading) first runs the access guard; the
  index cannot be built without one. Policy is unchanged: this module only produces and keeps material for the existing gate (`GatedRetrieval`, `ContextBuilder`, `GatedModel`).
* **Stored fields are trusted fields; message text is not.** Sender, date and subject are the STORED fields of the message record, rendered by the Core as the `headers` part. The body
  is a separate `body` part, so text inside a body that looks like "From: ..." can never be cited as the sender: a sender/date citation resolves only into the headers part.
* **Exact evidence.** One passage = one stored header line (locator `message_part: headers`) or one paragraph of the body (locator `message_part: body`), each with its exact span and
  the hash of the whole stored text as the version. A message that changed or disappeared is unresolvable (re-read and re-hashed on every resolution).
* **Attachments do not exist here.** Only five fields are ever taken from the adapter (id, sender, date, subject, body); anything else it returns is ignored and never stored, listed,
  counted or exposed. Attachment content is the separate G-O18 package; the answer discloses `attachments_not_searched` through the existing rule.
* **Hostile content is data.** A body can say anything; it widens no scope, changes no grant and triggers nothing (there is no action path here at all).
"""

from __future__ import annotations

import hashlib
import heapq
import json
import re
import threading
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from kit.db import connect

from .access import AccessCheck
from .documents import FETCH_CHUNK, IndexStore, paragraph_blocks, terms
from .evidence import StoredSource, sha256_text
from .policy import PermissionRevoked
from .rules import Rules, load_rules

MAX_BODY_CHARS = 1_000_000  # a larger body is 'oversized': reported, never truncated
MAX_FIELD_CHARS = 500
MAX_MESSAGES = 50_000  # at most this many messages are ever admitted to one scan: the NEWEST ones; a larger mailbox says so and coverage is never complete
MAX_MALFORMED_ROWS = (
    1_000  # at most this many malformed listing entries are recorded (as identity-free failed rows); the rest only keep the scan from being complete
)
PAGE_SIZE = 500  # the most the Core asks for, and accepts, in one adapter call: nothing unbounded is ever materialised
MAX_LIST_WORK = 200_000  # the most listing entries examined in one scan, whatever the adapter does
SCHEMA_VERSION = 2  # 2: the postings table (term -> message)
_ID = re.compile(r"[A-Za-z0-9._@<>+=-]{1,200}\Z")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class MailError(Exception):
    """A message that cannot be taken in full. `reason` is a code (never content): malformed_message, oversized, corrupt or unreadable."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Listed:
    """What listing a mailbox returns: an identity, an adapter-supplied change marker (NOT trusted for correctness: every read is re-hashed) and the stored date for ordering."""

    message_id: str
    version: str
    date: str | None


@dataclass(frozen=True)
class ListPage:
    items: list[Listed]
    next_cursor: str | None  # None: this was the last page


class Mailbox(Protocol):
    """The platform seam. The real Apple Mail adapter (not built, never pointed at a real mailbox in this stage) returns ONLY these fields; the Core ignores any other key.

    Listing is PAGED and BOUNDED: `list_page(cursor, limit)` returns at most `limit` entries and a cursor for the next page. Newest-first is a hope, never a guarantee, and the Core
    never relies on it: it examines up to a fixed amount of work (MAX_LIST_WORK entries) whatever the order, keeps the newest of what it saw, and reports the scan incomplete when
    the mailbox was not fully seen. An adapter that DOES list newest first therefore gets the newest messages admitted, and one that does not still gets the newest of its window."""

    def list_page(self, cursor: str | None, limit: int) -> ListPage: ...

    def read(self, message_id: str) -> dict[str, Any] | None: ...


class InMemoryMailbox:
    """SYNTHETIC fixtures only. `attachment_reads` counts any access to the attachments a fixture may carry: the Core must leave it at zero. `order` is how listing orders the
    messages: "newest_first" (the contract), "by_id" or "as_given" (deliberately NOT date-ordered, to prove the Core does not rely on it)."""

    def __init__(self, messages: Iterable[dict[str, Any]] = (), order: str = "newest_first") -> None:
        self.messages = {m["message_id"]: dict(m) for m in messages}
        self.order = order
        self.lists = 0  # list_page calls
        self.listed = 0  # entries handed out
        self.max_page = 0  # the largest page handed out
        self.reads = 0
        self.attachment_reads = 0
        self.overshoot = 0  # a misbehaving adapter returns this many more than asked

    def _sequence(self) -> list[str]:
        ids = list(self.messages)
        if self.order == "by_id":
            return sorted(ids)
        if self.order == "as_given":
            return ids
        return sorted(ids, key=lambda i: (_epoch_or_floor(self.messages[i].get("date")), i), reverse=True)

    def list_page(self, cursor: str | None, limit: int) -> ListPage:
        self.lists += 1
        start = int(cursor or 0)
        ids = self._sequence()
        take = ids[start : start + limit + self.overshoot]
        self.listed += len(take)
        self.max_page = max(self.max_page, len(take))
        items = [Listed(i, hashlib.sha256(json.dumps(self._stored(i), sort_keys=True).encode()).hexdigest(), self.messages[i].get("date")) for i in take]
        end = start + limit
        return ListPage(items, str(end) if end < len(ids) else None)

    def read(self, message_id: str) -> dict[str, Any] | None:
        self.reads += 1
        return self._stored(message_id) if message_id in self.messages else None

    def _stored(self, message_id: str) -> dict[str, Any]:
        message = self.messages[message_id]
        return {k: message.get(k) for k in ("message_id", "sender", "date", "subject", "body")}  # attachments never leave the fixture

    def _attachments(self, message_id: str) -> Any:  # test-only: the Core never calls it
        self.attachment_reads += 1
        return self.messages[message_id].get("attachments")


@dataclass(frozen=True)
class Parsed:
    message_id: str
    sender: str
    date: str
    subject: str
    body: str
    sort_ts: float

    def text(self) -> str:
        return "\n".join((f"From: {self.sender}", f"Date: {self.date}", f"Subject: {self.subject}", self.body))

    def parts(self) -> dict[str, tuple[int, int]]:
        head = len(f"From: {self.sender}\nDate: {self.date}\nSubject: {self.subject}")
        return {"headers": (0, head), "body": (head + 1, len(self.text()))}

    def header_spans(self) -> list[tuple[int, int]]:
        spans, start = [], 0
        for line in (f"From: {self.sender}", f"Date: {self.date}", f"Subject: {self.subject}"):
            spans.append((start, start + len(line)))
            start += len(line) + 1
        return spans


def _field(raw: dict[str, Any], key: str, *, multiline: bool = False, limit: int = MAX_FIELD_CHARS) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise MailError("malformed_message")
    if len(value) > limit:
        raise MailError("oversized")
    if _CONTROL.search(value if not multiline else value.replace("\n", "").replace("\r", "").replace("\t", "")):
        raise MailError("corrupt")  # also refuses a header line smuggled in through a sender or subject (a newline)
    return value


def to_epoch(stamp: str) -> float:
    moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    return (moment if moment.tzinfo else moment.replace(tzinfo=UTC)).timestamp()


def _epoch_or_floor(stamp: Any) -> float:
    """The order key of a listed date: an unusable or missing date sorts as the oldest."""
    try:
        return to_epoch(stamp) if isinstance(stamp, str) and stamp else float("-inf")
    except ValueError:
        return float("-inf")


def parse(raw: dict[str, Any] | None) -> Parsed:
    """Strict and bounded. Only five fields are read; a missing, mistyped, oversized, control-character or unparseable-date record is an explicit outcome, never repaired."""
    if not isinstance(raw, dict):
        raise MailError("unreadable")
    message_id = _field(raw, "message_id", limit=200)
    if not _ID.match(message_id):
        raise MailError("malformed_message")
    date = _field(raw, "date", limit=64)
    try:
        stamp = to_epoch(date)
    except ValueError:
        raise MailError("malformed_message") from None
    body = raw.get("body")
    if not isinstance(body, str):
        raise MailError("malformed_message")
    if len(body) > MAX_BODY_CHARS:
        raise MailError("oversized")
    if "\x00" in body:
        raise MailError("corrupt")
    return Parsed(message_id, _field(raw, "sender"), date, _field(raw, "subject"), body, stamp)


def _valid_entry(item: Any) -> Listed | None:
    """A listing entry is used only if it has exactly the right shape: a `Listed` with a well-formed string identity, a non-empty string change marker and a string-or-absent date."""
    if not isinstance(item, Listed):
        return None
    ok = isinstance(item.message_id, str) and bool(_ID.match(item.message_id)) and isinstance(item.version, str) and bool(item.version)
    return item if ok and (item.date is None or isinstance(item.date, str)) else None


def source_id_for(message_id: str) -> str:
    """An opaque identifier that carries none of the message (the contract's Opaque pattern)."""
    return "m" + hashlib.sha256(message_id.encode("utf-8")).hexdigest()[:24]


class _Guarded:
    """The only handle the index keeps on the adapter: every call first runs the access guard (owner grant AND platform permission, checked now)."""

    def __init__(self, mailbox: Mailbox, guard: Callable[[], None]) -> None:
        self._mailbox, self._guard = mailbox, guard

    def list_page(self, cursor: str | None, limit: int) -> ListPage:
        self._guard()
        return self._mailbox.list_page(cursor, limit)

    def read(self, message_id: str) -> dict[str, Any] | None:
        self._guard()
        return self._mailbox.read(message_id)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS msgs (
  message_id TEXT PRIMARY KEY, source_id TEXT UNIQUE NOT NULL, status TEXT NOT NULL, reason TEXT, version TEXT, content_sha TEXT, sort_ts REAL,
  sender TEXT, date TEXT, subject TEXT, body TEXT, seen_gen INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS msgs_order ON msgs (status, sort_ts DESC, message_id);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


class MailIndex(IndexStore):
    """The encrypted, restart-safe index of one mailbox. A message's state change (and its stored fields) commits as ONE transaction; re-running any step is harmless."""

    def __init__(
        self,
        path: Path,
        key: str | None,
        mailbox: Mailbox,
        source_type: str,
        rules: Rules | None = None,
        sensitivity: str | None = None,
        *,
        access: AccessCheck,
    ) -> None:
        rules = rules or load_rules()
        label = sensitivity or rules.sensitivity_of(source_type)
        if label not in rules.raw["sensitivity_order"]:
            raise ValueError("unknown sensitivity")
        self.source_type, self.label, self._access = source_type, label, access
        self._mailbox = _Guarded(mailbox, self._require)
        self._write_guard = self._require
        self.hook: Callable[[str], None] | None = None  # tests: called at each boundary; an exception inside a transaction rolls it back (a simulated crash)
        self.cancelled = threading.Event()
        self._lock = threading.RLock()
        self._conn = connect(path, key)
        self._conn.isolation_level = None
        with self._lock:
            self._conn.executescript(_SCHEMA)
            if self._conn.execute("PRAGMA user_version").fetchone()[0] > SCHEMA_VERSION:
                raise ValueError("newer index than this code understands")
        self._prepare_postings(self._texts)

    def close(self) -> None:
        self._conn.close()

    def _require(self) -> None:
        if not self._access.permitted(self.source_type):
            raise PermissionRevoked([{"source_type": self.source_type, "reason_code": "grant_revoked"}])

    # -- scanning: what the mailbox lists now (identities, change markers, dates: no body) ---------------------------------------------------------------------
    def scan(self) -> None:
        """Record what the mailbox holds now: at most MAX_MESSAGES, the newest. New or changed messages become pending (their stored text is dropped at once), vanished ones are
        forgotten, and the scan counts as complete only when this whole step has committed. The (possibly slow) listing runs OUTSIDE the index lock, and every write re-checks
        access inside its own transaction, so a revocation during the listing can never leave listed metadata behind."""
        self._require()
        self._transaction(lambda: self._set_meta("scan_state", "running"))
        self._hit("scan:begin")
        listed, malformed, cut_off = self._list_bounded()
        self._transaction(lambda: self._apply_scan(listed, malformed, cut_off))

    def _list_bounded(self) -> tuple[list[Listed], int, bool]:
        """The newest MAX_MESSAGES VALID entries of the mailbox, by consuming bounded pages, plus how many entries were malformed, plus whether the mailbox was NOT fully admitted.
        Memory is bounded by MAX_MESSAGES and work by MAX_LIST_WORK (and the number of pages by a fixed count), whatever the adapter returns. Everything the adapter returns is
        untrusted: a page of the wrong shape ends the scan with a non-content error before anything is written; an entry of the wrong shape or type is counted, never used.
        There is NO early stop: a sorted prefix proves nothing about the pages not yet seen, so the work budget is always used (and only the newest entries seen are kept). Entries
        beyond the work bound are never seen; that makes the scan incomplete, never complete."""
        heap: list[
            tuple[float, str, int, Listed]
        ] = []  # a min-heap: the oldest admitted entry is the one to drop (the counter keeps ties from ever comparing entries)
        cursor: str | None = None
        work = pages = malformed = 0
        over, exhausted = False, False
        while pages <= 2 * (MAX_LIST_WORK // PAGE_SIZE) + 2:
            pages += 1
            page = self._mailbox.list_page(cursor, PAGE_SIZE)
            if not (isinstance(page, ListPage) and isinstance(page.items, (list, tuple)) and (page.next_cursor is None or isinstance(page.next_cursor, str))):
                raise MailError("malformed_listing")  # nothing has been written: the previous index stands, and this scan never completes
            over = over or len(page.items) > PAGE_SIZE  # a page larger than asked for is never consumed past the limit
            for raw in page.items[:PAGE_SIZE]:
                work += 1
                item = _valid_entry(raw)
                if item is None:
                    malformed += 1
                    continue
                heapq.heappush(heap, (_epoch_or_floor(item.date), item.message_id, work, item))
                if len(heap) > MAX_MESSAGES:
                    heapq.heappop(heap)
            cursor = page.next_cursor
            if cursor is None:
                exhausted = True
                break
            if work >= MAX_LIST_WORK:
                break
        newest = [entry[3] for entry in sorted(heap, key=lambda e: (e[0], e[1], e[2]), reverse=True)]
        return newest, malformed, not exhausted or over or work - malformed > MAX_MESSAGES

    def _apply_scan(self, listed: list[Listed], malformed: int, cut_off: bool) -> None:
        gen = int(self._meta("generation", "0")) + 1
        for item in listed:
            self._note(item, gen)
        for ordinal in range(min(malformed, MAX_MALFORMED_ROWS)):
            self._note_malformed(ordinal, gen)  # a failed row with a synthetic identity: the malformed value itself is never stored
        self._hit("scan:mid")
        self._conn.execute("DELETE FROM postings WHERE key IN (SELECT message_id FROM msgs WHERE seen_gen < ?)", (gen,))
        self._conn.execute("DELETE FROM msgs WHERE seen_gen < ?", (gen,))
        self._set_meta("generation", str(gen))
        self._set_meta("scan_cut_off", "1" if cut_off or malformed > MAX_MALFORMED_ROWS else "0")
        self._set_meta("scan_state", "done")

    def _note_malformed(self, ordinal: int, gen: int) -> None:
        placeholder = f"malformed-listing-{ordinal}"
        self._conn.execute(
            "INSERT OR REPLACE INTO msgs (message_id, source_id, status, reason, version, sort_ts, seen_gen) VALUES (?,?,?,?,?,?,?)",
            (placeholder, source_id_for(placeholder), "failed", "malformed_message", None, None, gen),
        )

    def _note(self, item: Listed, gen: int) -> None:
        """A VALID listing entry (its identity is a well-formed string): new or changed ones become pending, unchanged ones are kept."""
        row = self._conn.execute("SELECT status, version FROM msgs WHERE message_id=?", (item.message_id,)).fetchone()
        if row is not None and row["version"] == item.version and row["status"] in ("indexed", "pending"):
            self._conn.execute("UPDATE msgs SET seen_gen=? WHERE message_id=?", (gen, item.message_id))
            return  # unchanged since it was last indexed (or judged)
        try:
            stamp = to_epoch(item.date) if item.date else None
        except ValueError:
            stamp = None
        self._conn.execute("DELETE FROM postings WHERE key=?", (item.message_id,))
        self._conn.execute(
            "INSERT OR REPLACE INTO msgs (message_id, source_id, status, reason, version, sort_ts, seen_gen) VALUES (?,?,?,?,?,?,?)",
            (item.message_id, source_id_for(item.message_id), "pending", None, item.version, stamp, gen),
        )

    # -- indexing: parse and store, a bounded slice at a time, newest first ----------------------------------------------------------------------------------------
    def run(self, max_messages: int = 10) -> dict[str, Any]:
        """Index at most `max_messages` pending messages, newest first (by stored date), then return, so a question is never queued behind a whole ingestion."""
        self._require()
        done = 0
        with self._lock:
            self._transaction(lambda: self._set_meta("paused", ""))
        for message_id in self._pending(max_messages):
            if self.cancelled.is_set():
                self._transaction(lambda: self._set_meta("paused", "cancelled"))
                break
            self._index_one(message_id)
            done += 1
        return {"indexed_now": done, **self.coverage()}

    def _pending(self, limit: int) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT message_id FROM msgs WHERE status='pending' ORDER BY (sort_ts IS NULL), sort_ts DESC, message_id LIMIT ?", (limit,)
            ).fetchall()
        return [r["message_id"] for r in rows]

    def _index_one(self, message_id: str) -> None:
        self._hit("msg:before")
        parsed: Parsed | None = None
        status, reason = "indexed", None
        try:
            parsed = parse(self._mailbox.read(message_id))
            if parsed.message_id != message_id:
                raise MailError("malformed_message")  # a record that is not the one asked for
        except MailError as error:
            parsed, status, reason = None, "failed", error.reason
        self._hit("msg:extracted")
        self._transaction(lambda: self._store(message_id, status, reason, parsed))
        self._hit("msg:after_commit")

    def _store(self, message_id: str, status: str, reason: str | None, parsed: Parsed | None) -> None:
        fields: tuple[Any, ...] = (None, None, None, None, None, None)
        if parsed is not None:
            fields = (sha256_text(parsed.text()), parsed.sort_ts, parsed.sender, parsed.date, parsed.subject, parsed.body)
        changed = self._conn.execute(
            "UPDATE msgs SET status=?, reason=?, content_sha=?, sort_ts=COALESCE(?, sort_ts), sender=?, date=?, subject=?, body=? WHERE message_id=? AND status='pending'",
            (status, reason, *fields, message_id),
        ).rowcount
        if changed and parsed is not None:
            self._post(message_id, parsed.text())
        self._hit("msg:mid_commit")

    def purge(self) -> None:
        """Drop every stored message and status: used when the source is revoked or re-designated."""

        def wipe() -> None:
            self._conn.execute("DELETE FROM msgs")
            self._conn.execute("DELETE FROM postings")
            self._conn.execute("DELETE FROM meta")

        self._transaction(wipe, guarded=False)  # the purge is what a revocation triggers: it must always be able to run

    # -- coverage ------------------------------------------------------------------------------------------------------------------------------------------
    def coverage(self) -> dict[str, Any]:
        with self._lock:
            counts = {r["status"]: r["n"] for r in self._conn.execute("SELECT status, count(*) AS n FROM msgs GROUP BY status")}
            reasons = {r["reason"]: r["n"] for r in self._conn.execute("SELECT reason, count(*) AS n FROM msgs WHERE reason IS NOT NULL GROUP BY reason")}
            failed_reasons = {
                r["reason"]: r["n"]
                for r in self._conn.execute("SELECT reason, count(*) AS n FROM msgs WHERE status='failed' AND reason IS NOT NULL GROUP BY reason")
            }
            missing = self._conn.execute("SELECT count(*) AS n FROM msgs WHERE sort_ts IS NULL AND status != 'failed'").fetchone()["n"]
            scan_done = self._meta("scan_state") == "done" and self._meta("scan_cut_off") != "1"
            paused = self._meta("paused") or None
        out = {
            "total": sum(counts.values()),
            "searched": counts.get("indexed", 0),
            "pending": counts.get("pending", 0),
            "failed": counts.get("failed", 0),
            "missing_timestamps": missing,
            "reasons": reasons,
            "failed_reasons": failed_reasons,
            "scan_complete": scan_done,
            "paused": paused,
        }
        out["complete"] = scan_done and paused is None and out["pending"] == 0 and out["failed"] == 0
        return out

    # -- the source store: what a citation is checked against ----------------------------------------------------------------------------------------------------
    def get(self, source_id: str) -> StoredSource | None:
        """The message as indexed, but only while the mailbox still holds exactly those stored fields. Changed, deleted, malformed now, or access ended: None (fail closed)."""
        if not self._access.permitted(self.source_type):
            return None
        with self._lock:
            row = self._conn.execute("SELECT * FROM msgs WHERE source_id=? AND status='indexed'", (source_id,)).fetchone()
        if row is None:
            return None
        parsed = self._current(row)
        if parsed is None:
            return None
        return StoredSource(row["source_id"], self.source_type, parsed.text(), parts=parsed.parts(), sensitivity=self.label)

    def _current(self, row: Any) -> Parsed | None:
        try:
            parsed = parse(self._mailbox.read(row["message_id"]))
        except (MailError, PermissionRevoked):
            return None
        return parsed if sha256_text(parsed.text()) == row["content_sha"] and parsed.message_id == row["message_id"] else None

    # -- the retriever --------------------------------------------------------------------------------------------------------------------------------------------
    def search(self, source_type: str, query: str) -> Iterable[dict[str, Any]]:
        """Passages (a stored header line, or one paragraph of a body) with exact spans and `message_part` locators, best match first, newest first among equals. Messages that
        changed since they were indexed are skipped, never answered from their old text."""
        words = terms(query)
        if source_type != self.source_type or not words:
            return []
        self._require()
        return self._rank(words, self._fetch, self._passages, lambda row: (-(row["sort_ts"] or 0.0), row["message_id"]), lambda sid: self.get(sid) is not None)

    def _fetch(self, keys: list[str]) -> list[Any]:
        rows: list[Any] = []
        with self._lock:
            for at in range(0, len(keys), FETCH_CHUNK):
                part = keys[at : at + FETCH_CHUNK]
                rows += self._conn.execute(f"SELECT * FROM msgs WHERE status='indexed' AND message_id IN ({','.join('?' for _ in part)})", part).fetchall()
        return rows

    def _texts(self) -> Iterator[tuple[str, str]]:
        for row in self._conn.execute("SELECT * FROM msgs WHERE status='indexed'"):
            yield row["message_id"], Parsed(row["message_id"], row["sender"], row["date"], row["subject"], row["body"], row["sort_ts"] or 0.0).text()

    def _passages(self, row: Any) -> list[dict[str, Any]]:
        parsed = Parsed(row["message_id"], row["sender"], row["date"], row["subject"], row["body"], row["sort_ts"] or 0.0)
        text, version = parsed.text(), sha256_text(parsed.text())
        body_start = parsed.parts()["body"][0]
        spans = [("headers", a, b) for a, b in parsed.header_spans()] + [("body", body_start + a, body_start + b) for a, b in paragraph_blocks(parsed.body)]
        return [
            {
                "evidence": {
                    "source_id": row["source_id"],
                    "source_type": self.source_type,
                    "version_sha256": version,
                    "locator": {"kind": "message_part", "message_part": part},
                    "span": {"start": start, "end": end},
                },
                "text": text[start:end],
            }
            for part, start, end in spans
            if end > start
        ]


__all__ = ["InMemoryMailbox", "ListPage", "Listed", "MailError", "MailIndex", "Mailbox", "Parsed", "parse", "source_id_for"]
