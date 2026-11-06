"""Filing the original documents and mail into folders: the same gate as for pictures (prepared, shown in the confirmation window, confirmed by the person,
checked again, journalled, audited), for the files in the inbox folder.

- A document that lies in the inbox is MOVED into a folder inside the inbox, and can be put back.
- A mail message that lies in the inbox's `mail` folder is COPIED into `Filed mail/<folder>`; the original stays. Apple Mail's own store is never written to.
- Files in a named collection (the bank statements) are never touched: they stay read-only.
The file behind a document is found again by name and proved by its content hash, so a document is never filed from a guess."""

from __future__ import annotations

import hashlib
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from images.export import sanitize_folder_name
from images.safety import is_inside

from . import store

MOVE, COPY = "file_move", "file_copy"
KINDS = (MOVE, COPY)
MAIL_FOLDER = "mail"
COPIES_FOLDER = "Filed mail"
MAX_FILES = 500


def inbox() -> Path | None:
    value = os.environ.get("LIBRARY_INBOX", "")
    path = Path(value).expanduser().resolve() if value else None
    return path if path and path.is_dir() else None


def _digest(path: Path, area: str) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return hashlib.sha256((area + h.hexdigest()).encode()).hexdigest() if area else h.hexdigest()


def _stamp(path: Path) -> list[float]:
    try:
        stat = path.stat()
    except OSError:
        return [-1, -1]
    return [stat.st_size, int(stat.st_mtime)]


def _locate(root: Path, doc: dict, folders: dict[str, list[Path]]) -> Path | None:
    """The one file in the inbox that is this document: same name, same content hash. Several or none means it is not filed."""
    if "/" in doc["name"]:
        return None  # a part of an archive or mail: there is no file of its own
    area = "mail" if doc["area"] == "mail" else ""
    found = [
        p for p in folders.get(doc["name"], []) if (MAIL_FOLDER in p.relative_to(root).parts[:1]) == (area == "mail") and _digest(p, area) == doc["sha256"]
    ]
    return found[0] if len(found) == 1 else None


def prepare(conn, args: dict) -> tuple[list[list], str, str, list[str]]:
    """Which files would go where. Returns the entries, the kind, the destination folder and the documents that could not be found as files."""
    root = inbox()
    if root is None:
        raise ValueError("the inbox folder is not available for filing here")
    mail = args.get("mail") is True
    name = sanitize_folder_name(str(args.get("folder", "")))
    if not str(args.get("folder", "")).strip():
        raise ValueError("a folder name is needed to file documents into")
    kinds = [k for k in str(args.get("kind", "")).replace(" ", "").split(",") if k]
    if not kinds and not mail:
        raise ValueError("say which kind of document to file (for example invoice or insurance)")
    wanted = store.list_documents(conn, kinds, area="mail" if mail else "", limit=500)
    wanted = [d for d in wanted if (d["area"] == "mail") == mail and d["area"] in ("", "mail")]
    folders: dict[str, list[Path]] = {}
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            folders.setdefault(path.name, []).append(path)
    dest = root / COPIES_FOLDER / name if mail else root / name
    entries: list[list] = []
    missing: list[str] = []
    for doc in wanted:
        src = _locate(root, doc, folders)
        if src is None:
            missing.append(doc["name"])
        elif not is_inside(src, dest):
            entries.append([doc["id"], str(src), str(dest / src.name), *_stamp(src)])
    if not entries:
        raise ValueError("no matching original file could be found to file" + (f" ({len(missing)} documents have no file of their own)" if missing else ""))
    return entries[:MAX_FILES], COPY if mail else MOVE, str(dest), missing


def problems(kind: str, entries: list[list], dest: str) -> list[str]:
    """Everything that is wrong with doing this right now. Empty means it may be done."""
    root = inbox()
    if root is None:
        return ["the inbox folder is not available"]
    found: list[str] = []
    target = Path(dest).resolve()
    if len(entries) > MAX_FILES:
        found.append(f"it touches {len(entries)} files; the most one change may touch is {MAX_FILES}")
    if not is_inside(target, root) or target == root or (kind == MOVE and MAIL_FOLDER in target.relative_to(root).parts[:1]):
        found.append("the destination is not a folder inside your inbox")
    if not os.access(root, os.W_OK):
        found.append("the inbox folder is read-only here")
    gone = changed = clash = outside = 0
    for _, src, dst, size, mtime in entries:
        path = Path(src)
        if not path.is_file():
            gone += 1
        elif _stamp(path) != [size, mtime]:
            changed += 1
        if not is_inside(path.resolve(), root) or (kind == MOVE and MAIL_FOLDER in path.resolve().relative_to(root).parts[:1]):
            outside += 1
        if Path(dst).exists():
            clash += 1
    for count, text in (
        (gone, "no longer where it was"),
        (changed, "changed since this was prepared"),
        (clash, "would land on a file that already exists"),
        (outside, "not a file that may be filed"),
    ):
        if count:
            found.append(f"{count} file(s) {text}")
    return found


def carry_out(conn, kind: str, entries: list[list], label: str) -> dict[str, Any]:
    """Do it: each file is written to the journal first, then moved or copied, then looked for at its new place."""
    batch = uuid.uuid4().hex[:12]
    done, failed = 0, []
    for _, src, dst, size, _mtime in entries:
        cur = conn.execute("INSERT INTO file_moves (batch, src, dst, op, status, at) VALUES (?,?,?,?, 'pending', ?)", (batch, src, dst, kind, time.time()))
        conn.commit()  # journal first, then act
        try:
            Path(dst).parent.mkdir(parents=True, exist_ok=True)
            if Path(dst).exists():
                raise OSError("a file is already there")
            if kind == COPY:
                shutil.copy2(src, dst)
            else:
                os.rename(src, dst)
            if not Path(dst).is_file() or Path(dst).stat().st_size != size:
                raise OSError("not found at its new place after the change")
            conn.execute("UPDATE file_moves SET status='done' WHERE id=?", (cur.lastrowid,))
            done += 1
        except OSError as exc:
            conn.execute("UPDATE file_moves SET status='failed' WHERE id=?", (cur.lastrowid,))
            failed.append(str(exc))
        conn.commit()
    verb = "copied" if kind == COPY else "moved"
    text = f"{verb} {done} of {len(entries)}" + (f"; {len(failed)} could not be done ({failed[0]})" if failed else "")
    return {"status": "done" if done else "failed", "text": text, "batch": batch if kind == MOVE else None}


def undo(conn, batch: str) -> str:
    """Put moved files back where they were; nothing is overwritten."""
    back, left = 0, 0
    for r in conn.execute("SELECT id, src, dst FROM file_moves WHERE batch=? AND op=? AND status='done'", (batch, MOVE)).fetchall():
        src, dst = Path(r["src"]), Path(r["dst"])
        if dst.is_file() and not src.exists():
            os.rename(dst, src)
            conn.execute("UPDATE file_moves SET status='undone' WHERE id=?", (r["id"],))
            back += 1
        else:
            left += 1
    conn.commit()
    return f"put back {back}" + (f"; {left} could not be put back (changed since)" if left else "")
