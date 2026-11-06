"""The one gate for everything that writes to the person's own files: move pictures, delete them, copy them out, and undo.

Every write goes the same way, with every check in this file:
1. PREPARED from a request (which pictures, where to). Only described and remembered: nothing on disk changes, and the assistant cannot go further.
2. SHOWN in a confirmation window the person opens: the full list, what it will do, what is wrong with it right now. Opening it is recorded.
3. CONFIRMED by the person pressing the button. There is no tool, request or sentence an assistant can use to do this for them.
4. CHECKED once more at that moment: nothing changed since it was prepared, everything still where it was, room to write, the right folders, a sensible size.
5. DONE with a journal written before each file is touched (so it can be undone) and verified afterwards; everything is recorded in an audit trail.
A delete is a move into a trash folder inside the photo folder, so it can be undone too; nothing here erases a file for good."""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from images import browse, export, organize
from images.safety import SafetyError, is_inside

from . import pictures

TRASH_FOLDER = "Aperture - deleted"
ALBUMS_FOLDER = "Trips"  # automatic albums: one folder per trip inside it
MIN_TRIP_PHOTOS = 5
EXPIRES_SECONDS = 3600  # a prepared change that was not confirmed within an hour is forgotten
MAX_FILES = 1000  # one change touches at most this many files: a bigger one is split, so a slip never reaches everything
EXAMPLES = 8
MIN_OPEN_SECONDS = 1.0  # the window must have been open this long before it can be confirmed
LISTED = 2000
_APPLYING = threading.Lock()  # one write at a time


class Refused(Exception):
    """A write that must not happen, in words the person can read."""


def _engine(state):
    engine = state.engine()
    if engine is None:
        raise Refused("pictures are not set up")
    return engine


def audit(conn, change_id: str, action: str, detail: str = "") -> None:
    conn.execute("INSERT INTO write_audit (at, change_id, action, detail) VALUES (?,?,?,?)", (time.time(), change_id, action, detail[:300]))
    conn.commit()


# ---- 1. prepared: described, nothing done -------------------------------------------------------------------------------------------------
def prepare(state, conn, kind: str, args: dict) -> tuple[dict[str, Any], dict[str, str]]:
    """Remember what a request would do. Returns what the assistant may say about it, and the card that opens the confirmation window."""
    engine = _engine(state)
    ids = pictures.find_ids(engine, args)
    if not ids:
        raise ValueError("no pictures match that request, so there is nothing to change")
    photo_dir = Path(engine.settings.photo_dir)
    stamp = datetime.now().astimezone().date().isoformat()
    if kind == "delete":
        folder, label = f"{TRASH_FOLDER}/{stamp}", f"delete {len(ids)} pictures (they go to a trash folder)"
    elif kind == "move":
        if not str(args.get("folder", "")).strip():
            raise ValueError("a folder name is needed to move pictures into")
        folder = export.sanitize_folder_name(str(args["folder"]))
        label = f"move {len(ids)} pictures into the folder {folder}"
    else:
        folder = export.sanitize_folder_name(str(args.get("folder", "")))
        label = f"copy {min(len(ids), MAX_FILES)} pictures into the export folder {folder}"
    index = engine.db.connect()
    try:
        if kind == "export":
            plan = export.build_plan(index, engine.paths, engine.settings, ids[:MAX_FILES], folder)
            entries = [[e.item_id, e.source, str(plan.folder / Path(e.source).name), *_stamp(e.source)] for e in plan.entries]
            dest = str(plan.folder)
        else:
            plan = organize.plan_move(index, engine.paths, engine.settings, ids, photo_dir / folder)
            entries = [[e.item_id, e.src, e.dst, *_stamp(e.src)] for e in plan.entries]
            dest = str(plan.dest_dir)
            if not entries:
                raise ValueError("none of those pictures can be moved: " + "; ".join(sorted({why for _, why in plan.skipped})[:3]))
    finally:
        index.close()
    if not entries:
        raise ValueError("there is nothing to copy for that request")
    return _remember(conn, kind, label, dest, entries)


