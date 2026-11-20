"""The answer envelope: what was claimed, what supports it, what was not searched, and how far it can be trusted.

An answer is `verified` only if every citation resolves exactly and every figure and numeric date in it appears in the cited text. A citation that
fails replaces the answer with a plain refusal. Language support is never claimed beyond what was measured (G-019).
"""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from typing import Any

from kit.audit import unproven_figures

from .contracts import validate
from .evidence import CitationError, SourceStore, check_citation
from .rules import Rules, load_rules
from .values import LanguageIn

SAFE_TEXT = "I could not check this answer against your sources, so I am not giving it."
WITHHELD_TEXT = "This answer is no longer available because permission to one or more of the sources it was built from was revoked."
STOPPED_TEXT = "The task was stopped because permission to one or more sources changed after it had started. No answer was delivered."
DENIED_TEXT = "Nothing was searched: Atlas is not allowed to search the kinds of source that were asked for."
NUMERIC_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b")


def _language(info: LanguageIn, rules: Rules) -> tuple[dict[str, Any], list[str]]:
    out: dict[str, Any] = {k: v for k, v in (("detected", info.detected), ("requested", info.requested), ("confidence", info.confidence)) if v is not None}
    low = info.confidence is not None and info.confidence < rules.low_confidence_below
    if info.path_unsupported:
        out["support_status"], limits = "unsupported", ["language_unsupported"]
    elif low:
        out["support_status"], limits = "unsupported", ["low_confidence"]
    elif info.detected and info.detected.lower() in rules.measured_languages:
        out["support_status"], limits = "measured", []
    else:
        out["support_status"], limits = "unmeasured", ["language_unmeasured"]
    return out, limits


def _unproven_dates(draft: str, cited: Sequence[str]) -> list[str]:
    body = "\n".join(cited)
    return sorted({d for d in NUMERIC_DATE.findall(draft) if d not in body})


def _check_citations(citations: Sequence[dict[str, Any]], store: SourceStore, retrieved: Sequence[dict[str, Any]]) -> tuple[list[str], list[int]]:
    texts: list[str] = []
    failed: list[int] = []
    for position, citation in enumerate(citations):
        try:
            if citation["evidence"] not in retrieved:
                raise CitationError("not_retrieved")  # a model may cite only what it was given
            texts.append(check_citation(citation, store))
        except CitationError:
            failed.append(position)
    return texts, failed


def _status(failed: list[int], citations: Sequence[Any], figures: list[float], dates: list[str], support: str) -> str:
    if failed:
        return "failed"
    if not citations:
        return "unverified"
    if figures or dates or support == "unsupported":
        return "partially_verified"
    return "verified"


@dataclass(frozen=True)
class AnswerInput:
    task_id: str
    draft: str
    citations: Sequence[dict[str, Any]]
    requested: Sequence[str]
    denied: Sequence[dict[str, str]]
    retrieved: Sequence[dict[str, Any]] = ()
    truncated: bool = False
    partial: bool = False
    language: LanguageIn = field(default_factory=LanguageIn)


def build_envelope(item: AnswerInput, store: SourceStore, rules: Rules | None = None) -> dict[str, Any]:
    rules = rules or load_rules()
    cited, failed = _check_citations(item.citations, store, item.retrieved)
    figures = unproven_figures(item.draft, cited or [""])
    dates = _unproven_dates(item.draft, cited)
    language, limits = _language(item.language, rules)
    not_searched = [dict(d) for d in item.denied]
    disclose = rules.discloses_attachments(item.requested)
    if disclose and all(n["source_type"] != rules.attachment_type for n in not_searched):
        not_searched.append({"source_type": rules.attachment_type, "reason_code": "deferred_decision"})  # attachment contents are not searched until G-O18
    limits = [*limits, *(["attachments_not_searched"] if disclose else [])]
    limits += ["source_type_not_searched"] if item.denied else []
    limits += ["figures_unproven"] if figures else []
    limits += ["dates_unproven"] if dates else []
    limits += ["context_truncated"] if item.truncated else []
    limits += ["partial_work"] if item.partial else []
    status = _status(failed, item.citations, figures, dates, language["support_status"])
    envelope = {
        "task_id": item.task_id,
        "answer": SAFE_TEXT if failed else item.draft,
        "citations": list(item.citations),
        "verification": {"status": status, "unproven_figures": figures, "unproven_dates": dates, "citation_failures": failed},
        "language": language,
        "limitations": list(dict.fromkeys(limits)),
        "not_searched": not_searched,
    }
    validate("AnswerEnvelope", envelope)
    return envelope


def denied_envelope(task_id: str, requested: Sequence[str], denied: Sequence[dict[str, str]]) -> dict[str, Any]:
    """The answer for a task whose sources were all denied: nothing was searched, and it says so."""
    envelope = {
        "task_id": task_id,
        "answer": DENIED_TEXT,
        "citations": [],
        "verification": {"status": "unverified", "unproven_figures": [], "unproven_dates": [], "citation_failures": []},
        "language": {"support_status": "unmeasured"},
        "limitations": ["source_type_not_searched"],
        "not_searched": [dict(d) for d in denied] or [{"source_type": s, "reason_code": "no_grant"} for s in requested],
    }
    validate("AnswerEnvelope", envelope)
    return envelope


def _after_retrieval(task_id: str, text: str, limitation: str, denied: Sequence[dict[str, str]], used: Collection[str]) -> dict[str, Any]:
    """An answer for a task whose sources were retrieved before a permission changed. Retrieved sources are 'withheld', never 'not searched'."""
    envelope = {
        "task_id": task_id,
        "answer": text,
        "citations": [],
        "verification": {"status": "unverified", "unproven_figures": [], "unproven_dates": [], "citation_failures": []},
        "language": {"support_status": "unmeasured"},
        "limitations": [limitation],
        "not_searched": [dict(d) for d in denied if d["source_type"] not in used],
        "withheld_sources": [dict(d) for d in denied if d["source_type"] in used],
    }
    validate("AnswerEnvelope", envelope)
    return envelope


def withheld_envelope(task_id: str, denied: Sequence[dict[str, str]], used: Collection[str]) -> dict[str, Any]:
    """An answer WAS produced, then permission to a source it was built from was revoked: the previous answer is withheld."""
    return _after_retrieval(task_id, WITHHELD_TEXT, "answer_withheld", denied, used)


def stopped_envelope(task_id: str, denied: Sequence[dict[str, str]], used: Collection[str]) -> dict[str, Any]:
    """Retrieval happened but no answer had been produced when permission changed: the task stopped and there is nothing to withhold."""
    return _after_retrieval(task_id, STOPPED_TEXT, "task_stopped_no_answer", denied, used)
