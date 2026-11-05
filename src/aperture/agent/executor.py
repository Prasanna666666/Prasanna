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
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import numpy as np

from ..db import chunked, in_clause
from ..ml.protocols import ImageEmbedder
from ..people.repository import named_people, resolve_name
from ..search.dates import resolve
from ..search.embeddings import EmbeddingIndex
from ..search.filters import Filters, apply_filters
from ..search.geo import GeoIndex
from ..search.metadata import all_ids, date_ids, path_ids, place_ids, remembered
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
    hard: Any = (
        None  # photos that satisfy every exact requirement (place, date, person, written text), before looks are considered
    )


CLOSEST_LIMIT = 200  # how many near matches to return when nothing fits every requirement


@dataclass
class Exploration:
    """Every reading of the request's words, plus the best evidence for each condition on its own."""

    readings: list[tuple[str, np.ndarray]]
    terms: dict[str, np.ndarray]  # each word: the photos that have good evidence for it
    when: np.ndarray | None = None  # the photos in the requested time, if a time was asked for

    def together(self) -> np.ndarray | None:
        """The photos where EVERY condition holds at once (each condition judged by its own best evidence). None for a single condition."""
        sets = [*self.terms.values(), *([self.when] if self.when is not None else [])]
        if len(sets) < 2:
            return None
        both = sets[0]
        for other in sets[1:]:
            both = np.intersect1d(both, other)
        return both