def _remember(conn, kind: str, label: str, dest: str, entries: list[list]) -> tuple[dict[str, Any], dict[str, str]]:
    """Store a prepared change (nothing on disk changes) and return what the assistant may say and the card that opens the window."""
    change = uuid.uuid4().hex[:10]
    conn.execute(
        "INSERT INTO pending_changes (id, kind, label, dest, entries, nonce, created) VALUES (?,?,?,?,?,?,?)",
        (change, kind, label, dest, json.dumps(entries), secrets.token_hex(16), time.time()),
    )
    conn.commit()
    audit(conn, change, "prepared", f"{kind}: {len(entries)} files into {dest}")
    data = {
        "change_id": change,
        "kind": kind,
        "files": len(entries),
        "into": dest,
        "examples": [Path(e[1]).name for e in entries[:EXAMPLES]],
        "status": (
            "NOT DONE. A confirmation window is waiting for the person; nothing has changed. Tell them briefly what it would do and that they must review and press "
            "Confirm in the window. You cannot confirm it yourself."
        ),
    }
    card = {"kind": "confirm", "title": f"Confirm: {label}", "subtitle": "Waiting for you. Nothing has changed yet.", "link": f"#/changes?id={change}"}
    return data, card


def prepare_albums(state, conn, args: dict) -> tuple[dict[str, Any], dict[str, str]]:
    """Sort the pictures of every trip into its own folder `Trips/<year> <place>` inside the photo folder: one change, one window, nothing done until confirmed."""
    engine = _engine(state)
    photo_dir = Path(engine.settings.photo_dir)
    year = str(args.get("year", ""))[:4]
    index = engine.db.connect()
    try:
        trips = [t for t in browse.trips(index) if t["place"] and t["n"] >= MIN_TRIP_PHOTOS and (not year or t["start"][:4] == year)]
        entries: list[list] = []
        names: list[str] = []
        taken: set[int] = set()
        for trip in trips:
            ids = [i for i in pictures.find_ids(engine, {"from": trip["start"], "to": trip["stop"]}) if i not in taken]
            folder = f"{ALBUMS_FOLDER}/{export.sanitize_folder_name(trip['start'][:4] + ' ' + trip['place'])}"
            plan = organize.plan_move(index, engine.paths, engine.settings, ids, photo_dir / folder)
            if plan.entries:
                taken.update(e.item_id for e in plan.entries)
                names.append(folder)
                entries += [[e.item_id, e.src, e.dst, *_stamp(e.src)] for e in plan.entries]
    finally:
        index.close()
    if not entries:
        raise ValueError("no trip has pictures that could be sorted into an album (or they are already sorted)")
    label = f"sort {len(entries)} pictures into {len(names)} trip albums inside {ALBUMS_FOLDER}"
    return _remember(conn, "albums", label, str(photo_dir / ALBUMS_FOLDER), entries[:MAX_FILES])


def _stamp(path: str) -> list[float]:
    try:
        stat = os.stat(path)
    except OSError:
        return [-1, -1]
    return [stat.st_size, int(stat.st_mtime)]


# ---- 2. shown ---------------------------------------------------------------------------------------------------------------------------------
def problems(engine, kind: str, entries: list[list], dest: str) -> list[str]:
    """Everything that is wrong with doing this right now. Empty means it may be done."""
    found: list[str] = []
    photo = Path(engine.settings.photo_dir).expanduser().resolve()
    if len(entries) > MAX_FILES:
        found.append(f"it touches {len(entries)} files; the most one change may touch is {MAX_FILES}")
    if pictures.scan_state(engine).get("running"):
        found.append("the pictures are being read right now: wait for that to finish")
    if kind != "export":
        target = Path(dest).resolve()
        if not is_inside(target, photo) or target == photo:
            found.append("the destination is not a folder inside your photo folder")
        if is_inside(target, engine.paths.root.resolve()):
            found.append("the destination is inside the program's own data folder")
    changed = missing = clash = outside = 0
    for _, src, dst, size, mtime in entries:
        path = Path(src)
        if not path.is_file():
            missing += 1
        elif _stamp(src) != [size, mtime]:
            changed += 1
        if kind != "export" and not is_inside(path.resolve(), photo):
            outside += 1
        if Path(dst).exists():
            clash += 1
    for count, text in (
        (missing, "no longer where it was"),
        (changed, "changed since this was prepared"),
        (clash, "would land on a file that already exists"),
        (outside, "outside your photo folder"),
    ):
        if count:
            found.append(f"{count} file(s) {text}")
    return found


