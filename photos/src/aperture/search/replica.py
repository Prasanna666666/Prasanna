"""A copy of the facts a question needs, held in memory, so a question never reads the external drive.

Your library file lives on the external drive and reading it there is slow: any query that scans a table costs seconds, and a question makes
many. This keeps the small tables (photos, labels, trips, face counts, people ...) in memory, without the large picture and face vectors, and
refreshes them in the background when the library changes. Tables that are not copied (the text index, the picture vectors) are read from the
drive file as before, through the same connection. If the copy cannot be built, questions simply use the drive file.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path

log = logging.getLogger("aperture.replica")

TABLES = ("items", "faces", "people", "flags", "photo_labels", "photo_events", "captions")
REFRESH_SECONDS = 600.0


class Replica:
    def __init__(self, source: Path) -> None:
        self._source = Path(source)
        self._generation = 0
        self._current: tuple[str, sqlite3.Connection] | None = None  # (uri, the connection that keeps the in-memory copy alive)
        self._built_for: tuple[float, int] | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def _signature(self) -> tuple[float, int] | None:
        import os

        try:
            parts = [os.stat(str(self._source) + suffix) for suffix in ("", "-wal") if os.path.exists(str(self._source) + suffix)]
            return (max(p.st_mtime for p in parts), sum(p.st_size for p in parts)) if parts else None
        except OSError:
            return None

    def build(self) -> bool:
        """Copy the tables into a new in-memory database and switch to it. Returns False (and keeps the old copy) on any problem."""
        with self._lock:
            started = time.monotonic()
            signature = self._signature()
            uri = f"file:lumo_replica_{self._generation + 1}?mode=memory&cache=shared"
            holder = None
            try:
                holder = sqlite3.connect(uri, uri=True, check_same_thread=False, timeout=60)
                holder.execute("ATTACH DATABASE ? AS src", (f"file:{self._source}?mode=ro",))
                rows = 0
                for table in TABLES:
                    info = holder.execute(f"PRAGMA src.table_info({table})").fetchall()
                    if not info:
                        continue
                    columns = [r[1] for r in info if str(r[2]).upper() != "BLOB"]  # the large vectors stay on the drive
                    holder.execute(f"CREATE TABLE main.{table} AS SELECT {', '.join(columns)} FROM src.{table}")
                    rows += holder.execute(f"SELECT COUNT(*) FROM main.{table}").fetchone()[0]
                    for column in (r[1] for r in info if r[5] == 1 and str(r[2]).upper() == "INTEGER" and r[1] in columns):
                        holder.execute(f"CREATE UNIQUE INDEX {table}__pk ON {table}({column})")  # an id lookup must not scan
                    for (sql,) in holder.execute(
                        "SELECT sql FROM src.sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL", (table,)
                    ).fetchall():
                        try:
                            holder.execute(sql)
                        except sqlite3.Error:
                            pass  # an index on a column that was not copied
                holder.commit()
                holder.execute("DETACH DATABASE src")
            except Exception:
                log.exception("could not build the in-memory copy; questions will read the drive file")
                if holder is not None:
                    holder.close()
                return False
            previous = self._current
            self._generation += 1
            self._current = (uri, holder)
            self._built_for = signature
            if previous is not None:
                previous[1].close()  # connections still using the old copy keep working until they close
            log.info("in-memory copy ready: %d rows in %.1f s", rows, time.monotonic() - started)
            return True

    def stale(self) -> bool:
        return self._current is None or self._signature() != self._built_for

    def keep_fresh(self) -> None:
        """Rebuild in the background when the library file has changed (checked every few minutes)."""

        def loop() -> None:
            while True:
                time.sleep(REFRESH_SECONDS)
                if self.stale():
                    self.build()

        threading.Thread(target=loop, name="replica-refresh", daemon=True).start()

    # ------------------------------------------------------------------
    def connect(self) -> sqlite3.Connection | None:
        """A connection to the in-memory copy (with the drive file attached for the tables that are not copied), or None while there is none."""
        current = self._current
        if current is None:
            return None
        conn = sqlite3.connect(current[0], uri=True, check_same_thread=False, timeout=60)
        conn.row_factory = sqlite3.Row
        conn.execute("ATTACH DATABASE ? AS src", (f"file:{self._source}?mode=ro",))
        return conn
