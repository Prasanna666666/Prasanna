"""The Core-owned document source (WP3.2): a bounded, deterministic path from a designated folder to exact evidence, with no model in it.

    designated folder --Scanner--> Extractor (bounded, stdlib only) --DocumentIndex (encrypted SQLite)--> Retriever / SourceStore --> the existing gate

* Nothing here decides who may read anything: every passage still goes through `GatedRetrieval` / `ContextBuilder` / `GatedModel`, which check the grant and the TRUSTED label
  this store reports (`StoredSource.sensitivity`). This module only produces and keeps the material, and refuses to hand out anything it cannot prove is still current.
* A file that cannot be read in full is never skipped, truncated, guessed or cited: it becomes an explicit coverage outcome (unsupported / failed, with a reason code).
* A source is current only while the bytes on disk still hash to what was indexed: a changed or deleted file is unresolvable, so its old passages can never be cited.
* Newest first means the file system's modification time. A date found inside a document is kept separately (`created`) and never replaces it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import threading
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from kit.db import connect

from .access import AccessCheck
from .evidence import StoredSource, sha256_text
from .policy import PermissionRevoked
from .rules import Rules, load_rules

MAX_BYTES = 2_000_000  # a larger file is 'oversized': it is reported, never truncated
MAX_BLOCK_CHARS = 1_200  # a longer paragraph is split into several blocks, each its own exact locator
MAX_BLOCKS = 5_000  # a document that would need more blocks is 'oversized' (a parser bomb is refused, not cut)
MAX_FILES = 20_000  # a folder with more files is scanned only that far and says so: coverage is never complete
MIN_FREE_BYTES = 64 * 1024 * 1024  # below this much free disk, indexing pauses (and says so) instead of failing halfway
RESULT_LIMIT = 8
SCHEMA_VERSION = 1
_BREAK = re.compile(r"\n[ \t\r]*\n")  # a blank line ends a paragraph
_WORD = re.compile(r"\w+", re.UNICODE)
_CREATED = re.compile(r"\A---\r?\n(?:.*\r?\n)*?created:[ \t]*(\d{4}-\d{2}-\d{2})[ \t]*\r?\n(?:.*\r?\n)*?---[ \t]*(?:\r?\n|\Z)")


class ExtractionError(Exception):
    """A document that cannot be extracted in full. `reason` is a code (never content): unsupported_format, encrypted, corrupt or oversized."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Extracted:
    text: str
    blocks: tuple[tuple[int, int], ...]
    created: str | None = None  # a date the document itself states: kept separately, never used for ordering


class Extractor(Protocol):
    def extract(self, data: bytes) -> Extracted: ...


def paragraph_blocks(text: str) -> tuple[tuple[int, int], ...]:
    out: list[tuple[int, int]] = []
    edges = [0, *(i for m in _BREAK.finditer(text) for i in (m.start(), m.end())), len(text)]
    for low, high in zip(edges[::2], edges[1::2], strict=True):
        piece = text[low:high]
        start, end = low + len(piece) - len(piece.lstrip()), low + len(piece.rstrip())
        if end <= start:
            continue
        while end - start > MAX_BLOCK_CHARS:
            cut = text.rfind(" ", start + MAX_BLOCK_CHARS // 2, start + MAX_BLOCK_CHARS)
            cut = start + MAX_BLOCK_CHARS if cut < 0 else cut
            out.append((start, cut))
            start = cut + (1 if text[cut : cut + 1].isspace() else 0)
        out.append((start, end))
        if len(out) > MAX_BLOCKS:
            raise ExtractionError("oversized")
    return tuple(b for b in out if b[1] > b[0])


def _created(text: str) -> str | None:
    found = _CREATED.match(text)
    try:
        return date.fromisoformat(found.group(1)).isoformat() if found else None
    except ValueError:
        return None  # an impossible date is no date; it is not guessed


class TextExtractor:
    """Plain UTF-8 text and Markdown. Strict: invalid UTF-8 or a NUL byte is 'corrupt' (a binary file in disguise), never decoded with replacement characters."""

    def extract(self, data: bytes) -> Extracted:
        if len(data) > MAX_BYTES:
            raise ExtractionError("oversized")
        if b"\x00" in data:
            raise ExtractionError("corrupt")
        try:
            text = data.decode("utf-8-sig")  # a leading byte-order mark is dropped; evidence offsets are into this exact text, whose hash is the version
        except UnicodeDecodeError:
            raise ExtractionError("corrupt") from None
        blocks = paragraph_blocks(text)
        if not blocks:
            raise ExtractionError("corrupt")  # nothing extractable: a file that yields no text is not 'indexed'
        return Extracted(text, blocks, _created(text))


EXTRACTORS: dict[str, Extractor] = {".txt": TextExtractor(), ".md": TextExtractor()}  # the audited formats; anything else is reported as unsupported


@dataclass(frozen=True)
class Found:
    rel_path: str
    size: int
    mtime: float | None  # None: the file system gave no usable time (counted in coverage; ordered after every file that has one)
    kind: str  # "file" or a refusal code (symlink_refused)


def race_safe_platform() -> bool:
    """Descriptor-relative, no-follow traversal is the only way to keep a file outside the root unreachable while the tree changes under us; without it the scanner refuses to run."""
    return hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY") and os.open in os.supports_dir_fd and os.scandir in os.supports_fd


_DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
_FILE_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)


