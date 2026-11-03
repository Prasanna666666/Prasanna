"""The agent loop: the model decides which tool to use next, looks at the result, and repeats.

Nothing about *how to interpret a request* is coded here.  The model chooses
engines, filters, thresholds and verification steps itself, and can check its
own work with a vision model.  What stays in code are the guarantees that must
not depend on a model's judgement:

* photo ids only ever come from tools (the model cannot invent a photo);
* the model cannot move, delete or write anything - it can only *propose* an
  export or a move, which the user confirms in the interface;
* the loop is bounded (steps, vision checks) and every failure becomes a clear
  message instead of a guess.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np

from .. import library, quality
from ..config import Paths, Settings
from ..ml.protocols import ImageEmbedder
from ..people.repository import faces_in_item, named_people
from ..search.embeddings import EmbeddingIndex
from ..search.visual import STRICTNESS, VisualSearch
from .executor import Executor
from .jsonutil import JSONExtractError, extract_json
from .llm import LLMClient, LLMError, Vision
from .planner import PlannerContext, PlanningError, PlanResult
from .schema import Plan, plan_from_raw
from .service import AgentReply, describe_conditions, explain_empty

log = logging.getLogger(__name__)

TOOLS: dict[str, str] = {
    "library_overview": "no args. Counts, years, places, named people and folders that exist. Use when unsure what is in the library.",
    "plan_search": 'args = a search plan {"intent","scope","match","clauses":[{"engines":[visual|text|path|place|person],"query","exclude"}],"date":{year,month,season,relative,start,end},"filters":{time_of_day,hour_from,hour_to,day_type,orientation,min_people,max_people,quality,has_gps,kind,near,radius_km}}. Runs everything and returns a photo set.',
    "search_visual": 'args {"query":"english phrase","strictness":"strict|balanced|broad"}. Pure image-content search; strictness trades recall for precision.',
    "combine": 'args {"op":"and|or|not","a":"A","b":"B"}. Set algebra on earlier sets (not = a minus b).',
    "inspect": 'args {"set":"A","n":5}. Describes a few photos of a set (folder, date, place, people, text) so you can judge them.',
    "verify_visually": 'args {"set":"A","question":"does the photo show ...?","n":6}. A vision model checks a sample and reports how many are right. Use to measure precision.',
    "filter_visually": 'args {"set":"A","question":"..."}. The vision model checks EVERY photo of a small set and keeps the confirmed ones as a new set.',
    "suggest_defects": 'args {"sensitivity":"low|medium|high"}. Candidate badly-taken photos (measured blur/exposure), as a set. Confirm with filter_visually.',
    "ask_user": 'args {"question":"..."}. Ends the turn with one short question when the request is too vague to search.',
    "finish": 'args {"set":"A","message":"short wording for the user","show":"photos|count|export|move|none","folder_name":""}. Ends the turn. show=none for chit-chat. export/move only PROPOSE; the user confirms.',
}

SYSTEM_PROMPT = (
    """You are Aperture, an agent that finds and organises the user's private photo library using tools.
Each turn reply with ONE JSON object: {"thought": "<one short sentence>", "tool": "<name>", "args": {...}}.
After a tool runs you see its result and choose the next tool, until you call finish.

TOOLS
"""
    + "\n".join(f"- {name}: {text}" for name, text in TOOLS.items())
    + """

HOW TO WORK
- For most requests start with plan_search: put every constraint the user stated in it (objects/scenes -> visual clauses, printed words -> text, names of people -> person, places and folders -> place+path, dates, time of day, counts of people...). Do not add constraints the user did not state.
- Read the result. If it is empty, say so honestly (finish with an empty set) - never loosen the request to fill the screen.
- If precision matters or the result looks doubtful, use inspect or verify_visually. If many in the sample are wrong, search again more strictly (search_visual strictness=strict, or combine). Use filter_visually only on small sets.
- Photo sets are named A, B, C... and only tools create them. Never write photo ids yourself.
- Finish as soon as you are confident. Keep "message" to one friendly sentence.

