"""Answering questions in plain text, from facts read out of the library itself.

The model never has to remember or guess a number: every figure it may use is placed in front
of it first (library totals, places, cameras, people, indexing progress, move history, and
facts about the photos from the previous answer)."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from datetime import datetime

import numpy as np

from ..config import Paths
from ..db import chunked, in_clause
from ..indexing.progress import ScanLock, read_progress

SYSTEM_PROMPT = (
    "You are the Photos assistant, a private photo assistant. Answer the user's question in plain, friendly English, in 1 to 6 short "
    "sentences or a short list. Use ONLY the FACTS below; copy numbers exactly. If the facts do not contain the answer, "
    "say what you do not know and what the user could ask or do instead. Never invent photos, places, names or numbers. "
    "Folder paths are real: quote them as given."
)


def _rows(conn: sqlite3.Connection, sql: str, params: Sequence[object] = ()) -> list[sqlite3.Row]:
    return conn.execute(sql, tuple(params)).fetchall()


def _when(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%d %b %Y %H:%M")


def _library_facts(conn: sqlite3.Connection) -> list[str]:
    total, indexed, errors = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(meta_done),0), COALESCE(SUM(error IS NOT NULL),0) FROM items WHERE missing=0"
    ).fetchone()
    lines = [f"Library: {total:,} files, {indexed:,} indexed, {errors:,} with read errors."]
    kinds = ", ".join(f"{r[0]}: {r[1]:,}" for r in _rows(conn, "SELECT kind, COUNT(*) FROM items WHERE missing=0 GROUP BY kind"))
    if kinds:
        lines.append(f"File types: {kinds}.")
    gps, placed, exif = conn.execute(
        "SELECT COALESCE(SUM(gps_lat IS NOT NULL),0), COALESCE(SUM(place IS NOT NULL AND place<>''),0), COALESCE(SUM(taken_exif),0) "
        "FROM items WHERE missing=0 AND meta_done=1"
    ).fetchone()
    lines.append(
        f"Location and dates: {gps:,} photos have GPS, {placed:,} of them have a place name; {exif:,} have a camera date, "
        "the others only a file date."
    )
    first, last = conn.execute("SELECT MIN(taken_at), MAX(taken_at) FROM items WHERE missing=0").fetchone()
    if first and last:
        lines.append(f"Photos span {str(first)[:10]} to {str(last)[:10]}.")
    years = ", ".join(
        f"{r[0]}: {r[1]:,}"
        for r in _rows(
            conn,
            "SELECT substr(taken_at,1,4), COUNT(*) FROM items WHERE missing=0 AND taken_at IS NOT NULL GROUP BY 1 ORDER BY 1 DESC",
        )
    )
    if years:
        lines.append(f"Photos per year: {years}.")
    places = "; ".join(
        f"{r[0]} ({r[1]:,})"
        for r in _rows(
            conn,
            "SELECT place, COUNT(*) FROM items WHERE missing=0 AND place IS NOT NULL AND place<>'' GROUP BY place ORDER BY 2 DESC LIMIT 15",
        )
    )
    if places:
        lines.append(f"Top places: {places}.")
    cameras = "; ".join(
        f"{r[0]} ({r[1]:,})"
        for r in _rows(
            conn,
            "SELECT camera, COUNT(*) FROM items WHERE missing=0 AND camera IS NOT NULL AND camera<>'' GROUP BY camera ORDER BY 2 DESC LIMIT 8",
        )
    )
    if cameras:
        lines.append(f"Cameras: {cameras}.")
    with_gps = conn.execute("SELECT COUNT(*) FROM items WHERE missing=0 AND place IS NOT NULL AND place<>''").fetchone()[0]
    lines.append(f"Photos with a known place: {with_gps:,}.")
    faces, clusters = conn.execute("SELECT COUNT(*), COUNT(DISTINCT person_id) FROM faces").fetchone()
    lines.append(f"Faces found: {faces:,}, grouped into {clusters:,} people.")
    defects = conn.execute("SELECT COUNT(*) FROM flags WHERE status='defect'").fetchone()[0]
    lines.append(f"Photos labelled as defects: {defects:,}.")
    return lines


def _status_facts(conn: sqlite3.Connection, paths: Paths) -> list[str]:
    cov = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(meta_done),0), COALESCE(SUM(clip_done),0), COALESCE(SUM(faces_done),0), "
        "COALESCE(SUM(ocr_done),0) FROM items WHERE missing=0"
    ).fetchone()
    lines = [
        f"Indexing progress: read {cov[1]:,}/{cov[0]:,}; searchable by content {cov[2]:,}; faces done {cov[3]:,}; text reading done {cov[4]:,}."
    ]
    progress = read_progress(paths)
    if ScanLock(paths).running() and progress:
        lines.append(
            f"A scan is running now: stage {progress.get('stage', '?')}, {progress.get('done', 0)}/{progress.get('total', 0)}."
        )
    else:
        lines.append("No scan is running right now.")
    return lines


def _move_facts(conn: sqlite3.Connection) -> list[str]:
    batches = _rows(conn, "SELECT id, label, created, undone FROM move_batches ORDER BY created DESC LIMIT 5")
    if not batches:
        return ["Moves: nothing has been moved yet."]
    lines = ["Recent moves (newest first):"]
    for b in batches:
        counts = {r[0]: r[1] for r in _rows(conn, "SELECT status, COUNT(*) FROM moves WHERE batch=? GROUP BY status", (b["id"],))}
        dst = conn.execute("SELECT dst FROM moves WHERE batch=? LIMIT 1", (b["id"],)).fetchone()
        folder = dst[0].rsplit("/", 1)[0] if dst else "?"
        state = "UNDONE" if b["undone"] else "in place"
        detail = ", ".join(f"{n:,} {s}" for s, n in sorted(counts.items()))
        lines.append(f"- {_when(b['created'])}: {b['label']}; {detail}; destination folder {folder}; {state}.")
    return lines


def _previous_facts(conn: sqlite3.Connection, ids: np.ndarray) -> list[str]:
    ids_list = [int(i) for i in ids]
    lines = [f"The photos from the previous answer: {len(ids_list):,}."]
    rows: list[sqlite3.Row] = []
    for part in chunked(ids_list):
        rows += _rows(conn, f"SELECT path, taken_at, place, camera, kind FROM items WHERE id IN ({in_clause(part)})", part)
    dates = sorted(str(r["taken_at"])[:10] for r in rows if r["taken_at"])
    if dates:
        lines.append(f"They were taken between {dates[0]} and {dates[-1]}.")

    def top(values: list[str], n: int) -> str:
        counts: dict[str, int] = {}
        for v in values:
            counts[v] = counts.get(v, 0) + 1
        return "; ".join(f"{k} ({c:,})" for k, c in sorted(counts.items(), key=lambda kv: -kv[1])[:n])

    for label, values in (
        ("Places", [r["place"] for r in rows if r["place"]]),
        ("Cameras", [r["camera"] for r in rows if r["camera"]]),
        ("Folders", [r["path"].rsplit("/", 1)[0] for r in rows]),
    ):
        if values:
            lines.append(f"{label} among them: {top(values, 5)}.")
    return lines


def gather_facts(conn: sqlite3.Connection, paths: Paths, previous_ids: np.ndarray | None) -> str:
    parts = _library_facts(conn) + _status_facts(conn, paths) + _move_facts(conn)
    if previous_ids is not None and len(previous_ids):
        parts += _previous_facts(conn, previous_ids)
    return "FACTS:\n" + "\n".join(parts)


def answer(complete_text: Callable[[str, str], str], question: str, facts: str) -> str:
    text = complete_text(SYSTEM_PROMPT, f"{facts}\n\nQUESTION: {question.strip()}").strip()
    return text or "I could not work out an answer from what I know about your library."
