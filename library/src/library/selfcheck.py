"""A reading check you can run on your own folders: every file is read the way the reader reads it, and the outcomes are counted by what the file turned out to be.
Nothing is stored and nothing leaves the machine; the report holds counts and, for the files that were not read well, a few names so you can look at them yourself."""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from . import parser, sniff

EXAMPLES = 3
ENOUGH_TEXT = 20  # characters: less than this is "no text"


def outcome(path: Path, timeout: int) -> tuple[str, str]:
    """(what the file is, how reading it went): text, table, scan, no text, or failed with the reason."""
    try:
        kind = sniff.kind_of(path)
    except (OSError, ValueError):
        return "unknown", "failed: could not be opened"
    try:
        res = parser.extract_isolated(path, timeout)
    except Exception as exc:  # noqa: BLE001 - a file that fails must be counted, never stop the check
        return kind, f"failed: {str(exc).strip().splitlines()[-1][:70] if str(exc).strip() else 'unreadable'}"
    meta = res.get("meta") or {}
    data = res.get("data") or {}
    if meta.get("ocr_pages"):
        return kind, "scan (read by character recognition)" + (", cut short" if meta.get("ocr_cut_short") else "")
    if isinstance(data.get("table"), list) and len(data["table"]) >= 3:
        return kind, "text with a table"
    if len((res.get("text") or "").strip()) >= ENOUGH_TEXT:
        return kind, "text"
    return kind, "no text found (kept by its name only)"


def check(roots: list[tuple[str, Path]], limit: int = 0, timeout: int = 120, workers: int = 2) -> dict[str, Any]:
    files = [f for _label, root in roots if root.is_dir() for f in sorted(root.rglob("*")) if f.is_file() and not f.is_symlink() and not f.name.startswith(".")]
    if limit:
        files = files[:: max(1, len(files) // limit)][:limit]  # an even sample across the folders, not the first N
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        results = list(pool.map(lambda f: outcome(f, timeout), files))
    table: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    examples: dict[str, list[str]] = defaultdict(list)
    for f, (kind, how) in zip(files, results, strict=True):
        table[kind][how] += 1
        key = f"{kind}: {how}"
        if how.startswith(("failed", "no text")) and len(examples[key]) < EXAMPLES:
            examples[key].append(f.name)
    return {"files": len(files), "by_kind": {k: dict(v) for k, v in table.items()}, "examples": dict(examples)}


def render(report: dict[str, Any]) -> str:
    lines = [f"{report['files']} files looked at", ""]
    for kind, outcomes in sorted(report["by_kind"].items(), key=lambda kv: -sum(kv[1].values())):
        lines.append(f"{kind} ({sum(outcomes.values())})")
        lines += [f"    {n:>6}  {how}" for how, n in sorted(outcomes.items(), key=lambda kv: -kv[1])]
    if report["examples"]:
        lines += ["", "To look at yourself:"]
        lines += [f"    {key}: {', '.join(names)}" for key, names in report["examples"].items()]
    return "\n".join(lines)