class Scanner:
    """Reads only below one designated root. Every directory and file is opened RELATIVE TO THE ALREADY-OPEN PARENT descriptor with no-follow flags, so a link planted on any
    component (also between a check and the open) cannot lead outside the root: the open fails and the item is reported. A file above the size limit is refused, never cut."""

    def __init__(self, root: Path, max_files: int = MAX_FILES, *, guard: Callable[[], None]) -> None:
        self._guard = guard  # called immediately before EVERY directory open, listing and file open; it raises when access is no longer current. There is no way to scan without one.
        if not race_safe_platform():
            raise RuntimeError("this platform cannot guarantee race-free, root-confined reads; the document source is disabled")
        self.root, self._max_files = root.resolve(), max_files
        self.stat_time: Callable[[os.stat_result], float | None] = lambda st: st.st_mtime  # tests replace it to simulate a missing timestamp
        self.seam: Callable[[str, str], None] | None = (
            None  # tests: called before and after each component is opened, to change the tree at exactly that moment
        )

    def _open_dir(self, parts: tuple[str, ...]) -> int:
        self._guard()
        fd = os.open(self.root, _DIR_FLAGS)
        try:
            for part in parts:
                if self.seam is not None:
                    self.seam("before", part)
                self._guard()  # after any hook, immediately before the open
                child = os.open(part, _DIR_FLAGS, dir_fd=fd)  # directory only, never a link
                os.close(fd)
                fd = child
                if self.seam is not None:
                    self.seam("after", part)
        except BaseException:
            os.close(fd)
            raise
        return fd

    def _classify(self, entry: os.DirEntry[str], rel: str) -> Found | None:
        """What one directory entry is. None for a sub-directory (it is walked); an unreadable entry is raised as OSError by the caller's guard."""
        if entry.is_symlink():
            return Found(rel, 0, None, "symlink_refused")
        if entry.is_dir(follow_symlinks=False):
            return None
        if entry.is_file(follow_symlinks=False):
            st = entry.stat(follow_symlinks=False)
            return Found(rel, st.st_size, self.stat_time(st), "file")
        return Found(rel, 0, None, "unsupported_entry")  # a device, socket or pipe: reported, never opened

    def _listing(self, parts: tuple[str, ...]) -> list[tuple[str, Found | None]]:
        """Each entry of one directory as (name, Found or None for a sub-directory). Entries are classified while the directory descriptor is still open; an entry that cannot be
        examined becomes a failed item instead of being lost."""
        fd = self._open_dir(parts)
        out: list[tuple[str, Found | None]] = []
        try:
            self._guard()
            with os.scandir(fd) as entries:
                for entry in sorted(entries, key=lambda e: e.name):
                    rel = "/".join((*parts, entry.name))
                    try:
                        out.append((entry.name, self._classify(entry, rel)))
                    except OSError:
                        out.append((entry.name, Found(rel, 0, None, "unreadable_entry")))
        finally:
            os.close(fd)
        return out

    def walk(self) -> tuple[list[Found], bool]:
        """Every item below the root (breadth first, sorted, so the result is deterministic) and whether the walk was cut off by the file limit. A directory or an entry that
        cannot be read is NOT dropped: it becomes a failed item (`unreadable_directory` / `unreadable_entry`), so the scan can never look complete when part of the tree was not inspected."""
        found: list[Found] = []
        queue: list[tuple[str, ...]] = [()]
        while queue:
            parts = queue.pop(0)
            try:
                entries = self._listing(parts)
            except OSError:
                found.append(Found("/".join(parts) or ".", 0, None, "unreadable_directory"))
                continue
            for name, item in entries:
                if len(found) >= self._max_files:
                    return found, True
                if item is None:
                    queue.append((*parts, name))
                else:
                    found.append(item)
        return found, False

    def read(self, rel_path: str) -> bytes:
        """The bytes of one regular file, or ExtractionError. No absolute path, no '..', no link on ANY component (checked by the open itself, not beforehand), and at most MAX_BYTES
        (a bigger file is oversized, not truncated)."""
        pure = PurePosixPath(rel_path)
        parts = pure.parts
        if not parts or pure.is_absolute() or ".." in parts or "\x00" in rel_path:
            raise ExtractionError("unreadable")
        try:
            parent = self._open_dir(parts[:-1])
            try:
                self._guard()  # the final check: after every hook and directory step, immediately before the file is opened
                fd = os.open(parts[-1], _FILE_FLAGS, dir_fd=parent)
            finally:
                os.close(parent)
            with os.fdopen(fd, "rb") as handle:
                if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                    raise ExtractionError("unreadable")
                data = handle.read(MAX_BYTES + 1)
        except OSError:
            raise ExtractionError("unreadable") from None
        if len(data) > MAX_BYTES:
            raise ExtractionError("oversized")
        return data


