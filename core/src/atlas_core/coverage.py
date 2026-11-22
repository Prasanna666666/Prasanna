"""Turns what the source indexes report into the API 1.1 `Coverage` object, and decides which limitations that coverage requires.

Honest by construction: an index that is still scanning, paused or holding pending items is `indexing`; failed or unsupported items make it `partial`; only a finished scan with
nothing pending, failed or unsupported is `complete`. A source type the Core cannot report on contributes an unknown total (`null`) and a `partial` state, never a guess.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

FAILED_REASON = {"corrupt": "corrupt", "oversized": "too_large", "unreadable": "extraction_failed", "malformed_message": "corrupt", "timeout": "timeout"}
Provider = Callable[[], Mapping[str, Any]]


def _bump(into: dict[str, int], key: str, amount: int) -> None:
    if amount > 0:
        into[key] = into.get(key, 0) + amount


def build_coverage(source_types: Iterable[str], providers: Mapping[str, Provider], now: datetime) -> dict[str, Any]:
    searched = total = 0
    unknown = scanning = False
    pending: dict[str, int] = {}
    failed: dict[str, int] = {}
    for source_type in sorted(set(source_types)):
        provider = providers.get(source_type)
        if provider is None:
            unknown = True
            continue
        report = provider()
        searched += int(report["searched"])
        total += int(report["total"])
        _bump(pending, "not_yet_indexed", int(report["pending"]))
        _bump(pending, "unsupported_source", int(report.get("unsupported", 0)))
        counted = 0
        for reason, count in report.get("failed_reasons", {}).items():
            _bump(failed, FAILED_REASON.get(reason, "extraction_failed"), int(count))
            counted += int(count)
        _bump(failed, "extraction_failed", int(report["failed"]) - counted)
        scanning = scanning or not report["scan_complete"] or report["paused"] is not None
    if scanning or pending.get("not_yet_indexed"):
        state = "indexing"
        pending.setdefault("not_yet_indexed", 0)
    elif pending or failed or unknown:
        state = "partial"
        if unknown and not pending and not failed:
            pending["not_yet_indexed"] = 0  # coverage of that source is not reported: partial with an unknown total, never "complete"
    else:
        state = "complete"
    return {
        "state": state,
        "searched": searched,
        "total": None if unknown else total,
        "pending": [{"category": k, "count": v} for k, v in sorted(pending.items())],
        "failed": [{"reason_code": k, "count": v} for k, v in sorted(failed.items())],
        "as_of": now.astimezone(UTC).isoformat(timespec="seconds"),
    }


def required_limitations(coverage: Mapping[str, Any]) -> list[str]:
    """The limitations the 1.1 contract ties to this coverage (it rejects an envelope that has one without the other)."""
    out = ["indexing_incomplete"] if coverage["state"] == "indexing" else []
    categories = {p["category"] for p in coverage["pending"]}
    if "unsupported_source" in categories:
        out.append("source_unsupported")
    if "os_access" in categories:
        out.append("os_access_missing")
    if coverage["failed"] or (coverage["state"] == "partial" and "not_yet_indexed" in categories):
        out.append("partial_work")
    return out
