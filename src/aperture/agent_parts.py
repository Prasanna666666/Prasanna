"""The pieces the photo agent is built from: how it finds people and places, reads text, looks at photos and writes its answers.

Each method is one capability handed to the agent as a plain function. They live here, not inside `AppContext.agent`, so each can be read, tested and changed on its own."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

import numpy as np

from . import library as lib
from .agent.captions import describe_item
from .agent.executor import Executor
from .agent.jsonutil import extract_json
from .agent.knowledge import answer as answer_question
from .agent.knowledge import gather_facts
from .agent.llm import LLMError
from .agent.service import CHAT_MAX_TOKENS, CHAT_SYSTEM, DATE_SCHEMA, DATE_SYSTEM
from .agent.toolagent import close_matches
from .people.repository import named_people, resolve_name
from .search.quick import probe

if TYPE_CHECKING:
    from .bootstrap import AppContext

MAX_PHOTOS_TO_LOOK_AT = 3  # vision is slow: only look when the question concerns a few photos


class AgentParts:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

    def make_executor(self) -> Executor:
        return Executor(
            self.ctx.question_db(),
            self.ctx.embedding_index,
            self.ctx.ready_embedder,
            strictness=self.ctx.settings.visual_strictness,
            geo_provider=self.ctx.ready_geo,
        )

    def people_names(self) -> list[str]:
        def load() -> list[str]:
            conn = self.ctx.db.connect()
            try:
                return [name for _, name in named_people(conn)]
            finally:
                conn.close()

        return self.ctx.memo("people", 60.0, load)

    def library_facts(self, request: str) -> str:
        def static_facts() -> tuple[list[str], str | None, str | None]:  # two table scans: the same for every request
            scan = self.ctx.db.connect()
            try:
                found = [
                    r[0]
                    for r in scan.execute(
                        "SELECT place FROM items WHERE place IS NOT NULL AND place<>'' AND missing=0 "
                        "GROUP BY place ORDER BY COUNT(*) DESC LIMIT 25"
                    )
                ]
                lo, hi = scan.execute("SELECT MIN(taken_at), MAX(taken_at) FROM items WHERE missing=0").fetchone()
                return found, lo, hi
            finally:
                scan.close()

        places, first, last = self.ctx.memo("static_facts", 300.0, static_facts)
        conn = self.ctx.db.connect()
        try:

            def person_photos(phrase: str) -> int:
                ids = resolve_name(conn, phrase)
                if not ids:
                    return 0
                marks = ",".join("?" * len(ids))
                return int(
                    conn.execute(f"SELECT COUNT(DISTINCT item_id) FROM faces WHERE person_id IN ({marks})", ids).fetchone()[0]
                )

            evidence = probe(conn, request, person_photos)
        finally:
            conn.close()
        lines = []
        if places:
            lines.append("PLACES IN THIS LIBRARY: " + "; ".join(places))
        if first and last:
            lines.append(f"PHOTOS SPAN: {str(first)[:10]} to {str(last)[:10]}")
        if evidence:
            lines.append(evidence)
        return "\n".join(lines)

    def answerer(self, question: str, previous: np.ndarray | None) -> str:
        conn = self.ctx.db.connect()
        try:
            facts = gather_facts(conn, self.ctx.paths, previous)
            if previous is not None and 0 < len(previous) <= MAX_PHOTOS_TO_LOOK_AT and self.ctx.needs_to_see(question):
                seen = []
                for i, item_id in enumerate(previous.tolist(), 1):
                    try:
                        seen.append(
                            f"- photo {i}: {describe_item(conn, self.ctx.paths, self.ctx.describer(), self.ctx.settings.vision_model, int(item_id), question)}"
                        )
                    except LLMError as exc:
                        seen.append(f"- photo {i}: could not look at it ({exc})")
                facts += "\nWHAT THE VISION MODEL SAW IN THE PREVIOUS PHOTOS:\n" + "\n".join(seen)
        finally:
            conn.close()
        return answer_question(self.ctx.llm().complete_text, question, facts)

    def _chat_system(self) -> str:
        return f"Today's date is {date.today():%A %d %B %Y}.\n" + CHAT_SYSTEM

    def chatter(self, request: str, history: list[tuple[str, str]]) -> str:
        turns = [{"role": role, "content": text} for role, text in history[-8:] if role in ("user", "assistant") and text]
        return self.ctx.llm().complete_chat(
            self._chat_system(), [*turns, {"role": "user", "content": request}], max_tokens=CHAT_MAX_TOKENS
        )

    def chat_stream(self, request: str, history: list[tuple[str, str]]):
        turns = [{"role": role, "content": text} for role, text in history[-8:] if role in ("user", "assistant") and text]
        return self.ctx.llm().stream_chat(
            self._chat_system(), [*turns, {"role": "user", "content": request}], max_tokens=CHAT_MAX_TOKENS
        )

    def library_context(self, request: str) -> str:
        """RAG: facts from the user's own library that matter for THIS request (matching places and people, the date span)."""
        lines = [self.library_facts(request)]

        def count() -> str:
            conn = self.ctx.db.connect()
            try:
                cov = lib.coverage(conn)
                return f"{cov.total:,} files, {cov.indexed:,} indexed"
            finally:
                conn.close()

        lines.append("LIBRARY SIZE: " + self.ctx.memo("coverage_text", 60.0, count))
        people = self.people_names()
        if people:
            lines.append("PEOPLE FOUND: " + ", ".join(people[:40]))
        return "\n".join(line for line in lines if line)

    def date_step(self, request: str):
        """A short, focused model call: the time expression in the message (if any), as real date fields."""
        from .agent import phrasebook
        from .agent.schema import plan_from_raw

        hit = phrasebook.match(request)  # a known phrasing: its meaning comes from the phrasebook, exactly, with no model call
        if hit is not None:
            phrase, fields = hit
            return phrase, plan_from_raw({"intent": "find", "date": fields})[0].date
        answer = self.ctx.llm().complete_json(
            DATE_SYSTEM, phrasebook.examples_text(request) + "Message: " + request, DATE_SCHEMA, max_tokens=60
        )
        try:
            raw = extract_json(answer)
        except Exception:  # unreadable answer: treat as "no time expression"; an extra check must never stop a search
            raw = None
        if not isinstance(raw, dict):
            return "", plan_from_raw({})[0].date
        date_fields = {k: raw[k] for k in ("year", "month", "season", "relative", "ago", "unit", "through", "span") if k in raw}
        return str(raw.get("phrase") or "").strip(), plan_from_raw({"intent": "find", "date": date_fields})[0].date

    def reviser(self, request: str, plan: Any, feedback: str) -> Any:
        """Agent step: the search found nothing. Show the model what it tried and why it failed, and ask for a better plan."""
        import dataclasses
        import json

        from .agent.planner import plan_schema, plan_style, system_prompt
        from .agent.schema import plan_from_raw

        user = (
            f"{self.library_context(request)}\nUser: {request}\n\n"
            f"YOUR LAST PLAN FOUND NOTHING.\nPlan: {json.dumps(dataclasses.asdict(plan), default=str)}\nWhat happened: {feedback}\n"
            "Write a DIFFERENT plan that finds what the user meant. Compare each query with the real places, people and folders listed above: "
            'use a name exactly as listed, widen a place to its country or region, use scope "library" unless they clearly mean the earlier results, '
            "or drop a wrong clause. Output ONLY the JSON object."
        )
        style = plan_style()
        raw = extract_json(self.ctx.llm().complete_json(system_prompt(style), user, plan_schema(style)))
        return plan_from_raw(raw)[0] if isinstance(raw, dict) else None

    def probe_term(self, term: str) -> dict[str, Any]:
        """The probe tool: where does this word occur in the library? Counts per possible meaning, from the library itself.ctx."""
        from .people.repository import resolve_name
        from .search.metadata import path_ids, place_ids
        from .search.text import search_text_ids

        conn = self.ctx.db.connect()
        try:
            counts = {
                "photos_taken_in_a_place_with_this_name": len(place_ids(conn, term)),
                "photos_in_folders_or_files_with_this_name": len(path_ids(conn, term)),
                "photos_with_this_word_written_in_them": len(search_text_ids(conn, term)),
                "people_with_this_name": len(resolve_name(conn, term)),
            }
            try:
                counts["photos_that_look_like_this"] = conn.execute(
                    "SELECT COUNT(DISTINCT item_id) FROM photo_labels WHERE label=?", (term.strip().lower(),)
                ).fetchone()[0]
            except Exception:
                pass
        finally:
            conn.close()
        out: dict[str, Any] = {"term": term, **counts}
        if not any(counts.values()):
            out["similar_places"] = self.lookup("place", term)
            out["note"] = (
                "no exact match anywhere: it may be something to look for in the pictures, a date, or a place spelled differently"
            )
        return out

    def inspect_results(self, ids: list[int]) -> dict[str, Any]:
        """The inspect_results tool: when (date periods), where (places) and in which folders the given photos were taken."""
        from collections import Counter
        from datetime import date as _date
        from datetime import timedelta

        conn = self.ctx.db.connect()
        try:
            rows: list[tuple[Any, Any, Any]] = []
            for start in range(0, len(ids), 500):
                part = ids[start : start + 500]
                rows += conn.execute(
                    f"SELECT substr(taken_at,1,10), place, rel_path FROM items WHERE id IN ({','.join('?' * len(part))})",
                    part,
                ).fetchall()
        finally:
            conn.close()
        days = sorted({_date.fromisoformat(d) for d, _, _ in rows if d and len(d) == 10})
        periods: list[list[Any]] = []
        for day in days:
            if periods and day - periods[-1][1] <= timedelta(days=5):
                periods[-1][1] = day
                periods[-1][2] += 1
            else:
                periods.append([day, day, 1])
        counts = Counter(d for d, _, _ in rows if d)
        sized = [
            {
                "date_from": a.isoformat(),
                "date_to": b.isoformat(),
                "photos": sum(c for d, c in counts.items() if a.isoformat() <= d <= b.isoformat()),
            }
            for a, b, _ in periods
        ]
        sized.sort(key=lambda p: -p["photos"])
        places = Counter(p for _, p, _ in rows if p)
        folders = Counter(r.split("/")[0] for _, _, r in rows if r and "/" in r)
        return {
            "photos": len(rows),
            "date_periods": sized[:6],
            "places": places.most_common(5),
            "folders": folders.most_common(5),
        }

    def overview(self, previous_ids: Any) -> str:
        """The library_overview tool: plain facts for the model to read."""
        conn = self.ctx.db.connect()
        try:
            return gather_facts(conn, self.ctx.paths, previous_ids)
        finally:
            conn.close()

    def read_text(self, ids: list[int]) -> list[dict[str, Any]]:
        """The read_photo_text tool: the words found inside photos (OCR), for the model to answer from."""
        conn = self.ctx.db.connect()
        try:
            items = lib.items_by_ids(conn, ids)
            out = []
            for i in ids:
                text = " ".join(lib.item_text(conn, i, 900).split())
                if text:
                    item = items.get(i)
                    out.append(
                        {
                            "photo": i,
                            "date": (item.taken_at or "")[:10] if item else "",
                            "place": item.place if item else "",
                            "text": text,
                        }
                    )
            return out
        finally:
            conn.close()

    def look(self, ids: list[int], question: str) -> list[dict[str, Any]]:
        """The look_at_photos tool: the vision model answers a question about a few photos (descriptions are remembered)."""
        conn = self.ctx.db.connect()
        try:
            answers = []
            for i in ids:
                try:
                    answers.append(
                        {
                            "photo": i,
                            "answer": describe_item(
                                conn, self.ctx.paths, self.ctx.describer(), self.ctx.settings.vision_model, i, question
                            ),
                        }
                    )
                except LLMError as exc:
                    answers.append({"photo": i, "error": str(exc)})
            return answers
        finally:
            conn.close()

    def lookup(self, kind: str, text: str) -> list[str]:
        """The look_up tool: which places, people or folders really exist in this library."""

        def distinct(sql: str) -> list[str]:
            conn = self.ctx.db.connect()
            try:
                return [str(r[0]) for r in conn.execute(sql) if r[0]]
            finally:
                conn.close()

        if kind == "person":
            return close_matches(self.people_names(), text)
        if kind == "place":
            places = self.ctx.memo(
                "all_places",
                300.0,
                lambda: distinct("SELECT DISTINCT place FROM items WHERE place IS NOT NULL AND place<>'' AND missing=0"),
            )
            return close_matches(places, text)
        if kind == "folder":
            folders = self.ctx.memo(
                "all_folders",
                300.0,
                lambda: distinct(
                    "SELECT DISTINCT substr(rel_path, 1, instr(rel_path, '/') - 1) FROM items WHERE instr(rel_path, '/') > 0 AND missing=0"
                ),
            )
            return close_matches(folders, text)
        return []
