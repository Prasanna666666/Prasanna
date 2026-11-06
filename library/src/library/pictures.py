"""Pictures: the shared picture engine (`images`), run for every picture Documents is given.

One indexer (a sealed container with no network, see indexer.py) reads the photo folder: dates, places, text in the pictures, faces, labels and CLIP.
The service answers questions from that index: search, thumbnails, and the text found in pictures, which joins the documents' text in one search.
Other apps that show pictures (Photos) open the same index and ask this service to update it, so a picture is read once, in one place.

Without `LIBRARY_PICTURES_DRIVE` set, none of this runs.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from images.config import Paths, thumb_rel
from images.engine import Engine
from images.indexing.runner import ScanSummary
from images.library import items_by_ids
from images.search.quick import quick_ids

Progress = Callable[[str], None]
WAKE, STATUS = "pictures-scan.wake", "pictures-scan.status.json"
MAX_RESULTS = 60


def drive() -> Path | None:
    value = os.environ.get("LIBRARY_PICTURES_DRIVE", "")
    return Path(value) if value else None


def configured() -> bool:
    return drive() is not None


def build_engine(root: Path | None = None) -> Engine:
    """The engine over the drive that holds the photos and the index. The photo folder is `LIBRARY_PHOTOS`, or `<drive>/Photos`."""
    paths = Paths(drive=root or drive() or Path("/nonexistent"))
    engine = Engine(paths)
    folder = os.environ.get("LIBRARY_PHOTOS", "")
    if folder and engine.settings.photo_dir != folder:
        engine.settings.photo_dir = folder
        engine.settings.save(paths)
    return engine


def _control(engine: Engine) -> Path:
    folder = engine.paths.data / "control"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


# ---- the indexer and the service talk through two small files (the indexer has no network) -------------------------------------
def request_scan(engine: Engine) -> None:
    (_control(engine) / WAKE).touch()


def scan_state(engine: Engine) -> dict[str, Any]:
    """{running, progress, summary} as the indexer last wrote it."""
    try:
        state = json.loads((_control(engine) / STATUS).read_text())
    except (OSError, ValueError):
        return {"running": False, "progress": "", "summary": ""}
    return state if isinstance(state, dict) else {"running": False, "progress": "", "summary": ""}


def write_state(engine: Engine, running: bool, progress: str = "", summary: str = "") -> None:
    target = _control(engine) / STATUS
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps({"running": running, "progress": progress, "summary": summary, "at": time.time()}))
    os.replace(tmp, target)


def summarise(engine: Engine, done: ScanSummary) -> str:
    c = counts(engine)
    return f"{c['indexed']:,} of {c['pictures']:,} pictures read" + (f", {done.errors} could not be read" if done.errors else "")


def wait_for_scan(engine: Engine, progress: Progress, poll: float = 2.0, appear: float = 6.0) -> str:
    """Ask the indexer to read what is new and wait until it has finished. Returns what it did."""
    request_scan(engine)
    deadline = time.monotonic() + appear
    seen = False
    while True:
        state = scan_state(engine)
        if state.get("running"):
            seen = True
            progress(str(state.get("progress") or "Reading pictures…"))
        elif seen or time.monotonic() > deadline:
            return str(state.get("summary") or "")
        time.sleep(poll)


# ---- asking ----------------------------------------------------------------------------------------------------------------------
def search(engine: Engine, text: str, limit: int = 24) -> list[dict[str, Any]]:
    """Pictures that fit the words, best first: by words in the text/place/name, otherwise by what the picture looks like."""
    conn = engine.db.connect()
    try:
        ids = [int(i) for i in quick_ids(conn, text, engine.embedding_index, engine.search_embedder)[: min(limit, MAX_RESULTS)]]
        found = items_by_ids(conn, ids)
    finally:
        conn.close()
    return [
        {
            "id": i,
            "name": Path(found[i].rel_path or found[i].path).name,
            "taken": found[i].taken_at,
            "place": found[i].place,
            "thumb": f"/api/pictures/thumb/{i}",
        }
        for i in ids
        if i in found
    ]


def thumb_file(engine: Engine, item_id: int) -> Path | None:
    data = engine.paths.data.resolve()
    path = (data / thumb_rel(int(item_id))).resolve()
    return path if data in path.parents and path.is_file() else None


def counts(engine: Engine) -> dict[str, int]:
    conn = engine.db.connect()
    try:
        row = conn.execute("SELECT COUNT(*) AS n, SUM(meta_done=1) AS indexed FROM items WHERE missing=0").fetchone()
    finally:
        conn.close()
    return {"pictures": int(row["n"] or 0), "indexed": int(row["indexed"] or 0)}


def text_sources(engine: Engine) -> Callable[[Any], Iterator[tuple[str, str, str, str]]]:
    """The text found in pictures (signs, receipts, letters, labels), as sources for the one search that also covers the documents."""

    def sources(_documents_conn: Any) -> Iterator[tuple[str, str, str, str]]:
        conn = engine.db.connect()
        try:
            for r in conn.execute("SELECT i.id, i.rel_path, f.text FROM items i JOIN fts f ON f.rowid=i.id WHERE i.missing=0 AND length(f.text) > 20"):
                yield f"p{r['id']}", "picture", r["rel_path"] or str(r["id"]), r["text"]
        finally:
            conn.close()

    return sources


def in_window(engine: Engine, start: str, end: str, limit: int = 24) -> list[dict[str, Any]]:
    """Pictures taken within the window (inclusive), oldest first."""
    conn = engine.db.connect()
    try:
        ids = [
            int(r[0])
            for r in conn.execute(
                "SELECT id FROM items WHERE missing=0 AND kind='image' AND substr(taken_at,1,10) BETWEEN ? AND ? ORDER BY taken_at, id LIMIT ?",
                (start, end, min(limit, MAX_RESULTS)),
            )
        ]
        found = items_by_ids(conn, ids)
    finally:
        conn.close()
    return [
        {
            "id": i,
            "name": Path(found[i].rel_path or found[i].path).name,
            "taken": found[i].taken_at,
            "place": found[i].place,
            "thumb": f"/api/pictures/thumb/{i}",
        }
        for i in ids
        if i in found
    ]
