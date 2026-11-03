"""Runs a validated :class:`Plan` against the retrieval engines.

Each clause becomes a *set of photo ids*; clauses are combined with set
algebra (intersection / union / difference).  Because nothing is scored or
weighted, a photo can only appear if it truly satisfies the request.  The
executor also records how many photos each clause matched on its own, so an
empty result can explain exactly which constraint eliminated everything.
"""

from __future__ import annotations

import dataclasses
import difflib
import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

from ..db import chunked, in_clause
from ..ml.protocols import ImageEmbedder
from ..people.repository import named_people, resolve_name
from ..search.dates import resolve
from ..search.embeddings import EmbeddingIndex
from ..search.filters import Filters, apply_filters
from ..search.geo import GeoIndex
from ..search.metadata import all_ids, date_ids, path_ids, place_ids
from ..search.quick import quick_ids
from ..search.text import search_text_ids
from ..search.visual import VisualSearch
from .schema import Clause, Plan

log = logging.getLogger(__name__)


@dataclass
class ClauseReport:
    label: str
    matched: int  # photos this clause matches on its own
    remaining: int  # photos left after applying it
    note: str = ""


@dataclass
class ExecResult:
    ids: np.ndarray  # final result, best first - NEVER truncated
    reports: list[ClauseReport] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    date_range: str = ""
    universe: int = 0


CLOSEST_LIMIT = 200  # how many near matches to return when nothing fits every requirement

FALLBACK_ENGINES = ("place", "path", "text", "visual")  # cheap, exact ones first; people are never guessed