def source_id_for(rel_path: str) -> str:
    """An opaque identifier that carries none of the file's name or content (the contract's Opaque pattern)."""
    return "d" + hashlib.sha256(rel_path.encode("utf-8")).hexdigest()[:24]


def terms(query: str) -> list[str]:
    return sorted({w for w in (m.group(0).lower() for m in _WORD.finditer(query)) if len(w) >= 2})  # noqa: PLR2004


_SCHEMA = """
CREATE TABLE IF NOT EXISTS docs (
  rel_path TEXT PRIMARY KEY, source_id TEXT UNIQUE NOT NULL, status TEXT NOT NULL, reason TEXT, content_sha TEXT, size INTEGER NOT NULL,
  mtime REAL, created TEXT, text TEXT, blocks TEXT, seen_gen INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS docs_order ON docs (status, mtime DESC, rel_path);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


class IndexStore:
    """The plumbing the two local indexes (documents, mail) share: a lock, an optional test hook, a key/value `meta` table and one transaction helper. A subclass sets `_conn`
    (an encrypted connection opened with explicit transactions) and `_lock`."""

    _conn: Any
    _lock: threading.RLock
    hook: Callable[[str], None] | None = None

    def _hit(self, name: str) -> None:
        if self.hook is not None:
            self.hook(name)

    def _meta(self, key: str, default: str = "") -> str:
        row = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return str(row["value"]) if row else default

    def _set_meta(self, key: str, value: str) -> None:
        self._conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)", (key, value))

    def _transaction(self, body: Callable[[], None]) -> None:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                body()
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise


class DocumentIndex(IndexStore):
    """The encrypted, restart-safe index of one designated folder. Every document's state change (and its text) commits as ONE transaction, so a crash leaves each document
    either as it was or fully in its new state; re-running any step is harmless (same bytes -> same result)."""

    def __init__(
        self, path: Path, key: str | None, root: Path, source_type: str, rules: Rules | None = None, sensitivity: str | None = None, *, access: AccessCheck
    ) -> None:
        rules = rules or load_rules()
        label = sensitivity or rules.sensitivity_of(source_type)
        if label not in rules.raw["sensitivity_order"]:
            raise ValueError("unknown sensitivity")
        self.source_type, self.label, self._access = source_type, label, access
        self.scanner = Scanner(root, guard=self._require)
        self.hook: Callable[[str], None] | None = None  # tests: called at each boundary; an exception inside a transaction rolls it back (a simulated crash)
        self.free_bytes: Callable[[], int] = lambda: shutil.disk_usage(path.parent).free
        self.cancelled = threading.Event()
        self._lock = threading.RLock()
        self._conn = connect(path, key)
        self._conn.isolation_level = None
        with self._lock:
            self._conn.executescript(_SCHEMA)
            if self._conn.execute("PRAGMA user_version").fetchone()[0] > SCHEMA_VERSION:
                raise ValueError("newer index than this code understands")
            self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def close(self) -> None:
        self._conn.close()

    # -- plumbing ----------------------------------------------------------------------------------------------------------------------------

    # -- scanning: what is in the folder now (cheap: names and times only) ------------------------------------------------------------------------
    def _require(self) -> None:
        """Nothing is scanned, indexed, searched or read unless the owner's grant AND the platform permission are current right now (checked again at every use)."""
        if not self._access.permitted(self.source_type):
            raise PermissionRevoked([{"source_type": self.source_type, "reason_code": "grant_revoked"}])

    def scan(self) -> None:
        """Record what the folder holds now. New or changed files become pending (their old text is dropped at once: a changed file is never answered from its old text),
        files that disappeared are forgotten, and the scan counts as complete only when this whole step has committed."""
        self._require()
        with self._lock:
            self._transaction(lambda: self._set_meta("scan_state", "running"))
            self._hit("scan:begin")
            found, cut_off = self.scanner.walk()
            gen = int(self._meta("generation", "0")) + 1
            self._transaction(lambda: self._apply_scan(found, cut_off, gen))

    def _apply_scan(self, found: list[Found], cut_off: bool, gen: int) -> None:
        for item in found:
            self._note_file(item, gen)
        self._hit("scan:mid")
        self._conn.execute("DELETE FROM docs WHERE seen_gen < ?", (gen,))  # a source that is gone is gone: its text and passages with it
        self._set_meta("generation", str(gen))
        self._set_meta("scan_cut_off", "1" if cut_off else "0")
        self._set_meta("scan_state", "done")

    def _note_file(self, item: Found, gen: int) -> None:
        row = self._conn.execute("SELECT status, size, mtime FROM docs WHERE rel_path=?", (item.rel_path,)).fetchone()
        status, reason = ("pending", None)
        if item.kind != "file":
            status, reason = "failed", item.kind
        elif EXTRACTORS.get(PurePosixPath(item.rel_path).suffix.lower()) is None:
            status, reason = "unsupported", "unsupported_format"
        if row is not None and (row["size"], row["mtime"]) == (item.size, item.mtime) and row["status"] in ("indexed", status):
            self._conn.execute("UPDATE docs SET seen_gen=? WHERE rel_path=?", (gen, item.rel_path))
            return  # unchanged since it was last indexed (or last judged): nothing to redo
        self._conn.execute(
            "INSERT OR REPLACE INTO docs (rel_path, source_id, status, reason, size, mtime, seen_gen) VALUES (?,?,?,?,?,?,?)",
            (item.rel_path, source_id_for(item.rel_path), status, reason, item.size, item.mtime, gen),
        )

    # -- indexing: extract and store, a bounded slice at a time, newest first ------------------------------------------------------------------------
    def run(self, max_docs: int = 10) -> dict[str, Any]:
        """Index at most `max_docs` pending documents, newest first, then return, so an interactive request is never queued behind a whole ingestion. Stops early, saying
        so, when cancelled or when the disk is nearly full; neither fails a document."""
        self._require()
        done = 0
        with self._lock:
            self._set_pause(None)
        for rel_path in self._pending(max_docs):
            self._require()  # withdrawn or lost between two documents: the next one is not touched
            if self.cancelled.is_set():
                self._set_pause("cancelled")
                break
            if self.free_bytes() < MIN_FREE_BYTES:
                self._set_pause("disk_pressure")
                break
            self._index_one(rel_path)
            done += 1
        return {"indexed_now": done, **self.coverage()}

    def _set_pause(self, reason: str | None) -> None:
        with self._lock:
            self._transaction(lambda: self._set_meta("paused", reason or ""))

    def _pending(self, limit: int) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT rel_path FROM docs WHERE status='pending' ORDER BY (mtime IS NULL), mtime DESC, rel_path LIMIT ?", (limit,)
            ).fetchall()
        return [r["rel_path"] for r in rows]

    def _index_one(self, rel_path: str) -> None:
        self._hit("doc:before")
        status, reason, data = "indexed", None, None
        extracted: Extracted | None = None
        try:
            raw = self.scanner.read(rel_path)
            extractor = EXTRACTORS.get(PurePosixPath(rel_path).suffix.lower())
            if extractor is None:
                raise ExtractionError("unsupported_format")
            extracted = extractor.extract(raw)
            data = hashlib.sha256(raw).hexdigest()
        except ExtractionError as error:
            status, reason = ("unsupported" if error.reason == "unsupported_format" else "failed"), error.reason
        self._hit("doc:extracted")
        self._transaction(lambda: self._store(rel_path, status, reason, data, extracted))
        self._hit("doc:after_commit")

    def _store(self, rel_path: str, status: str, reason: str | None, content_sha: str | None, extracted: Extracted | None) -> None:
        text = json_blocks = created = None
        if extracted is not None:
            text, json_blocks, created = extracted.text, json.dumps(extracted.blocks), extracted.created
        self._conn.execute(
            "UPDATE docs SET status=?, reason=?, content_sha=?, text=?, blocks=?, created=? WHERE rel_path=? AND status='pending'",
            (status, reason, content_sha, text, json_blocks, created, rel_path),
        )
        self._hit("doc:mid_commit")

    # -- the owner revokes the designation: nothing stays behind ------------------------------------------------------------------------------------
    def purge(self) -> None:
        """Drop every indexed text, passage and status. Used when the source is revoked or re-designated: a new grant starts from an empty index and a fresh scan."""

        def wipe() -> None:
            self._conn.execute("DELETE FROM docs")
            self._conn.execute("DELETE FROM meta")

        self._transaction(wipe)

    # -- coverage: what was searched, and what was not --------------------------------------------------------------------------------------------------
    def coverage(self) -> dict[str, Any]:
        with self._lock:
            counts = {r["status"]: r["n"] for r in self._conn.execute("SELECT status, count(*) AS n FROM docs GROUP BY status")}
            reasons = {r["reason"]: r["n"] for r in self._conn.execute("SELECT reason, count(*) AS n FROM docs WHERE reason IS NOT NULL GROUP BY reason")}
            missing = self._conn.execute("SELECT count(*) AS n FROM docs WHERE mtime IS NULL AND status != 'failed'").fetchone()["n"]
            scan_done = self._meta("scan_state") == "done" and self._meta("scan_cut_off") != "1"
            paused = self._meta("paused") or None
        out = {
            "total": sum(counts.values()),
            "searched": counts.get("indexed", 0),
            "pending": counts.get("pending", 0),
            "unsupported": counts.get("unsupported", 0),
            "failed": counts.get("failed", 0),
            "missing_timestamps": missing,
            "reasons": reasons,
            "scan_complete": scan_done,
            "paused": paused,
        }
        out["complete"] = scan_done and paused is None and out["pending"] == 0 and out["unsupported"] == 0 and out["failed"] == 0
        return out

    # -- the source store: what a citation is checked against ------------------------------------------------------------------------------------------
    def get(self, source_id: str) -> StoredSource | None:
        """The source as it was indexed, but only while the file on disk still has exactly the indexed bytes. Changed, deleted, replaced by a link or unreadable: None (fail closed)."""
        if not self._access.permitted(self.source_type):
            return None  # not permitted now: no stored text and no byte on disk is touched
        with self._lock:
            row = self._conn.execute("SELECT * FROM docs WHERE source_id=? AND status='indexed'", (source_id,)).fetchone()
        if row is None or not self._current(row):
            return None
        return StoredSource(row["source_id"], self.source_type, row["text"], blocks=tuple((a, b) for a, b in json.loads(row["blocks"])), sensitivity=self.label)

    def _current(self, row: Any) -> bool:
        try:
            return hashlib.sha256(self.scanner.read(row["rel_path"])).hexdigest() == row["content_sha"]
        except (ExtractionError, PermissionRevoked):
            return False  # unreadable, changed, or access ended just now: not a current source

    # -- the retriever: a ranked search over what is indexed so far -------------------------------------------------------------------------------------
    def search(self, source_type: str, query: str) -> Iterable[dict[str, Any]]:
        """Passages (one block each, exact span and locator) from the indexed documents, best match first, newest first among equals. Only for this index's own source type.
        Documents that changed on disk since they were indexed are skipped, never answered from their old text."""
        words = terms(query)
        if source_type != self.source_type or not words:
            return []
        self._require()
        scored: list[tuple[int, float, str, int, dict[str, Any]]] = []
        for row in self._indexed():
            for number, (start, end) in enumerate(json.loads(row["blocks"])):
                hits = sum(1 for w in words if w in set(_WORD.findall(row["text"][start:end].lower())))
                if hits:
                    scored.append((-hits, -(row["mtime"] or 0.0), row["rel_path"], number, self._passage(row, number, start, end)))
        scored.sort(key=lambda s: s[:4])
        verified: dict[str, bool] = {}
        out: list[dict[str, Any]] = []
        for *_, passage in scored:
            sid = passage["evidence"]["source_id"]
            if sid not in verified:
                verified[sid] = self.get(sid) is not None  # re-checked against the bytes on disk, once per document
            if verified[sid]:
                out.append(passage)
            if len(out) >= RESULT_LIMIT:
                break
        return out

    def _indexed(self) -> Iterator[Any]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM docs WHERE status='indexed' ORDER BY (mtime IS NULL), mtime DESC, rel_path").fetchall()
        return iter(rows)

    def _passage(self, row: Any, number: int, start: int, end: int) -> dict[str, Any]:
        evidence = {
            "source_id": row["source_id"],
            "source_type": self.source_type,
            "version_sha256": sha256_text(row["text"]),
            "locator": {"kind": "block", "block": number},
            "span": {"start": start, "end": end},
        }
        return {"evidence": evidence, "text": row["text"][start:end]}
