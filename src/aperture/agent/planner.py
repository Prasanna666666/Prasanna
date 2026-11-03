"""Turns a plain-English request into a validated :class:`Plan` using the LLM.

There are deliberately **no keyword heuristics** here.  If the model is
unreachable or cannot produce a valid plan after retries, the planner raises
and the UI says so; it never guesses with a regex and dumps unrelated photos.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date

from .jsonutil import JSONExtractError, extract_json
from .llm import LLMClient, LLMError
from .schema import Plan, plan_from_raw, plan_schema

_PROMPT_TEXT_RAW = """You are the planning brain of Aperture, a private offline photo assistant.
Convert the user's request into ONE JSON object. You do not search; you only plan.

SEARCH ENGINES (a clause lists every engine where its words might live):
- visual : what is SEEN in the picture (objects, scenes, activities). Query = short English noun phrase.
- text   : words or numbers PRINTED in the picture (signs, receipts, documents, screenshots). Query = the exact text.
- path   : folder names, file names, camera models.
- place  : city / country from GPS data (e.g. Bangalore, Japan).
- person : a named person. Prefer names from KNOWN PEOPLE.

FILTERS (optional "filters" object, set ONLY what the user states; omit the rest):
- time_of_day: dawn | morning | afternoon | evening | night   (or hour_from/hour_to, 24-hour clock)
- day_type: weekend | weekday        - orientation: landscape | portrait | square
- min_people / max_people: number of faces (group photo: min 3; selfie or single person: min 1,max 1; no people: max 0)
- quality: defects | no_defects (photos the user labelled as bad)    - has_gps: yes | no
- color: red|orange|yellow|green|teal|blue|purple|pink|brown|black|white|gray (the photo's overall dominant colour)
- kind: image | document            - near: a place name, radius_km: distance (default 25)
Objects and scenes ("dog", "indoors", "snow") are NOT filters: use a visual clause.

RULES
1. One clause per distinct constraint. Clauses are combined with AND ("match":"all") unless the user says "or" ("match":"any").
2. Use several engines in one clause when unsure where a word lives, e.g. a city: ["place","path"].
3. "exclude":true means NOT (e.g. "without", "except", "not in").
4. Dates go in "date" using year / month (1-12) / season / relative. NEVER compute dates yourself. Use 0 or "none" or "" for unused fields.
5. intent: "find" (show photos), "count" (how many), "export" (copy/put/organize into a folder; set folder_name),
   "chat" (anything that is NOT a request to find, count or copy photos and NOT a question about the library: greetings, thanks, small talk,
   general knowledge, explanations, advice, writing help, questions about you. "message" may stay empty: a separate reply is written),
   "question" (the user asks ABOUT the library or the app instead of asking to see photos: statistics, "how many per year/place/camera",
   "did the move finish?", "is indexing done?", "what are these photos?", "tell me about my library". Leave clauses empty),
   "clarify" (the request has nothing searchable; ask ONE short question in "message").
6. scope "previous" ONLY when the user refers to the earlier results ("only those", "of these", "now put them in a folder").
7. "all_photos": true ONLY if the user explicitly asks for the whole library.
8. Never invent constraints the user did not state. Keep filler words ("show me", "please", "pics of") out of queries.
9. A word after "from", "in", "at", "near" or "around" is a PLACE (or a folder) unless it is a year, month or season. Put it in a place clause, never in "date".
10. Use "date" ONLY when the user states a year, month, season or a relative time ("last week"). Otherwise leave every date field unused.
11. When DATA MATCHES is given, search each matched word with the engine(s) listed there. A word with no match is probably filler or a visual subject.
12. When PLACES IN THIS LIBRARY is given, write place queries exactly as spelled there when the user means one of them.
13. Visual queries are SINGULAR noun phrases ("dog", "mountain", "wedding"), never plural.
14. People counts (group, selfie, alone, nobody), orientation, time of day, distance ("within N km of X") and quality are FILTERS ONLY:
    never also add a clause for them. A request made only of filters has "clauses": [].
15. Output ONLY the JSON object.

EXAMPLES (compact):
User: show me photos of Anna at the beach in Goa last summer
{"intent":"find","message":"","scope":"library","match":"all","all_photos":false,"clauses":[{"engines":["person"],"query":"Anna","exclude":false},{"engines":["visual"],"query":"beach","exclude":false},{"engines":["place","path"],"query":"Goa","exclude":false}],"date":{"year":0,"month":0,"season":"summer","relative":"none","start":"","end":""},"folder_name":""}
User: put all receipts mentioning Starbucks into a folder called Coffee
{"intent":"export","message":"","scope":"library","match":"all","all_photos":false,"clauses":[{"engines":["text"],"query":"Starbucks","exclude":false}],"date":{"year":0,"month":0,"season":"none","relative":"none","start":"","end":""},"folder_name":"Coffee"}
User: how many pictures do I have from 2019?
{"intent":"count","message":"","scope":"library","match":"all","all_photos":false,"clauses":[],"date":{"year":2019,"month":0,"season":"none","relative":"none","start":"","end":""},"folder_name":""}
User: only the ones from December
{"intent":"find","message":"","scope":"previous","match":"all","all_photos":false,"clauses":[],"date":{"year":0,"month":12,"season":"none","relative":"none","start":"","end":""},"folder_name":""}
User: sunsets but not in Bangalore
{"intent":"find","message":"","scope":"library","match":"all","all_photos":false,"clauses":[{"engines":["visual"],"query":"sunset","exclude":false},{"engines":["place","path"],"query":"Bangalore","exclude":true}],"date":{"year":0,"month":0,"season":"none","relative":"none","start":"","end":""},"folder_name":""}
User: group photos from the weekend evenings within 30 km of Eindhoven
{"intent":"find","message":"","scope":"library","match":"all","all_photos":false,"clauses":[],"date":{"year":0,"month":0,"season":"none","relative":"none","start":"","end":""},"filters":{"time_of_day":"evening","day_type":"weekend","min_people":3,"near":"Eindhoven","radius_km":30},"folder_name":""}
User: portrait photos of dogs at night
{"intent":"find","message":"","scope":"library","match":"all","all_photos":false,"clauses":[{"engines":["visual"],"query":"dog","exclude":false}],"date":{"year":0,"month":0,"season":"none","relative":"none","start":"","end":""},"filters":{"time_of_day":"night","orientation":"portrait"},"folder_name":""}
User: invoice number 48213
{"intent":"find","message":"","scope":"library","match":"all","all_photos":false,"clauses":[{"engines":["text"],"query":"48213","exclude":false}],"date":{"year":0,"month":0,"season":"none","relative":"none","start":"","end":""},"folder_name":""}
User: did the move finish? how many photos are in each year?
{"intent":"question","message":"","scope":"library","match":"all","all_photos":false,"clauses":[],"date":{"year":0,"month":0,"season":"none","relative":"none","start":"","end":""},"folder_name":""}
{EXTRA_EXAMPLES}User: hi, what can you do?
{"intent":"chat","message":"I can find photos by what they show, text inside them, people, places, dates and folders, and copy results into a folder.","scope":"library","match":"all","all_photos":false,"clauses":[],"date":{"year":0,"month":0,"season":"none","relative":"none","start":"","end":""},"folder_name":""}
"""

def _example(request: str, intent: str = "find", clauses=(), date_: dict | None = None, filters: dict | None = None,
             scope: str = "library", folder: str = "") -> str:
    plan = {"intent": intent, "message": "", "scope": scope, "match": "all", "all_photos": False,
            "clauses": [{"engines": list(e), "query": q, "exclude": x} for e, q, x in clauses],
            "date": {"year": 0, "month": 0, "season": "none", "relative": "none", "start": "", "end": "", **(date_ or {})}}
    if filters:
        plan["filters"] = filters
    plan["folder_name"] = folder
    return f"User: {request}\n{json.dumps(plan, separators=(',', ':'), ensure_ascii=False)}\n"


# Worked examples that teach PRINCIPLES (singular nouns, filters replace clauses, folder requests are not "previous",
# "what did I shoot in <month>" is a find). They deliberately do not reuse the phrases of the eval cases.
_EXTRA_EXAMPLES = "".join([
    _example("photos with only one person in them", filters={"min_people": 1, "max_people": 1}),
    _example("crowded pictures with ten or more people", filters={"min_people": 10}),
    _example("photos within 5 km of Utrecht", filters={"near": "Utrecht", "radius_km": 5}),
    _example("street scenes without any people", clauses=[(["visual"], "street", False)], filters={"max_people": 0}),
    _example("what did I shoot in March 2018", date_={"year": 2018, "month": 3}),
    _example("how many shots did I take last year", intent="count", date_={"relative": "last_year"}),
    _example("put my Rome pictures into a folder called Italy", intent="export",
             clauses=[(["place", "path"], "Rome", False)], folder="Italy"),
    _example("wildlife photos not taken in Kenya", clauses=[(["visual"], "wildlife", False), (["place", "path"], "Kenya", True)]),
    _example("thanks, that was really helpful", intent="chat"),
    _example("what is the difference between RAW and JPEG?", intent="chat"),
    _example("tell me a joke", intent="chat"),
    _example("how are you doing today?", intent="chat"),
])
_PROMPT_TEXT = _PROMPT_TEXT_RAW.replace("{EXTRA_EXAMPLES}", _EXTRA_EXAMPLES)

# Speed: a 3B model on an 8 GB Mac writes ~19 tokens/s, so every token costs time. Two styles (APERTURE_PLAN_STYLE):
#   full - every field forced (the original; most reliable guidance for a small model)
#   lean - drops only the empty fields (message, folder_name, exclude:false, date start/end): ~18% fewer tokens; decision fields stay forced.
# plan_from_raw fills every default either way, so both mean the same plan. Pick with `aperture eval-plans`.
_DEFAULTS = {"message": "", "folder_name": ""}
_RULE4_FULL = 'Use 0 or "none" or "" for unused fields.'
_RULE4_LEAN = 'Use 0 or "none" for unused date fields. Leave out "message" and "folder_name" unless they are needed.'


def plan_style() -> str:
    return "lean" if os.environ.get("APERTURE_PLAN_STYLE", "full").lower() == "lean" else "full"  # full until lean is measured


def slim_plan(obj: dict) -> dict:
    """Lean form of a full example plan: same meaning, without the empty fields."""
    out = {k: v for k, v in obj.items() if k not in _DEFAULTS or v != _DEFAULTS[k]}
    out["clauses"] = [{k: v for k, v in c.items() if not (k == "exclude" and v is False)} for c in obj.get("clauses", [])]
    if isinstance(obj.get("date"), dict):
        out["date"] = {k: v for k, v in obj["date"].items() if k not in ("start", "end") or v}
    out.setdefault("filters", {})
    return out


def _slim_examples(text: str) -> str:
    return "\n".join(
        json.dumps(slim_plan(json.loads(line)), separators=(",", ":"), ensure_ascii=False) if line.startswith("{") else line
        for line in text.split("\n")
    )


def system_prompt(style: str | None = None) -> str:
    style = style or plan_style()
    if style == "full":
        return _PROMPT_TEXT
    return _slim_examples(_PROMPT_TEXT.replace(_RULE4_FULL, _RULE4_LEAN))


SYSTEM_PROMPT = _PROMPT_TEXT  # default-style prompt is built per call by system_prompt()


@dataclass(frozen=True)
class PlannerContext:
    today: date
    known_people: tuple[str, ...] = ()
    previous_count: int | None = None
    library: str = ""  # facts about THIS library (places, date span) so the model picks real values


@dataclass
class PlanResult:
    plan: Plan
    warnings: list[str] = field(default_factory=list)
    attempts: int = 1


class PlanningError(RuntimeError):
    """The model never produced a usable plan."""


class Planner:
    def __init__(self, llm: LLMClient, max_attempts: int = 3) -> None:
        self._llm = llm
        self._max_attempts = max_attempts

    @staticmethod
    def _user_prompt(request: str, ctx: PlannerContext) -> str:
        people = ", ".join(ctx.known_people[:150]) or "(none named yet)"
        previous = f"{ctx.previous_count} photos" if ctx.previous_count is not None else "(none)"
        library = f"{ctx.library}\n" if ctx.library else ""
        # No "TODAY" line on purpose: dates are resolved in code (search/dates.py) from year/month/season/relative, and a small
        # model asked to fill year+month copies today's date into every plan ("sunset photos" -> year 2026, month 11).
        return f"KNOWN PEOPLE: {people}\n{library}PREVIOUS RESULTS: {previous}\nUser: {request.strip()}"

    def plan(self, request: str, ctx: PlannerContext) -> PlanResult:
        user = self._user_prompt(request, ctx)
        last_error = "no attempt made"
        for attempt in range(1, self._max_attempts + 1):
            prompt = (
                user
                if attempt == 1
                else (
                    f"{user}\n\nYour previous reply was rejected ({last_error}). "
                    "Reply again with ONLY a valid JSON object that follows the schema."
                )
            )
            try:
                style = plan_style()
                raw_text = self._llm.complete_json(system_prompt(style), prompt, plan_schema(style))
            except LLMError:
                raise  # unreachable / missing model: retrying will not help
            try:
                raw = extract_json(raw_text)
            except JSONExtractError as exc:
                last_error = str(exc)
                continue
            plan, warnings = plan_from_raw(raw)
            if not isinstance(raw, dict):
                last_error = "top level was not an object"
                continue
            return PlanResult(plan=plan, warnings=warnings, attempts=attempt)
        raise PlanningError(f"The local model could not produce a valid plan after {self._max_attempts} tries ({last_error}).")


def debug_prompt(request: str, ctx: PlannerContext) -> str:
    """The exact user prompt sent to the model (for the 'How I searched' panel)."""
    return json.dumps(Planner._user_prompt(request, ctx))