class Executor:
    def __init__(
        self,
        conn: sqlite3.Connection,
        index_provider: Callable[[], EmbeddingIndex],
        embedder_provider: Callable[[], ImageEmbedder | None],
        strictness: str = "balanced",
        today: Callable[[], date] = date.today,
        geo_provider: Callable[[], GeoIndex | None] = lambda: None,
    ) -> None:
        self._conn = conn
        self._index_provider = index_provider
        self._embedder_provider = embedder_provider
        self._strictness = strictness
        self._today = today
        self._geo_provider = geo_provider
        self._visual_scores: dict[int, float] = {}
        self._vocabulary: list[str] | None = None

    # ------------------------------------------------------------------
    def run(self, plan: Plan, previous_ids: np.ndarray | None = None) -> ExecResult:
        """Search, then rank. Criteria are soft: if no photo meets all of them, the closest photos are returned."""
        result = self._run(plan, previous_ids)
        if len(result.ids) == 0 and plan.scope == "previous" and previous_ids is not None and len(previous_ids):
            # "Refine the earlier results" is a preference, not a wall: nothing there, so look in the whole library.
            wider = self._run(dataclasses.replace(plan, scope="library"), None)
            if len(wider.ids):
                wider.notes.insert(0, "Nothing in the earlier results; searched everything.")
                return wider
        return result

    def _run(self, plan: Plan, previous_ids: np.ndarray | None = None) -> ExecResult:
        result = ExecResult(ids=np.zeros(0, np.int64))
        self._visual_scores = {}
        universe = all_ids(self._conn)
        if plan.scope == "previous":
            if previous_ids is not None and len(previous_ids):
                universe = np.intersect1d(universe, previous_ids)
            else:
                result.notes.append("No earlier results; searched everything.")
        result.universe = len(universe)
        self._coverage_note(result)

        if not plan.has_constraints:
            result.notes.append("Nothing to search for was given.")
            return result
        current = universe
        positives = [c for c in plan.clauses if not c.exclude]
        negatives = [c for c in plan.clauses if c.exclude]

        if positives:
            sets: list[tuple[Clause, np.ndarray]] = [(c, self._clause_ids(c, result)) for c in positives]
            if plan.match == "any":
                union = np.unique(np.concatenate([s for _, s in sets])) if sets else np.zeros(0, np.int64)
                current = np.intersect1d(current, union, assume_unique=True)
                for clause, ids in sets:
                    result.reports.append(ClauseReport(clause.label, len(ids), len(current)))
            else:
                for clause, ids in sets:
                    current = np.intersect1d(current, ids, assume_unique=True)
                    result.reports.append(ClauseReport(clause.label, len(ids), len(current)))
        for clause in negatives:
            ids = self._clause_ids(clause, result)
            current = np.setdiff1d(current, ids, assume_unique=True)
            result.reports.append(ClauseReport(clause.label, len(ids), len(current), "excluded"))

        span = resolve(plan.date, self._today())
        if span is not None:
            start, end = span
            ids = date_ids(self._conn, start.isoformat(), end.isoformat())
            current = np.intersect1d(current, ids, assume_unique=True)
            result.date_range = f"{start.isoformat()} to {(end - timedelta(days=1)).isoformat()}"
            result.reports.append(ClauseReport(f"date {result.date_range}", len(ids), len(current)))
        elif not plan.date.is_empty:
            result.notes.append("I could not understand the date, so I ignored it.")

        if not plan.filters.is_empty:
            ids, notes = apply_filters(self._conn, plan.filters, self._geo_provider())
            current = np.intersect1d(current, ids, assume_unique=True)
            result.notes.extend(n for n in notes if n not in result.notes)
            result.reports.append(ClauseReport(f"filters: {plan.filters.describe()}", len(ids), len(current)))

        result.ids = self._rank(current)
        return result

    def _clause_ids(self, clause: Clause, result: ExecResult) -> np.ndarray:
        parts = [self._engine_ids(engine, clause.query, result) for engine in clause.engines]
        ids = np.unique(np.concatenate(parts)) if parts else np.zeros(0, np.int64)
        if len(ids) or not clause.query.strip():
            return ids
        if "place" in clause.engines:
            # No photo is labelled with that name, but the photos' GPS may still be there (Tokyo photos are labelled with a district).
            nearby = self._near_ids(clause.query, result)
            if len(nearby):
                return nearby
        # The model may have looked in the wrong place (a city searched by what photos show).
        # Before declaring this clause empty, try the engines it did not use.
        for engine in FALLBACK_ENGINES:
            if engine in clause.engines:
                continue
            found = self._engine_ids(engine, clause.query, result)
            if len(found):
                result.notes.append(
                    f"'{clause.query}': found by {engine} instead."
                )
                return found
        near = self._similar_place_ids(clause.query, result)
        return near if len(near) else ids

    def _near_ids(self, query: str, result: ExecResult) -> np.ndarray:
        """Photos whose GPS lies within 25 km of the named place (offline place list)."""
        geo = self._geo_provider()
        if geo is None or not query.strip():
            return np.zeros(0, np.int64)
        try:
            ids, notes = apply_filters(self._conn, Filters(near=query), geo)
        except sqlite3.Error:
            return np.zeros(0, np.int64)
        if len(ids):
            result.notes.append(f"{len(ids):,} taken within 25 km of {query} (GPS).")
        return ids

    def readings(self, plan: Plan) -> list[tuple[str, np.ndarray]]:
        """Every way the search words could be meant, each searched on its own: labelled place, GPS near it, folder or file name,
        a person, words in the photo, how it looks, plus the date. The AI chose the words; this lists what each meaning finds."""
        scratch = ExecResult(ids=np.zeros(0, np.int64))
        universe = all_ids(self._conn)
        limit = max(50, int(0.2 * len(universe)))  # a meaning that matches a fifth of the library says nothing
        found: list[tuple[str, np.ndarray]] = []
        terms = list(dict.fromkeys(c.query.strip() for c in plan.clauses if not c.exclude and c.query.strip()))
        for term in terms:
            wording = (
                ("place", f"Labelled with the place '{term}'"),
                ("near", f"Taken near {term} (GPS)"),
                ("path", f"In a folder or file named '{term}'"),
                ("person", f"Photos of {term}"),
                ("text", f"With '{term}' written in them"),
                ("tag", f"Tagged '{term}'"),
                ("visual", f"Looks like '{term}'"),
            )
            for engine, label in wording:
                ids = self._near_ids(term, scratch) if engine == "near" else self._engine_ids(engine, term, scratch)
                if 0 < len(ids) <= limit:
                    found.append((label, np.sort(ids)))
        for term in terms:  # a trip: everything shot around the same time as the photos this word finds directly
            anchors = [ids for label, ids in found if f"'{term}'" in label or term in label]
            trip = self._trip_ids(np.unique(np.concatenate(anchors))) if anchors else np.zeros(0, np.int64)
            if 0 < len(trip) <= limit:
                found.append((f"Same trip or event as the '{term}' photos", np.sort(trip)))
        span = resolve(plan.date, self._today()) if not plan.date.is_empty else None
        if span is not None:
            ids = date_ids(self._conn, span[0].isoformat(), span[1].isoformat())
            if len(ids):
                found.append((f"Taken {span[0].isoformat()} to {(span[1] - timedelta(days=1)).isoformat()}", np.sort(ids)))
        banned = [self._clause_ids(c, scratch) for c in plan.clauses if c.exclude]  # what the user said they do not want stays out
        allowed = apply_filters(self._conn, plan.filters, self._geo_provider())[0] if not plan.filters.is_empty else None
        kept: list[tuple[str, np.ndarray]] = []
        for label, ids in found:
            for gone in banned:
                ids = np.setdiff1d(ids, gone)
            if allowed is not None:
                ids = np.intersect1d(ids, allowed)
            if len(ids):
                kept.append((label, ids))
        return kept

    def _place_vocabulary(self) -> list[str]:
        if self._vocabulary is None:
            words: set[str] = set()
            for (text,) in self._conn.execute("SELECT DISTINCT place_text FROM items WHERE missing=0 AND place_text IS NOT NULL"):
                words.update(w for w in text.split() if len(w) >= 5)
            self._vocabulary = sorted(words)
        return self._vocabulary

    def _similar_place_ids(self, query: str, result: ExecResult) -> np.ndarray:
        """A place spelled differently from the library's (Bangalore / Bengaluru, Zurich / Zürich)."""
        found: list[np.ndarray] = []
        for word in dict.fromkeys(w for w in query.lower().split() if len(w) >= 5):
            close = difflib.get_close_matches(word, self._place_vocabulary(), n=1, cutoff=0.66)
            if close:
                ids = place_ids(self._conn, close[0])
                if len(ids):
                    found.append(ids)
                    result.notes.append(f"'{word}' read as {close[0]}.")
        return np.unique(np.concatenate(found)) if found else np.zeros(0, np.int64)

    def rescue(self, request: str) -> np.ndarray:
        """Last resort when a plan finds nothing: match the request's own words against the library's data."""
        return quick_ids(self._conn, request, self._index_provider, self._embedder_provider, self._strictness)

    def _engine_ids(self, engine: str, query: str, result: ExecResult) -> np.ndarray:
        try:
            if engine == "text":
                return np.unique(search_text_ids(self._conn, query))
            if engine == "path":
                return path_ids(self._conn, query)
            if engine == "place":
                return place_ids(self._conn, query)
            if engine == "person":
                return self._person_ids(query, result)
            if engine == "visual":
                return self._visual_ids(query, result)
            if engine == "tag":
                return self._tag_ids(query)
        except sqlite3.Error as exc:  # a broken engine must not take the whole answer down
            log.exception("engine %s failed", engine)
            result.notes.append(f"The {engine} search failed: {exc}")
        return np.zeros(0, np.int64)

    def _trip_ids(self, anchors: np.ndarray) -> np.ndarray:
        """All photos of the trips/events that contain any of these photos (see `aperture scan`, which builds the events)."""
        if len(anchors) == 0:
            return np.zeros(0, np.int64)
        try:
            events: set[int] = set()
            for part in chunked(anchors.tolist(), 500):
                marks = ",".join("?" * len(part))
                events.update(r[0] for r in self._conn.execute(f"SELECT DISTINCT event_id FROM photo_events WHERE item_id IN ({marks})", part))
            ids: list[int] = []
            for part in chunked(sorted(events), 500):
                marks = ",".join("?" * len(part))
                ids += [r[0] for r in self._conn.execute(f"SELECT item_id FROM photo_events WHERE event_id IN ({marks})", part)]
            return np.array(sorted(set(ids)), np.int64)
        except sqlite3.Error:
            return np.zeros(0, np.int64)  # the events have not been built yet

    def _tag_ids(self, query: str) -> np.ndarray:
        """Photos labelled with this scene, object or landmark (read once from the picture; see `aperture details`)."""
        word = query.strip().lower()
        if len(word) < 2:
            return np.zeros(0, np.int64)
        try:
            rows = self._conn.execute(
                "SELECT DISTINCT item_id FROM photo_labels WHERE label=? OR label LIKE ? ESCAPE '\\'", (word, f"%{word.replace('%', '').replace('_', '')}%")
            )
            return np.array(sorted(r[0] for r in rows), np.int64)
        except sqlite3.Error:
            return np.zeros(0, np.int64)  # the details pass has not run yet

    def _person_ids(self, query: str, result: ExecResult) -> np.ndarray:
        person_ids = resolve_name(self._conn, query)
        if not person_ids:
            known = ", ".join(n for _, n in named_people(self._conn, 8)) or "none yet - name people in the People page"
            result.notes.append(f"I don't know anyone called '{query}'. Known people: {known}.")
            return np.zeros(0, np.int64)
        marks = in_clause(person_ids)
        rows = self._conn.execute(f"SELECT DISTINCT item_id FROM faces WHERE person_id IN ({marks})", person_ids)
        return np.array(sorted(r[0] for r in rows), np.int64)

    def _visual_ids(self, query: str, result: ExecResult) -> np.ndarray:
        index, embedder = self._index_provider(), self._embedder_provider()
        if embedder is None or len(index) == 0:
            result.notes.append("The visual index is not ready yet (CLIP embeddings are still being built).")
            return np.zeros(0, np.int64)
        hits = VisualSearch(index, embedder, self._strictness).search(query)
        for item_id, score in zip(hits.ids.tolist(), hits.scores.tolist(), strict=True):
            self._visual_scores[item_id] = max(score, self._visual_scores.get(item_id, -1.0))
        if len(hits.ids) == 0:
            result.notes.append(f"Nothing in the library looks like '{query}' (closest similarity {hits.best_cosine:.2f}).")
        return np.sort(hits.ids)

    def _coverage_note(self, result: ExecResult) -> None:
        """Only mention photos that are really still waiting. Files that failed to index (unreadable, unsupported) are flagged as
        errors and will never be indexed: counting them would keep this note on screen forever, even when indexing is finished."""
        total, pending = self._conn.execute(
            "SELECT COUNT(*), SUM(meta_done=0 AND error IS NULL) FROM items WHERE missing=0"
        ).fetchone()
        if total and (pending or 0) > 0:
            result.notes.append(f"{pending:,} of {total:,} photos not indexed yet.")

    def _rank(self, ids: np.ndarray) -> np.ndarray:
        """Best visual match first, otherwise newest first.  Never drops an id."""
        if len(ids) == 0:
            return ids
        if self._visual_scores:
            scores = np.array([self._visual_scores.get(int(i), -1.0) for i in ids])
            return ids[np.argsort(-scores, kind="stable")]
        return sort_ids(self._conn, ids, "newest")


def sort_ids(conn: sqlite3.Connection, ids: np.ndarray, mode: str) -> np.ndarray:
    """Re-order ids by capture date (``newest`` / ``oldest``); other modes keep order."""
    if mode not in ("newest", "oldest") or len(ids) == 0:
        return ids
    dates: dict[int, str] = {}
    id_list = [int(i) for i in ids]
    for part in chunked(id_list):
        for row in conn.execute(f"SELECT id, COALESCE(taken_at, '') AS t FROM items WHERE id IN ({in_clause(part)})", part):
            dates[row["id"]] = row["t"]
    order = sorted(id_list, key=lambda i: (dates.get(i, ""), i), reverse=(mode == "newest"))
    return np.array(order, np.int64)