EXAMPLES
User: photos of Anna at the beach last summer
{"thought":"person plus scene plus season","tool":"plan_search","args":{"intent":"find","scope":"library","match":"all","clauses":[{"engines":["person"],"query":"Anna","exclude":false},{"engines":["visual"],"query":"beach","exclude":false}],"date":{"season":"summer","relative":"none"}}}
(result: Set A: 14 photos)  ->  {"thought":"good","tool":"finish","args":{"set":"A","message":"Here are Anna's beach photos from last summer.","show":"photos","folder_name":""}}
User: how many invoices mention Acme?
{"thought":"printed text","tool":"plan_search","args":{"intent":"count","clauses":[{"engines":["text"],"query":"Acme","exclude":false}]}}
(result: Set A: 7 photos)  ->  {"thought":"done","tool":"finish","args":{"set":"A","message":"These mention Acme.","show":"count","folder_name":""}}
User: hello!
{"thought":"greeting","tool":"finish","args":{"set":"","message":"Hi! Ask me to find photos by what they show, text, people, places or time, or to organise them.","show":"none","folder_name":""}}
Output ONLY the JSON object."""
)

STEP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "thought": {"type": "string"},
        "tool": {"type": "string", "enum": list(TOOLS)},
        "args": {"type": "object"},
    },
    "required": ["thought", "tool", "args"],
}


@dataclass
class Step:
    tool: str
    thought: str
    args: dict[str, Any]
    observation: str

    def as_dict(self) -> dict[str, str]:
        return {
            "tool": self.tool,
            "thought": self.thought,
            "args": json.dumps(self.args, ensure_ascii=False)[:600],
            "observation": self.observation,
        }


class ToolError(Exception):
    """A tool was used wrongly; the message goes back to the model as its observation."""


@dataclass
class Memory:
    sets: dict[str, np.ndarray] = field(default_factory=dict)
    notes: dict[str, str] = field(default_factory=dict)
    last_plan: Plan | None = None
    last_reports: list[Any] = field(default_factory=list)
    last_notes: list[str] = field(default_factory=list)

    def add(self, ids: np.ndarray, note: str) -> str:
        name = chr(ord("A") + len(self.sets)) if len(self.sets) < 26 else f"S{len(self.sets)}"
        self.sets[name] = np.asarray(ids, np.int64)
        self.notes[name] = note
        return name

    def get(self, name: Any) -> np.ndarray:
        key = str(name).strip().strip("'\"").upper()
        if key not in self.sets:
            raise ToolError(f"unknown set {name!r}; existing sets: {', '.join(self.sets) or 'none yet'}")
        return self.sets[key]


class Toolbox:
    """The tools.  Every method returns a short text observation for the model."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        paths: Paths,
        settings: Settings,
        executor_factory: Callable[[], Executor],
        index_provider: Callable[[], EmbeddingIndex],
        embedder_provider: Callable[[], ImageEmbedder | None],
        vision: Vision | None,
        previous_ids: np.ndarray | None,
    ) -> None:
        self.conn, self.paths, self.settings = conn, paths, settings
        self._executor_factory = executor_factory
        self._index_provider, self._embedder_provider = index_provider, embedder_provider
        self.vision = vision
        self.previous_ids = previous_ids
        self.memory = Memory()

    # -- helpers ------------------------------------------------------------
    def _describe(self, item_id: int) -> str:
        item = library.get_item(self.conn, item_id)
        if item is None:
            return f"#{item_id} (missing)"
        who = ", ".join(sorted({label for _, label in faces_in_item(self.conn, item_id)})) or "-"
        text = " ".join(library.item_text(self.conn, item_id, 120).split())
        return f"#{item.id} {item.rel_path} | {item.date_label} | {item.place or '-'} | people: {who}" + (
            f" | text: {text}" if text else ""
        )

    def _sample(self, ids: np.ndarray, n: int) -> list[int]:
        if len(ids) <= n:
            return [int(i) for i in ids]
        picks = np.linspace(0, len(ids) - 1, n).astype(int)  # spread over the ranking, not just the top
        return [int(ids[i]) for i in picks]

    def _set_line(self, name: str, ids: np.ndarray, extra: str = "") -> str:
        examples = "; ".join(self._describe(i) for i in self._sample(ids, 3)) if len(ids) else "none"
        return f"Set {name}: {len(ids):,} photos. {extra}Examples: {examples}"

    # -- tools --------------------------------------------------------------
    def library_overview(self, args: dict[str, Any]) -> str:
        c = library.coverage(self.conn)
        places = [
            r[0]
            for r in self.conn.execute(
                "SELECT place FROM items WHERE place IS NOT NULL AND missing=0 GROUP BY place ORDER BY COUNT(*) DESC LIMIT 15"
            )
        ]
        folders = [
            r[0]
            for r in self.conn.execute(
                "SELECT DISTINCT substr(rel_path, 1, instr(rel_path || '/', '/') - 1) FROM items WHERE missing=0 LIMIT 20"
            )
        ]
        people = [n for _, n in named_people(self.conn, 30)]
        years = library.years_available(self.conn)
        return (
            f"{c.total:,} files ({c.indexed:,} indexed, {c.faces_done:,} with faces done, {c.ocr_done:,} text-read). "
            f"Years: {years[-1] if years else '-'}-{years[0] if years else '-'}. Places: {', '.join(places) or '-'}. "
            f"Top folders: {', '.join(folders) or '-'}. Named people: {', '.join(people) or 'none'}."
        )

    def plan_search(self, args: dict[str, Any]) -> str:
        raw = args.get("plan") if isinstance(args.get("plan"), dict) else args
        plan, warnings = plan_from_raw(raw)
        if not plan.has_constraints:
            raise ToolError("the plan has no constraints; state at least one clause, date or filter")
        outcome = self._executor_factory().run(plan, self.previous_ids if plan.scope == "previous" else None)
        mem = self.memory
        mem.last_plan, mem.last_reports, mem.last_notes = plan, outcome.reports, outcome.notes
        name = mem.add(outcome.ids, describe_conditions(plan, outcome.date_range))
        parts = [f"{r.label}: {r.matched:,} match, {r.remaining:,} left" for r in outcome.reports]
        extra = ("Steps: " + "; ".join(parts) + ". ") if parts else ""
        extra += ("Notes: " + " ".join(outcome.notes) + " ") if outcome.notes else ""
        extra += ("Warnings: " + " ".join(warnings) + " ") if warnings else ""
        if len(outcome.ids) == 0:
            extra += explain_empty(outcome.reports) + " "
        return self._set_line(name, outcome.ids, extra)

    def search_visual(self, args: dict[str, Any]) -> str:
        query = str(args.get("query", "")).strip()
        if not query:
            raise ToolError("query is required")
        level = str(args.get("strictness", "balanced")).lower()
        if level not in STRICTNESS:
            raise ToolError(f"strictness must be one of {', '.join(STRICTNESS)}")
        embedder = self._embedder_provider()
        if embedder is None:
            raise ToolError("the visual model is not available")
        hits = VisualSearch(self._index_provider(), embedder, level).search(query)
        name = self.memory.add(hits.ids, f"visual '{query}' ({level})")
        return self._set_line(name, hits.ids, f"Closest similarity in library {hits.best_cosine:.2f}. ")

    def combine(self, args: dict[str, Any]) -> str:
        a, b = self.memory.get(args.get("a")), self.memory.get(args.get("b"))
        op = str(args.get("op", "")).lower()
        if op == "and":
            ids = np.intersect1d(a, b)
        elif op == "or":
            ids = np.union1d(a, b)
        elif op == "not":
            ids = np.setdiff1d(a, b)
        else:
            raise ToolError("op must be and, or or not")
        order = {int(i): n for n, i in enumerate(a)}  # keep set a's ranking where possible
        ids = np.array(sorted(ids.tolist(), key=lambda i: order.get(i, len(order))), np.int64)
        return self._set_line(self.memory.add(ids, f"{args.get('a')} {op} {args.get('b')}"), ids)

    def inspect(self, args: dict[str, Any]) -> str:
        ids = self.memory.get(args.get("set"))
        n = max(1, min(int(args.get("n", 5) or 5), 8))
        return "\n".join(self._describe(i) for i in self._sample(ids, n)) or "(empty set)"

    def _look(self, item_id: int, question: str) -> tuple[bool, str]:
        if self.vision is None:
            raise ToolError("no vision model is configured")
        item = library.get_item(self.conn, item_id)
        thumb = self.paths.data / (item.thumb or "") if item and item.thumb else None
        if thumb is None or not thumb.is_file():
            return False, "no preview yet"
        try:
            return self.vision.judge(thumb.read_bytes(), question)
        except LLMError as exc:
            raise ToolError(f"the vision model is unavailable: {exc}") from exc

    def verify_visually(self, args: dict[str, Any]) -> str:
        ids, question = self.memory.get(args.get("set")), str(args.get("question", "")).strip()
        if not question:
            raise ToolError("question is required")
        n = max(1, min(int(args.get("n", 6) or 6), 12))
        sample = self._sample(ids, n)
        verdicts = [(i, *self._look(i, question)) for i in sample]
        good = sum(1 for _, ok, _ in verdicts if ok)
        bad = "; ".join(f"#{i} ({why})" for i, ok, why in verdicts if not ok)
        return f"{good}/{len(verdicts)} sampled photos confirmed ({good / max(1, len(verdicts)):.0%}). Rejected: {bad or 'none'}."

    def filter_visually(self, args: dict[str, Any]) -> str:
        ids, question = self.memory.get(args.get("set")), str(args.get("question", "")).strip()
        if not question:
            raise ToolError("question is required")
        limit = self.settings.verify_limit
        if len(ids) > limit:
            raise ToolError(
                f"the set has {len(ids):,} photos; filter_visually handles at most {limit}. Narrow it first or use verify_visually on a sample"
            )
        keep = [int(i) for i in ids if self._look(int(i), question)[0]]
        arr = np.array(keep, np.int64)
        return self._set_line(
            self.memory.add(arr, f"confirmed: {question}"), arr, f"Vision model confirmed {len(keep)} of {len(ids)}. "
        )

    def suggest_defects(self, args: dict[str, Any]) -> str:
        level = str(args.get("sensitivity", "high")).lower()
        if level not in quality.SENSITIVITY:
            raise ToolError("sensitivity must be low, medium or high")
        quality.ensure_quality(self.conn, self.paths)
        found = quality.suggest_defects(self.conn, level)
        ids = np.array([i for i, _ in found], np.int64)
        return self._set_line(
            self.memory.add(ids, f"defect candidates ({level})"),
            ids,
            "These are measurements only; confirm with filter_visually. ",
        )


