"""The query plan: what the LLM must produce and how it is validated.

A plan is a small *boolean* structure - clauses combined with AND (default) or
OR, optional NOT per clause - not a bag of fuzzy weights.  Set logic is what
gives Aperture its precision: a photo is returned only if it satisfies the
constraints, never because it half-matched several of them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..colors import COLORS
from ..search.dates import RELATIVE, DateSpec
from ..search.filters import DAY_TYPES, KINDS, ORIENTATIONS, QUALITIES, TIMES_OF_DAY, TRISTATE, Filters

ENGINES = ("visual", "text", "path", "person", "place")
INTENTS = ("find", "count", "export", "chat", "clarify", "question")
SEASONS = ("none", "spring", "summer", "autumn", "winter")
RELATIVES = ("none", *RELATIVE)
MAX_CLAUSES = 8


@dataclass(frozen=True)
class Clause:
    engines: tuple[str, ...]  # matches if ANY listed engine matches
    query: str
    exclude: bool = False  # NOT

    @property
    def label(self) -> str:
        what = "/".join(self.engines)
        return f"{'NOT ' if self.exclude else ''}{what} '{self.query}'"


@dataclass(frozen=True)
class Plan:
    intent: str = "clarify"
    clauses: tuple[Clause, ...] = ()
    match: str = "all"  # "all" = AND, "any" = OR (over positive clauses)
    date: DateSpec = field(default_factory=DateSpec)
    filters: Filters = field(default_factory=Filters)
    scope: str = "library"  # "previous" = refine the last result set
    all_photos: bool = False  # only when the user explicitly asks for everything
    folder_name: str = ""
    meanings: tuple[str, ...] = ()  # how the main subject would look in a photo (written by the model from the typed words only)
    message: str = ""

    @property
    def has_constraints(self) -> bool:
        return bool(self.clauses) or not self.date.is_empty or not self.filters.is_empty or self.all_photos


_DATE_PROPS: dict[str, Any] = {
    "year": {"type": "integer"},
    "month": {"type": "integer"},
    "season": {"type": "string", "enum": list(SEASONS)},
    "relative": {"type": "string", "enum": list(RELATIVES)},
    "start": {"type": "string"},
    "end": {"type": "string"},
}

_FILTER_PROPS: dict[str, Any] = {
    "time_of_day": {"type": "string", "enum": list(TIMES_OF_DAY)},
    "hour_from": {"type": "integer"},
    "hour_to": {"type": "integer"},
    "day_type": {"type": "string", "enum": list(DAY_TYPES)},
    "orientation": {"type": "string", "enum": list(ORIENTATIONS)},
    "min_people": {"type": "integer"},
    "max_people": {"type": "integer"},
    "quality": {"type": "string", "enum": list(QUALITIES)},
    "has_gps": {"type": "string", "enum": list(TRISTATE)},
    "kind": {"type": "string", "enum": list(KINDS)},
    "near": {"type": "string"},
    "radius_km": {"type": "integer"},
    "color": {"type": "string", "enum": list(COLORS)},
}

PLAN_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": list(INTENTS)},
        "message": {"type": "string"},
        "scope": {"type": "string", "enum": ["library", "previous"]},
        "match": {"type": "string", "enum": ["all", "any"]},
        "all_photos": {"type": "boolean"},
        "clauses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "engines": {"type": "array", "items": {"type": "string", "enum": list(ENGINES)}},
                    "query": {"type": "string"},
                    "exclude": {"type": "boolean"},
                },
                "required": ["engines", "query", "exclude"],
            },
        },
        "date": {"type": "object", "properties": _DATE_PROPS, "required": list(_DATE_PROPS)},
        "filters": {"type": "object", "properties": _FILTER_PROPS},
        "folder_name": {"type": "string"},
    },
    "required": ["intent", "message", "scope", "match", "all_photos", "clauses", "date", "folder_name"],
}


def plan_schema(style: str = "lean") -> dict[str, Any]:
    """The schema the model must follow. "full" = every field forced (original). "lean" = the same checklist for the fields that
    carry decisions (scope, match, all_photos, date, filters) but without the empty ones (message, folder_name, exclude:false,
    date start/end): ~20% fewer tokens to write, which matters at ~19 tokens/s. Measure both with `aperture eval-plans`."""
    if style == "full":
        return PLAN_JSON_SCHEMA
    import copy

    lean = copy.deepcopy(PLAN_JSON_SCHEMA)
    lean["required"] = ["intent", "scope", "match", "all_photos", "clauses", "date", "filters"]
    lean["properties"]["clauses"]["items"]["required"] = ["engines", "query"]
    lean["properties"]["date"]["required"] = ["year", "month", "season", "relative"]
    lean["properties"]["filters"] = {"type": "object", "properties": _FILTER_PROPS}
    return lean


# --------------------------------------------------------------------------
# Lenient coercion: never raises, never KeyErrors.
# --------------------------------------------------------------------------
def _text(value: Any, limit: int = 200) -> str:
    return " ".join(str(value).split())[:limit] if isinstance(value, (str, int, float)) else ""


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _choice(value: Any, allowed: tuple[str, ...] | list[str], default: str) -> str:
    text = _text(value).lower().replace(" ", "_")
    return text if text in allowed else default


def _date_spec(raw: Any) -> DateSpec:
    if not isinstance(raw, dict):
        return DateSpec()
    return DateSpec(
        year=_int(raw.get("year")),
        month=_int(raw.get("month")),
        season=_choice(raw.get("season"), SEASONS, "none"),
        relative=_choice(raw.get("relative"), RELATIVES, "none"),
        start=_text(raw.get("start"), 10),
        end=_text(raw.get("end"), 10),
        ago=max(0, min(_int(raw.get("ago")), 1200)),
        unit=_choice(raw.get("unit"), ("day", "week", "month", "year"), "none"),
        through=raw.get("through") is True or raw.get("span") == "until_now",
    )


def _people_count(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return -1
    return n if 0 <= n <= 50 else -1


def _filters(raw: Any) -> Filters:
    if not isinstance(raw, dict):
        return Filters()
    hour_from, hour_to = (
        _int(raw.get("hour_from")) if "hour_from" in raw else -1,
        _int(raw.get("hour_to")) if "hour_to" in raw else -1,
    )
    if not (0 <= hour_from <= 23 and 0 <= hour_to <= 24 and hour_from != hour_to):
        hour_from = hour_to = -1
    radius = _int(raw.get("radius_km"))
    return Filters(
        time_of_day=_choice(raw.get("time_of_day"), TIMES_OF_DAY, "none"),
        hour_from=hour_from,
        hour_to=hour_to,
        day_type=_choice(raw.get("day_type"), DAY_TYPES, "none"),
        orientation=_choice(raw.get("orientation"), ORIENTATIONS, "none"),
        min_people=_people_count(raw["min_people"]) if "min_people" in raw else -1,
        max_people=_people_count(raw["max_people"]) if "max_people" in raw else -1,
        quality=_choice(raw.get("quality"), QUALITIES, "none"),
        has_gps=_choice(raw.get("has_gps"), TRISTATE, "none"),
        kind=_choice(raw.get("kind"), KINDS, "none"),
        near=_text(raw.get("near"), 80),
        radius_km=radius if 0 < radius <= 20000 else 0,
        color=_choice(raw.get("color"), COLORS, "none"),
    )


def plan_from_raw(raw: Any) -> tuple[Plan, list[str]]:
    """Coerce whatever JSON the model produced into a valid :class:`Plan`."""
    warnings: list[str] = []
    if not isinstance(raw, dict):
        return Plan(intent="clarify"), ["The model did not return a JSON object."]
    clauses: list[Clause] = []
    items = raw.get("clauses")
    for entry in (items if isinstance(items, list) else [])[:MAX_CLAUSES]:
        if not isinstance(entry, dict):
            warnings.append("Ignored a malformed clause.")
            continue
        query = _text(entry.get("query"))
        engines_raw = entry.get("engines")
        engines = tuple(
            dict.fromkeys(
                e for e in (_choice(x, ENGINES, "") for x in (engines_raw if isinstance(engines_raw, list) else [])) if e
            )
        )
        if not query or not engines:
            warnings.append(f"Ignored an incomplete clause ({query or 'empty query'}).")
            continue
        clauses.append(Clause(engines=engines, query=query, exclude=entry.get("exclude") is True))
    return (
        Plan(
            intent=_choice(raw.get("intent"), INTENTS, "clarify"),
            clauses=tuple(clauses),
            match=_choice(raw.get("match"), ("all", "any"), "all"),
            date=_date_spec(raw.get("date")),
            filters=_filters(raw.get("filters")),
            scope=_choice(raw.get("scope"), ("library", "previous"), "library"),
            all_photos=raw.get("all_photos") is True,
            folder_name=_text(raw.get("folder_name"), 300),
            message=_text(raw.get("message"), 600),
        ),
        warnings,
    )