EXPLORE_SECONDS = 10.0  # listing the other readings may never take longer than this
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
                result.notes.append(f"'{clause.query}': found by {engine} instead.")
                return found
        near = self._similar_place_ids(clause.query, result)
        return near if len(near) else ids

    def _near_ids(self, query: str, result: ExecResult) -> np.ndarray:
        """Photos whose GPS lies within 25 km of the named place (offline place list)."""
        geo = self._geo_provider()
        if geo is None or not query.strip():
            return np.zeros(0, np.int64)
        try:
            ids, _notes = apply_filters(self._conn, Filters(near=query), geo)
        except sqlite3.Error:
            return np.zeros(0, np.int64)
        if len(ids):
            result.notes.append(f"{len(ids):,} taken within 25 km of {query} (GPS).")
        return ids

    def run_relaxed(self, plan: Plan, previous_ids: np.ndarray | None = None, keep: int = 60) -> ExecResult:
        """When nothing satisfies everything: keep every EXACT requirement (place, date, person, written text, filters), drop only what a
        picture should look like, and rank the photos that remain by how close they come. A place, date or person is never dropped."""
        soft = [c for c in plan.clauses if not c.exclude and tuple(c.engines) == ("visual",)]
        hard_plan = dataclasses.replace(plan, clauses=tuple(c for c in plan.clauses if c not in soft))
        if not soft or not (hard_plan.clauses or not hard_plan.date.is_empty or not hard_plan.filters.is_empty):
            return ExecResult(ids=np.zeros(0, np.int64))
        result = self._run(hard_plan, previous_ids)
        result.hard = result.ids
        if len(result.ids) == 0:
            return result
        result.ids = self._closest_in_look(result.ids, [c.query for c in soft], keep)
        return result

    def _closest_in_look(self, ids: np.ndarray, queries: list[str], keep: int) -> np.ndarray:
        index, embedder = self._index_provider(), self._embedder_provider()
        if embedder is None or len(index) == 0:
            return ids[:keep]
        search = VisualSearch(index, embedder, self._strictness)
        rows = np.searchsorted(index.ids, ids)
        rows = np.clip(rows, 0, len(index) - 1)
        known = index.ids[rows] == ids  # photos without an embedding cannot be ranked
        if not known.any():
            return ids[:keep]
        vectors = index.vectors[rows[known]].astype(np.float32)
        score = sum(vectors @ search.query_vector(q) for q in queries)
        return ids[known][np.argsort(-score)][:keep]

    HARD = (
        "place",
        "near",
        "estimated",
        "path",
        "person",
    )  # facts: the photo's own GPS, place tag, folder name, or a named person
    SOFT = ("text", "tag", "visual")  # clues: a word that appears in the picture, or what the picture looks like

    def explore(self, plan: Plan) -> Exploration:
        """Every way the search words could be meant, each searched on its own and then VALIDATED against everything stored about the
        photos: a photo is kept only if it has hard evidence (its GPS, place tag, folder or a named person) or at least two independent
        clues agree. Single weak clues (one word in a receipt, one look-alike guess) are dropped. Then the trip of the confirmed photos."""
        scratch = ExecResult(ids=np.zeros(0, np.int64))
        until = time.monotonic() + EXPLORE_SECONDS
        universe = all_ids(self._conn)
        limit = max(50, int(0.2 * len(universe)))  # a meaning that matches a fifth of the library says nothing
        found: list[tuple[str, np.ndarray]] = []
        term_sets: dict[str, np.ndarray] = {}
        terms = list(dict.fromkeys(c.query.strip() for c in plan.clauses if not c.exclude and c.query.strip()))
        for term in terms:
            wording = (
                ("place", f"Taken in {term}"),
                ("near", f"Taken near {term}"),
                ("estimated", f"Probably taken in {term}"),
                ("path", f"In folders named {term}"),
                ("person", f"People called {term}"),
                ("tag", f"Looks like {term}"),
                ("text", f"The word {term} in the photo"),
                ("visual", f"Similar to {term}"),
            )
            readings: list[tuple[str, str, np.ndarray]] = []
            identified = False  # found by hard evidence: guesses from appearance would only add noise
            for engine, label in wording:
                if identified and engine in ("tag", "visual"):
                    continue
                if time.monotonic() > until:  # a hard stop: whatever was found so far is the answer
                    scratch.notes.append("Some ways of matching were skipped to keep this fast.")
                    break
                ids = self._near_ids(term, scratch) if engine == "near" else self._engine_ids(engine, term, scratch)
                if engine == "visual" and len(ids):
                    ids = np.intersect1d(
                        ids, self._vision_agrees(term)
                    )  # a guess from appearance counts only if Apple Vision agrees
                if 0 < len(ids) <= limit:
                    readings.append((engine, label, np.sort(ids)))
                    identified = identified or engine in self.HARD
            hard_found = [(engine, ids) for engine, _, ids in readings if engine in self.HARD]
            if len(hard_found) >= 2:
                # Several hard facts point at the same word (the place name, GPS nearby, a folder...): one combined answer, not separate tabs.
                # Photos near a city are often named after a smaller neighbouring town, so the place name alone misses them.
                union = np.unique(np.concatenate([ids for _, ids in hard_found]))
                readings = [("place", f"Taken in or near {term}", union)] + [r for r in readings if r[0] not in self.HARD]
            hard = [ids for engine, _, ids in readings if engine in self.HARD]
            confirmed = np.unique(np.concatenate(hard)) if hard else np.zeros(0, np.int64)
            soft = [(label, ids) for engine, label, ids in readings if engine in self.SOFT]
            support: dict[int, int] = {}
            for _, ids in soft:
                for i in ids.tolist():
                    support[i] = support.get(i, 0) + 1
            agreed = np.array(sorted(i for i, n in support.items() if n >= 2), np.int64)  # two independent clues agree
            if len(agreed):
                confirmed = np.union1d(confirmed, agreed)
            for engine, _, ids in readings:
                if (
                    engine == "tag"
                ):  # a picture label that is already strong, or backed by two sources, is evidence in its own right
                    confirmed = np.union1d(confirmed, ids)
            term_sets[term] = confirmed
            for engine, label, ids in readings:
                if engine in self.SOFT:
                    ids = np.intersect1d(ids, confirmed)  # a clue counts only where hard evidence or a second clue backs it
                if len(ids):
                    found.append((label, ids))
            placed = any(
                engine in ("place", "near", "estimated") for engine, _, _ in readings
            )  # a trip only means something for a PLACE, never for 'baby'
            trip = (
                self._trip_ids(confirmed) if len(confirmed) and len(terms) == 1 and placed else np.zeros(0, np.int64)
            )  # one condition only: with several it just confuses
            if 0 < len(trip) <= limit:
                found.append((f"Same trip as your {term} photos", np.sort(trip)))
        span = resolve(plan.date, self._today()) if not plan.date.is_empty else None
        when: np.ndarray | None = None
        if span is not None:
            ids = date_ids(self._conn, span[0].isoformat(), span[1].isoformat())
            when = np.sort(ids)
            if len(ids):
                found.append((f"Taken {span[0].isoformat()} to {(span[1] - timedelta(days=1)).isoformat()}", np.sort(ids)))
        subject = next((c.query.strip() for c in plan.clauses if not c.exclude and tuple(c.engines) == ("visual",)), "")
        if plan.meanings and subject in term_sets:
            # The subject has no label of its own (no folder or caption says "hockey"). Where the OTHER conditions already pin the photos down
            # (the place, the time), look at what the pictures show, using the cloud's plain descriptions of how it would look.
            fixed = [ids for term, ids in term_sets.items() if term != subject]
            if when is not None:
                fixed.append(when)
            if fixed:
                region = fixed[0]
                for other in fixed[1:]:
                    region = np.intersect1d(region, other)
                if len(region):
                    seen = [np.intersect1d(self._visual_ids(m, scratch), region) for m in plan.meanings]
                    looks = np.unique(np.concatenate(seen)) if seen else np.zeros(0, np.int64)
                    if len(looks):
                        term_sets[subject] = np.union1d(term_sets[subject], looks)
        banned = [
            self._clause_ids(c, scratch) for c in plan.clauses if c.exclude
        ]  # what the user said they do not want stays out
        allowed = apply_filters(self._conn, plan.filters, self._geo_provider())[0] if not plan.filters.is_empty else None
        kept: list[tuple[str, np.ndarray]] = []
        for label, ids in found:
            for gone in banned:
                ids = np.setdiff1d(ids, gone)
            if allowed is not None:
                ids = np.intersect1d(ids, allowed)
            if len(ids):
                kept.append((label, ids))
        for term, ids in list(term_sets.items()):  # what the person excluded, and the exact filters, apply to every condition
            for gone in banned:
                ids = np.setdiff1d(ids, gone)
            if allowed is not None:
                ids = np.intersect1d(ids, allowed)
            term_sets[term] = ids
        return Exploration(kept, term_sets, when)

    def readings(self, plan: Plan) -> list[tuple[str, np.ndarray]]:
        return self.explore(plan).readings

    def _place_vocabulary(self) -> list[str]:
        if self._vocabulary is None:

            def build() -> list[str]:
                words: set[str] = set()
                for (text,) in self._conn.execute(
                    "SELECT DISTINCT place_text FROM items WHERE missing=0 AND place_text IS NOT NULL"
                ):
                    words.update(w for w in text.split() if len(w) >= 5)
                return sorted(words)

            self._vocabulary = remembered(self._conn, "place_vocabulary", build)
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
            if engine == "estimated":
                return self._estimated_ids(query)
        except sqlite3.Error as exc:  # a broken engine must not take the whole answer down
            log.exception("engine %s failed", engine)
            result.notes.append(f"The {engine} search failed: {exc}")
        return np.zeros(0, np.int64)

    def _estimated_ids(self, query: str) -> np.ndarray:
        """Photos with no GPS of their own, located from the photos around them in time (kept only where that tested >= 80% accurate)."""
        from ..search.metadata import estimated_place_ids

        try:
            ids = estimated_place_ids(self._conn, query)
            geo = self._geo_provider()
            found = geo.find(query) if geo is not None else None
            if found is not None:
                rows = remembered(
                    self._conn,
                    "estimated_positions",
                    lambda: self._conn.execute(
                        "SELECT id, gps_est_lat, gps_est_lon FROM items WHERE missing=0 AND gps_est_lat IS NOT NULL"
                    ).fetchall(),
                )
                if rows:
                    from ..search.filters import haversine_km

                    near = np.array([r[0] for r in rows], np.int64)
                    dist = haversine_km(found[0], found[1], np.array([r[1] for r in rows]), np.array([r[2] for r in rows]))
                    ids = np.union1d(ids, near[dist <= 25])
            return ids
        except sqlite3.Error:
            return np.zeros(0, np.int64)

    def _same_trip_without_gps(self, anchors: np.ndarray) -> np.ndarray:
        """Photos that carry no GPS (screenshots, forwarded or location-off shots) but were taken during the trip of the given photos."""
        trip = self._trip_ids(anchors)
        if len(trip) == 0:
            return trip
        try:
            keep: list[int] = []
            for part in chunked(trip.tolist(), 500):
                marks = ",".join("?" * len(part))
                keep += [
                    r[0] for r in self._conn.execute(f"SELECT id FROM items WHERE gps_lat IS NULL AND id IN ({marks})", part)
                ]
            return np.array(sorted(keep), np.int64)
        except sqlite3.Error:
            return np.zeros(0, np.int64)

    def _trip_ids(self, anchors: np.ndarray) -> np.ndarray:
        """All photos of the trips/events that contain any of these photos (see `aperture scan`, which builds the events), except any photo
        whose own location (GPS or estimated) is far from where the anchors are: a trip never reaches another country."""
        if len(anchors) == 0:
            return np.zeros(0, np.int64)
        try:
            ids = self._trip_ids_unfiltered(anchors)
            return self._same_camera_as_the_located(self._near_the_anchors(ids, anchors), anchors)
        except sqlite3.Error:
            return np.zeros(0, np.int64)

    def _same_camera_as_the_located(self, ids: np.ndarray, anchors: np.ndarray) -> np.ndarray:
        """A photo with no location of its own joins a trip only if its camera also took located photos of that trip: a camera that never
        records GPS may have a wrong clock, and its photos would land in trips they were not part of. A location the app only worked out
        does not prove a clock, so only a camera's own GPS counts."""
        if len(ids) == 0:
            return ids
        cameras: set[str] = set()
        for part in chunked(anchors.tolist(), 500):
            marks = ",".join("?" * len(part))
            cameras.update(
                r[0] or ""
                for r in self._conn.execute(
                    f"SELECT DISTINCT camera FROM items WHERE id IN ({marks}) AND gps_lat IS NOT NULL", part
                )
            )  # the camera's OWN GPS, never an estimate
        if not cameras:
            return ids  # nothing is located, so there is no camera to compare with
        drop: list[int] = []
        for part in chunked(ids.tolist(), 500):
            marks = ",".join("?" * len(part))
            for item_id, camera in self._conn.execute(
                f"SELECT id, COALESCE(camera, '') FROM items WHERE id IN ({marks}) AND COALESCE(gps_lat, gps_est_lat) IS NULL",
                part,
            ):
                if camera not in cameras:
                    drop.append(item_id)
        return np.setdiff1d(ids, np.array(drop, np.int64))

    def _near_the_anchors(self, ids: np.ndarray, anchors: np.ndarray, km: float = 300.0) -> np.ndarray:
        from ..search.filters import haversine_km

        def positions(of: np.ndarray) -> np.ndarray:
            out = []
            for part in chunked(of.tolist(), 500):
                marks = ",".join("?" * len(part))
                out += [
                    tuple(r)
                    for r in self._conn.execute(
                        f"SELECT id, COALESCE(gps_lat, gps_est_lat), COALESCE(gps_lon, gps_est_lon) FROM items WHERE id IN ({marks}) AND COALESCE(gps_lat, gps_est_lat) IS NOT NULL",
                        part,
                    )
                ]
            return np.array(out, float).reshape(-1, 3)

        known = positions(anchors)
        if len(known) == 0 or len(ids) == 0:
            return ids
        centre = (float(np.median(known[:, 1])), float(np.median(known[:, 2])))
        there = positions(ids)
        far = (
            there[haversine_km(centre[0], centre[1], there[:, 1], there[:, 2]) > km][:, 0].astype(np.int64)
            if len(there)
            else np.zeros(0, np.int64)
        )
        return np.setdiff1d(ids, far)

    def _trip_ids_unfiltered(self, anchors: np.ndarray) -> np.ndarray:
        try:
            events: set[int] = set()
            for part in chunked(anchors.tolist(), 500):
                marks = ",".join("?" * len(part))
                events.update(
                    r[0]
                    for r in self._conn.execute(f"SELECT DISTINCT event_id FROM photo_events WHERE item_id IN ({marks})", part)
                )
            ids: list[int] = []
            for part in chunked(sorted(events), 500):
                marks = ",".join("?" * len(part))
                ids += [r[0] for r in self._conn.execute(f"SELECT item_id FROM photo_events WHERE event_id IN ({marks})", part)]
            return np.array(sorted(set(ids)), np.int64)
        except sqlite3.Error:
            return np.zeros(0, np.int64)  # the events have not been built yet

    def _vision_agrees(self, term: str) -> np.ndarray:
        """Photos whose Apple Vision labels share a word with the term (confident labels only)."""
        from ..search.textnorm import tokens

        words = [w for w in tokens(term) if len(w) >= 3]
        if not words:
            return np.zeros(0, np.int64)
        try:
            names = sorted(
                {form for w in words for form in (w, w + "s", w.rstrip("s"))}
            )  # exact labels, so the label index is used (a '%word%' scan read every label)
            marks = ",".join("?" * len(names))
            rows = self._conn.execute(
                f"SELECT DISTINCT item_id FROM photo_labels WHERE label IN ({marks}) AND source='vision' AND score>=0.5", names
            )
            return np.array(sorted(r[0] for r in rows), np.int64)
        except sqlite3.Error:
            return np.zeros(0, np.int64)

    def _tag_ids(self, query: str) -> np.ndarray:
        """Photos labelled with this scene, object or landmark (read once from the picture; see `aperture details`)."""
        word = query.strip().lower()
        if len(word) < 2:
            return np.zeros(0, np.int64)
        try:
            # The exact label, never a part of one. Trusted when strong on its own (>= 0.8) or when two different sources agree (>= 0.5 each),
            # for example the face reader and Apple Vision both seeing a baby.
            rows = self._conn.execute(
                "SELECT item_id FROM photo_labels WHERE label=? AND score>=0.5 GROUP BY item_id "
                "HAVING MAX(score) >= 0.8 OR COUNT(DISTINCT source) >= 2",
                (word,),
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
        embedder = (
            self._embedder_provider()
        )  # first, and never waited for: loading the library's picture index from the drive is slow too
        index = self._index_provider() if embedder is not None else None
        if embedder is None or index is None or len(index) == 0:
            result.notes.append("Picture search is still starting up, so this answer does not use how the photos look yet.")
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
        total, pending = remembered(
            self._conn,
            "coverage",
            lambda: tuple(
                self._conn.execute("SELECT COUNT(*), SUM(meta_done=0 AND error IS NULL) FROM items WHERE missing=0").fetchone()
            ),
        )
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