def details(conn, state, change_id: str) -> dict[str, Any]:
    """The whole change for the confirmation window, with what is wrong with it now. Opening it is recorded: it cannot be confirmed unopened."""
    row = conn.execute("SELECT * FROM pending_changes WHERE id=?", (change_id,)).fetchone()
    if row is None:
        raise Refused("there is no such change")
    entries = json.loads(row["entries"])
    engine = _engine(state)
    expired = row["status"] == "pending" and time.time() - row["created"] > EXPIRES_SECONDS
    if row["status"] == "pending" and not expired:
        conn.execute("UPDATE pending_changes SET viewed=? WHERE id=?", (time.time(), change_id))
        conn.commit()
        audit(conn, change_id, "opened")
    return {
        "id": row["id"],
        "kind": row["kind"],
        "label": row["label"],
        "into": row["dest"],
        "status": "expired" if expired else row["status"],
        "files": len(entries),
        "megabytes": round(sum(max(e[3], 0) for e in entries) / 1_000_000, 1),
        "list": [{"name": Path(e[1]).name, "from": str(Path(e[1]).parent), "to": e[2]} for e in entries[:LISTED]],
        "problems": problems(engine, row["kind"], entries, row["dest"]) if row["status"] == "pending" and not expired else [],
        "nonce": row["nonce"] if row["status"] == "pending" and not expired else "",
        "result": row["result"],
        "undo_number": row["batch"] if row["kind"] != "export" and row["status"] == "done" else "",
    }


# ---- 3 to 5. confirmed, checked, done ---------------------------------------------------------------------------------------------------
def confirm(state, conn, change_id: str, nonce: str) -> dict[str, Any]:
    """The person pressed Confirm in the window."""
    row = conn.execute("SELECT * FROM pending_changes WHERE id=?", (change_id,)).fetchone()
    try:
        _allowed(row, nonce)
        engine = _engine(state)
        entries = json.loads(row["entries"])
        wrong = problems(engine, row["kind"], entries, row["dest"])
        if wrong:
            raise Refused("Not done: " + "; ".join(wrong) + ". Prepare it again.")
        if not _APPLYING.acquire(blocking=False):
            raise Refused("another change is being made: try again in a moment")
        try:
            result = _carry_out(engine, conn, row, entries)
        finally:
            _APPLYING.release()
    except Refused as why:
        if row is not None:
            audit(conn, change_id, "refused", str(why))
        return {"ok": False, "error": str(why)}
    conn.execute(
        "UPDATE pending_changes SET status=?, decided=?, batch=?, result=? WHERE id=?",
        (result["status"], time.time(), result.get("batch"), result["text"], change_id),
    )
    conn.commit()
    audit(conn, change_id, "confirmed", result["text"])
    return {"ok": True, **result}


def _allowed(row, nonce: str) -> None:
    if row is None:
        raise Refused("there is no such change")
    if row["status"] != "pending":
        raise Refused(f"that change is already {row['status']}")
    if time.time() - row["created"] > EXPIRES_SECONDS:
        raise Refused("that change was prepared more than an hour ago: prepare it again")
    if not secrets.compare_digest(str(nonce), row["nonce"]):
        raise Refused("this is not the window that was opened for the change")
    if row["viewed"] is None or time.time() - row["viewed"] < MIN_OPEN_SECONDS:
        raise Refused("the change must be looked at in the window before it is confirmed")