@dataclass
class Finish:
    set_name: str
    message: str
    show: str
    folder_name: str


class AgentLoop:
    """Same ``ask`` interface as :class:`AgentService`, but model-driven."""

    def __init__(
        self,
        llm: LLMClient,
        toolbox_factory: Callable[[np.ndarray | None], Toolbox],
        known_people: Callable[[], list[str]],
        max_steps: int = 8,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._llm = llm
        self._toolbox_factory = toolbox_factory
        self._known_people = known_people
        self._max_steps = max(1, max_steps)
        self._today = today

    # -- one model turn -----------------------------------------------------
    def _next(self, prompt: str) -> dict[str, Any]:
        error = ""
        for _ in range(3):
            text = self._llm.complete_json(
                SYSTEM_PROMPT,
                prompt + (f"\nYour last reply was invalid ({error}). Reply with ONLY the JSON object." if error else ""),
                STEP_SCHEMA,
            )
            try:
                raw = extract_json(text)
            except JSONExtractError as exc:
                error = str(exc)
                continue
            if isinstance(raw, dict) and str(raw.get("tool", "")) in TOOLS:
                args = raw.get("args")
                return {
                    "thought": str(raw.get("thought", ""))[:300],
                    "tool": str(raw["tool"]),
                    "args": args if isinstance(args, dict) else {},
                }
            error = f"'tool' must be one of {', '.join(TOOLS)}"
        raise PlanningError(f"The local model could not choose a valid next step ({error}).")

    @staticmethod
    def _history(steps: list[Step]) -> str:
        return "\n".join(
            f"{n}. {s.tool}({json.dumps(s.args, ensure_ascii=False)[:300]}) -> {s.observation[:700]}"
            for n, s in enumerate(steps[-6:], start=max(1, len(steps) - 5))
        )

    def _dispatch(self, box: Toolbox, tool: str, args: dict[str, Any]) -> str:
        try:
            return str(getattr(box, tool)(args))
        except ToolError as exc:
            return f"error: {exc}"
        except (sqlite3.Error, ValueError, TypeError, OSError) as exc:
            log.exception("tool %s failed", tool)
            return f"error: {type(exc).__name__}: {exc}"

    # -- public -------------------------------------------------------------
    def ask(
        self, request: str, previous_ids: np.ndarray | None = None, history: list[tuple[str, str]] | None = None
    ) -> AgentReply:
        if not request.strip():
            return AgentReply("clarify", "What would you like to find?")
        box = self._toolbox_factory(previous_ids)
        people = ", ".join(self._known_people()[:100]) or "none named yet"
        prior = (
            f"{len(previous_ids)} photos (use scope previous to refine them)"
            if previous_ids is not None and len(previous_ids)
            else "none"
        )
        header = f"TODAY: {self._today().isoformat()}\nKNOWN PEOPLE: {people}\nPREVIOUS RESULTS: {prior}\nUser: {request.strip()}"
        steps: list[Step] = []
        try:
            for _ in range(self._max_steps):
                prompt = header + ("\nPROGRESS:\n" + self._history(steps) if steps else "")
                move = self._next(prompt)
                tool, args = move["tool"], move["args"]
                if tool == "finish":
                    return self._finish(box, request, steps, move, args)
                if tool == "ask_user":
                    steps.append(Step(tool, move["thought"], args, "asked the user"))
                    return AgentReply(
                        "clarify",
                        str(args.get("question") or "Could you tell me a bit more?"),
                        trace=[s.as_dict() for s in steps],
                    )
                steps.append(Step(tool, move["thought"], args, self._dispatch(box, tool, args)))
        except (LLMError, PlanningError) as exc:
            return AgentReply("error", str(exc), trace=[s.as_dict() for s in steps])
        # Budget used up: show the latest set honestly, flagged.
        latest = list(box.memory.sets)[-1] if box.memory.sets else None
        if latest is None:
            return AgentReply(
                "error",
                f"I could not finish within {self._max_steps} steps. Try a more specific request.",
                trace=[s.as_dict() for s in steps],
            )
        reply = self._reply(
            box, latest, f"I stopped after {self._max_steps} steps; this is my latest result.", "photos", "", steps
        )
        reply.warnings.append("The agent ran out of steps, so this result may be unrefined.")
        return reply

    # -- building the reply from facts, not from model-claimed numbers --------
    def _finish(self, box: Toolbox, request: str, steps: list[Step], move: dict[str, Any], args: dict[str, Any]) -> AgentReply:
        steps.append(Step("finish", move["thought"], args, "done"))
        show = str(args.get("show", "photos")).lower()
        message = " ".join(str(args.get("message", "")).split())[:400]
        if show == "none":
            return AgentReply("chat", message or "Ask me to find or organise photos.", trace=[s.as_dict() for s in steps])
        name = str(args.get("set", "")).strip().upper()
        if name not in box.memory.sets:
            if not box.memory.sets:
                return AgentReply("clarify", message or "What should I look for?", trace=[s.as_dict() for s in steps])
            name = list(box.memory.sets)[-1]
        return self._reply(box, name, message, show, str(args.get("folder_name", ""))[:120], steps)

    def _reply(self, box: Toolbox, name: str, message: str, show: str, folder: str, steps: list[Step]) -> AgentReply:
        ids = box.memory.sets[name]
        n = len(ids)
        mem = box.memory
        fact = f"**{n:,}** photo{'s' if n != 1 else ''}" if n else "No photos"
        if n == 0 and mem.last_reports:
            message = f"{message} {explain_empty(mem.last_reports)}".strip()
        kind = "count" if show == "count" else "export" if show == "export" and n else "results"
        reply = AgentReply(
            kind,  # type: ignore[arg-type]
            f"{fact} {'found' if kind != 'count' else 'match'}. {message}".strip(),
            ids=ids,
            plan=mem.last_plan,
            reports=mem.last_reports,
            notes=list(mem.last_notes),
            folder_name=folder or (mem.last_plan.folder_name if mem.last_plan else ""),
            trace=[s.as_dict() for s in steps],
        )
        return reply


# --------------------------------------------------------------------------
# Dry-run adapter: lets `aperture eval-plans` measure the loop's first plan
# --------------------------------------------------------------------------
class _DryBox(Toolbox):
    def __init__(self) -> None:  # no database, no models
        self.memory = Memory()
        self.captured: Plan | None = None

    def _fake(self, label: str) -> str:
        name = self.memory.add(np.arange(3, dtype=np.int64), label)
        return f"Set {name}: 3 photos (dry run)."

    def plan_search(self, args: dict[str, Any]) -> str:
        raw = args.get("plan") if isinstance(args.get("plan"), dict) else args
        plan, _ = plan_from_raw(raw)
        self.captured = self.captured or plan
        return self._fake("plan")

    def search_visual(self, args: dict[str, Any]) -> str:
        return self._fake("visual")

    def combine(self, args: dict[str, Any]) -> str:
        return self._fake("combine")

    def library_overview(self, args: dict[str, Any]) -> str:
        return "dry run"

    def inspect(self, args: dict[str, Any]) -> str:
        return "dry run"

    def verify_visually(self, args: dict[str, Any]) -> str:
        return "6/6 sampled photos confirmed (100%). Rejected: none."

    def filter_visually(self, args: dict[str, Any]) -> str:
        return self._fake("filter")

    def suggest_defects(self, args: dict[str, Any]) -> str:
        return self._fake("defects")


class LoopPlanner:
    """Presents the agent loop as a ``Planner`` (``plan(request, ctx)``) for accuracy evaluation."""

    def __init__(self, llm: LLMClient, max_steps: int = 6) -> None:
        self._llm, self._max_steps = llm, max_steps

    def plan(self, request: str, ctx: PlannerContext) -> PlanResult:
        box = _DryBox()
        loop = AgentLoop(self._llm, lambda _p: box, lambda: list(ctx.known_people), self._max_steps, lambda: ctx.today)
        previous = np.arange(ctx.previous_count) if ctx.previous_count else None
        reply = loop.ask(request, previous)
        if reply.kind == "error":
            raise PlanningError(reply.text)
        plan = box.captured or Plan()
        finish = next((s for s in reversed(reply.trace) if s["tool"] in ("finish", "ask_user")), None)
        args = json.loads(finish["args"]) if finish else {}
        if reply.kind == "chat":
            return PlanResult(Plan(intent="chat", message=reply.text))
        if reply.kind == "clarify":
            return PlanResult(Plan(intent="clarify", message=reply.text))
        show = str(args.get("show", "photos"))
        intent = {"count": "count", "export": "export"}.get(show, "find")
        from dataclasses import replace

        return PlanResult(replace(plan, intent=intent, folder_name=str(args.get("folder_name", "")) or plan.folder_name))
