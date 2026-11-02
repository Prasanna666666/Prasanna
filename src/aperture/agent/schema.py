"""The query plan: what the LLM must produce and how it is validated.

A plan is a small *boolean* structure - clauses combined with AND (default) or
OR, optional NOT per clause - not a bag of fuzzy weights.  Set logic is what
gives Aperture its precision: a photo is returned only if it satisfies the
constraints, never because it half-matched several of them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..search.dates import RELATIVE, DateSpec

ENGINES = ("visual", "text", "path", "person", "place")
INTENTS = ("find", "count", "export", "chat", "clarify")
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
    scope: str = "library"  # "previous" = refine the last result set
    all_photos: bool = False  # only when the user explicitly asks for everything
    folder_name: str = ""
    message: str = ""

    @property
    def has_constraints(self) -> bool:
        return bool(self.clauses) or not self.date.is_empty or self.all_photos


_DATE_PROPS: dict[str, Any] = {
    "year": {"type": "integer"},
    "month": {"type": "integer"},
    "season": {"type": "string", "enum": list(SEASONS)},
    "relative": {"type": "string", "enum": list(RELATIVES)},
    "start": {"type": "string"},
    "end": {"type": "string"},
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
        "folder_name": {"type": "string"},
    },
    "required": ["intent", "message", "scope", "match", "all_photos", "clauses", "date", "folder_name"],
}


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
            scope=_choice(raw.get("scope"), ("library", "previous"), "library"),
            all_photos=raw.get("all_photos") is True,
            folder_name=_text(raw.get("folder_name"), 300),
            message=_text(raw.get("message"), 600),
        ),
        warnings,
    )