def _carry_out(engine, conn, row, entries: list[list]) -> dict[str, Any]:
    index = engine.db.connect()
    try:
        if row["kind"] == "export":
            plan = export.build_plan(index, engine.paths, engine.settings, [e[0] for e in entries], Path(row["dest"]).name)
            report = export.run_export(plan, engine.paths, engine.settings)
            ok = not report.failed
            return {"status": "done" if ok else "failed", "text": f"copied {report.copied}, {len(report.failed)} failed, into {row['dest']}"}
        plan = organize.MovePlan(Path(row["dest"]), [organize.MoveEntry(e[0], e[1], e[2]) for e in entries])
        try:
            report = organize.execute_move(index, engine.paths, engine.settings, plan, row["label"], scanning=False)
        except SafetyError as exc:
            raise Refused(str(exc)) from exc
        failed = {src for src, _ in report.failed}
        for entry in entries:  # verified afterwards: each file that was moved is really at its new place
            if entry[1] not in failed and not Path(entry[2]).is_file():
                report.failed.append((entry[1], "not found at its new place after the move"))
                report.moved -= 1
        text = f"moved {report.moved} of {len(entries)}" + (f"; {len(report.failed)} could not be moved ({report.failed[0][1]})" if report.failed else "")
        return {"status": "done" if report.moved else "failed", "text": text, "batch": report.batch}
    finally:
        index.close()


def cancel(conn, change_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT status FROM pending_changes WHERE id=?", (change_id,)).fetchone()
    if row is None or row["status"] != "pending":
        return {"ok": False, "error": "there is nothing waiting under that number"}
    conn.execute("UPDATE pending_changes SET status='cancelled', decided=? WHERE id=?", (time.time(), change_id))
    conn.commit()
    audit(conn, change_id, "cancelled")
    return {"ok": True}


def undo(state, conn, batch: str) -> dict[str, Any]:
    """The person pressed Undo for a move or delete that was done."""
    row = conn.execute("SELECT id FROM pending_changes WHERE batch=? AND status='done'", (batch,)).fetchone()
    if row is None:
        return {"ok": False, "error": "there is no such change to undo"}
    engine = _engine(state)
    if pictures.scan_state(engine).get("running"):
        return {"ok": False, "error": "the pictures are being read right now: wait for that to finish"}
    index = engine.db.connect()
    try:
        report = organize.undo_batch(index, engine.paths, engine.settings, batch, scanning=False)
    except SafetyError as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        index.close()
    text = f"put back {report.moved}" + (f"; {len(report.failed)} could not be put back ({report.failed[0][1]})" if report.failed else "")
    conn.execute("UPDATE pending_changes SET status='undone', result=? WHERE id=?", (text, row["id"]))
    conn.commit()
    audit(conn, row["id"], "undone", text)
    return {"ok": True, "text": text}


def overview(conn) -> dict[str, Any]:
    """What is waiting for the person, and what was done lately (newest first), for the Changes page."""

    def summary(r) -> dict[str, Any]:
        return {
            "id": r["id"],
            "kind": r["kind"],
            "label": r["label"],
            "status": r["status"],
            "files": len(json.loads(r["entries"])),
            "result": r["result"],
            "undo_number": r["batch"] if r["status"] == "done" and r["kind"] != "export" else "",
        }

    cutoff = time.time() - EXPIRES_SECONDS
    waiting = [summary(r) for r in conn.execute("SELECT * FROM pending_changes WHERE status='pending' AND created>? ORDER BY created DESC", (cutoff,))]
    history = [summary(r) for r in conn.execute("SELECT * FROM pending_changes WHERE status<>'pending' ORDER BY COALESCE(decided, created) DESC LIMIT 30")]
    return {"waiting": waiting, "history": history}
