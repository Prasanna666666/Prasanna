"""Changes to the person's own pictures on disk: move them into a folder, delete them, copy them out, and undo.

Nothing happens in one step. A change is first PREPARED from a request (which pictures, where to) and only described: nothing on disk moves. It is carried out
only by a later question whose own words confirm it, never in the same turn that prepared it, and every move is journaled so it can be undone. A delete is
a move into a trash folder inside the photo folder, so it can be undone too; nothing here erases a file for good."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from images import export, organize
from images.safety import SafetyError
from kit import consent

from . import pictures

TRASH_FOLDER = "Aperture - deleted"
PENDING_SECONDS = 3600
EXAMPLES = 8
EXPORT_LIMIT = 500


def _engine(state):
    engine = state.engine()
    if engine is None:
        raise ValueError("pictures are not set up")
    return engine


def _refuse(why: str) -> dict[str, Any]:
    return {"ok": False, "error": why}


def prepare(state, conn, kind: str, args: dict, turn: str) -> dict[str, Any]:
    """Describe a move or a delete without doing anything, and remember it for confirmation."""
    engine = _engine(state)
    ids = pictures.find_ids(engine, args)
    if not ids:
        raise ValueError("no pictures match that request, so there is nothing to change")
    photo_dir = Path(engine.settings.photo_dir)
    if kind == "delete":
        folder = f"{TRASH_FOLDER}/{datetime.now().astimezone().date().isoformat()}"
        label = f"deleted {len(ids)} pictures"
    else:
        if not str(args.get("folder", "")).strip():
            raise ValueError("a folder name is needed to move pictures into")
        folder = export.sanitize_folder_name(str(args["folder"]))
        label = f"moved {len(ids)} pictures to {folder}"
    index = engine.db.connect()
    try:
        plan = organize.plan_move(index, engine.paths, engine.settings, ids, photo_dir / folder)
        names = (
            {
                r["id"]: Path(r["path"]).name
                for r in index.execute(f"SELECT id, path FROM items WHERE id IN ({','.join('?' * len(plan.entries))})", [e.item_id for e in plan.entries])
            }
            if plan.entries
            else {}
        )
    finally:
        index.close()
    if not plan.entries:
        raise ValueError("none of those pictures can be moved: " + "; ".join(sorted({why for _, why in plan.skipped})[:3]))
    change = uuid.uuid4().hex[:10]
    entries = [[e.item_id, e.src, e.dst] for e in plan.entries]
    conn.execute(
        "INSERT INTO pending_changes (id, kind, label, dest, entries, turn, created) VALUES (?,?,?,?,?,?,?)",
        (change, kind, label, str(plan.dest_dir), json.dumps(entries), turn, time.time()),
    )
    conn.commit()
    return {
        "change_id": change,
        "kind": kind,
        "will_move": plan.count,
        "megabytes": round(plan.total_bytes / 1_000_000, 1),
        "into": str(plan.dest_dir),
        "skipped": len(plan.skipped),
        "examples": [names.get(e.item_id, "?") for e in plan.entries[:EXAMPLES]],
        "status": "NOT DONE YET. Nothing has been changed. Tell the person exactly what would happen and ask them to confirm; it can be undone afterwards.",
    }


def apply(state, conn, change_id: str, user_text: str, turn: str) -> dict[str, Any]:
    """Carry out a prepared change, but only if it was prepared in an earlier question and this one's own words confirm it."""
    row = conn.execute("SELECT * FROM pending_changes WHERE id=?", (change_id,)).fetchone()
    if row is None:
        return _refuse("there is no such prepared change")
    if row["applied_batch"]:
        return _refuse("that change was already done")
    if row["turn"] == turn:
        return _refuse("a change cannot be confirmed in the same question that prepared it: ask the person first")
    if time.time() - row["created"] > PENDING_SECONDS:
        return _refuse("that change was prepared more than an hour ago: prepare it again")
    if not consent.says(consent.AFFIRM, user_text):
        return _refuse("the person has not confirmed: ask them, and wait for a yes")
    engine = _engine(state)
    plan = organize.MovePlan(Path(row["dest"]), [organize.MoveEntry(i, src, dst) for i, src, dst in json.loads(row["entries"])])
    index = engine.db.connect()
    try:
        report = organize.execute_move(index, engine.paths, engine.settings, plan, row["label"], scanning=bool(pictures.scan_state(engine).get("running")))
    except SafetyError as exc:
        return _refuse(str(exc))
    finally:
        index.close()
    conn.execute("UPDATE pending_changes SET applied_batch=? WHERE id=?", (report.batch, change_id))
    conn.commit()
    return {"done": True, "moved": report.moved, "failed": [f"{Path(s).name}: {why}" for s, why in report.failed[:5]], "undo_number": report.batch}


def undo(state, conn, batch: str, user_text: str) -> dict[str, Any]:
    """Put a batch back where it was, if the person's own words ask for it."""
    if not consent.says(consent.UNDO, user_text):
        return _refuse("the person has not asked to undo it")
    engine = _engine(state)
    index = engine.db.connect()
    try:
        report = organize.undo_batch(index, engine.paths, engine.settings, str(batch), scanning=bool(pictures.scan_state(engine).get("running")))
    except SafetyError as exc:
        return _refuse(str(exc))
    finally:
        index.close()
    return {"restored": report.moved, "failed": [f"{Path(s).name}: {why}" for s, why in report.failed[:5]]}


def recent(state, conn) -> list[dict[str, Any]]:
    """The latest changes that were carried out, newest first, with the number that undoes each."""
    index = _engine(state).db.connect()
    try:
        return [{"undo_number": b.id, "what": b.label, "files": b.moved, "undone": b.undone} for b in organize.list_batches(index, 10)]
    finally:
        index.close()


def copy_out(state, args: dict) -> dict[str, Any]:
    """Copy (never move) the matching pictures into an export folder on the drive, checking each copy."""
    engine = _engine(state)
    ids = pictures.find_ids(engine, args)[:EXPORT_LIMIT]
    if not ids:
        raise ValueError("no pictures match that request")
    folder = export.sanitize_folder_name(str(args.get("folder", ""))) or "Export"
    index = engine.db.connect()
    try:
        plan = export.build_plan(index, engine.paths, engine.settings, ids, folder)
        report = export.run_export(plan, engine.paths, engine.settings)
    finally:
        index.close()
    return {"copied": report.copied, "into": str(plan.folder), "failed": len(report.failed)}
