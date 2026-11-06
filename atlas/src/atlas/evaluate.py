"""Measure, on THIS machine, whether the assistant uses the right parts of the app and how fast it answers. Standard library only.

    python -m atlas.evaluate --live http://atlas.localhost:8000

The cases live in ``eval/cases.json`` (levels 1 to 5: plain, other wording, several parts, follow-ups, reasoning). Each is sent through a running Atlas
(the apps and the model must be up). A case is handled correctly when the assistant used at least the parts the question needs (it may use more: a question
can chain tools), used none for plain conversation, and showed pictures or files exactly when the person asked to see them."""

from __future__ import annotations

import argparse
import http.client
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

DEFAULT_CASES = Path(__file__).resolve().parents[2] / "eval" / "cases.json"


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cases, list):
        raise ValueError(f"{path}: expected a list of cases")
    return cases


def handled(reply: dict[str, Any] | None, expect: dict[str, Any]) -> bool:
    """Did the assistant use the parts the question needs, and show pictures or files only when asked?"""
    if reply is None:
        return False
    routed = set(reply.get("routed", []))
    needed = set(expect["apps"])
    show = reply.get("show", {})
    return (
        needed <= routed
        and (bool(expect["apps"]) or not routed)
        and bool(show.get("photos", False)) == bool(expect["photos"])
        and bool(show.get("documents", False)) == bool(expect["documents"])
    )


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    return ordered[min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1)))]


def ask(base_url: str, case: dict[str, Any]) -> tuple[dict[str, Any] | None, float]:
    """One case through a running Atlas: its reply (None if it could not be reached or refused) and how long it took."""
    parts = urlsplit(base_url)
    body = json.dumps({"text": case["text"], "conv": "evaluation", "history": case.get("history", [])}).encode()
    conn = http.client.HTTPConnection("127.0.0.1", parts.port or 8000, timeout=180)
    started = time.perf_counter()
    try:
        conn.request(
            "POST",
            "/_atlas/api/chat",
            body=body,
            headers={"Host": parts.netloc, "Origin": f"{parts.scheme}://{parts.netloc}", "X-Atlas": "1", "Content-Type": "application/json"},
        )
        response = conn.getresponse()
        data = json.loads(response.read())
        reply = data if response.status == 200 and isinstance(data, dict) else None
    except (OSError, http.client.HTTPException, ValueError):
        reply = None
    finally:
        conn.close()
    return reply, time.perf_counter() - started


def run(base_url: str, cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for case in cases:
        reply, seconds = ask(base_url, case)
        results.append(
            {
                "level": case["level"],
                "text": case["text"],
                "ok": handled(reply, case["expect"]),
                "answered": reply is not None and any(p.get("ok") for p in reply.get("parts", [])),
                "seconds": seconds,
                "got": None if reply is None else {"used": reply.get("routed"), "show": reply.get("show")},
                "expected": case["expect"],
            }
        )
    return results


def summarise(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for level in sorted({r["level"] for r in results}):
        group = [r for r in results if r["level"] == level]
        times = [r["seconds"] for r in group]
        rows.append(
            {
                "level": level,
                "cases": len(group),
                "right": sum(r["ok"] for r in group) / len(group),
                "answered": sum(r["answered"] for r in group) / len(group),
                "p50": statistics.median(times),
                "p95": percentile(times, 95),
            }
        )
    return rows


def print_report(rows: list[dict[str, Any]], results: list[dict[str, Any]]) -> None:
    print("\nThe assistant, by level                          right   answered   median   slowest")
    names = {1: "1 plain", 2: "2 other wording", 3: "3 several parts", 4: "4 follow-ups", 5: "5 reasoning"}
    for r in rows:
        print(
            f"  {names.get(r['level'], r['level']):<28} {r['cases']:>3} cases   {r['right']:>5.0%}    {r['answered']:>5.0%}    {r['p50']:>6.1f}s  {r['p95']:>6.1f}s"
        )
    total = len(results)
    print(f"  {'all':<28} {total:>3} cases   {sum(r['ok'] for r in results) / total:>5.0%}    {sum(r['answered'] for r in results) / total:>5.0%}")
    for r in results:
        if not r["ok"]:
            print(f"\n  MISSED (level {r['level']}): {r['text']}\n     expected {r['expected']}\n     got      {r['got']}")
    slow = [r for r in results if r["seconds"] > 30]
    if slow:
        print(f"\n  Over 30 seconds ({len(slow)}):")
        for r in slow:
            print(f"    {r['seconds']:>6.1f}s  {r['text']}")


def unreachable(base_url: str) -> str:
    """Why Atlas cannot be asked at all, in words ('' when it answers): checked once before the cases, so a stopped app is not reported as 34 wrong answers."""
    parts = urlsplit(base_url)
    conn = http.client.HTTPConnection("127.0.0.1", parts.port or 8000, timeout=10)
    try:
        conn.request("GET", "/", headers={"Host": parts.netloc})
        status = conn.getresponse().status
    except (OSError, http.client.HTTPException) as exc:
        return f"nothing answers on 127.0.0.1:{parts.port or 8000} ({exc.__class__.__name__}). Is the app running? Start the apps: orbit/scripts/up.sh, library/scripts/up.sh, then atlas/up.sh"
    finally:
        conn.close()
    return "" if status < 500 else f"Atlas answered with an error (HTTP {status}). Look at its log: docker compose logs"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Test that the assistant uses the right parts of the app, and how fast it answers.")
    ap.add_argument("--live", metavar="URL", required=True, help="a running Atlas, for example http://atlas.localhost:8000")
    ap.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    ap.add_argument("--min-accuracy", type=float, default=0.0, help="exit with an error if the share of cases handled correctly is below this (0 to 1)")
    args = ap.parse_args(argv)
    cases = load_cases(args.cases)
    why = unreachable(args.live)
    if why:
        print(f"Cannot evaluate: {why}")
        return 2
    results = run(args.live, cases)
    print_report(summarise(results), results)
    accuracy = sum(r["ok"] for r in results) / len(results)
    return 0 if accuracy >= args.min_accuracy else 1


if __name__ == "__main__":
    sys.exit(main())
