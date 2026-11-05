"""Measure, on THIS machine, how well the model understands messages and how fast everything answers. Standard library only.

    python -m atlas.evaluate                 # the model's understanding, by difficulty level (needs only Ollama)
    python -m atlas.evaluate --live http://atlas.localhost:8000    # also: real questions through a running Atlas, with timings per path

The cases live in ``eval/cases.json`` (levels 1 to 5: plain, other wording, several parts, follow-ups, reasoning). A case is understood correctly when
the model picks the right apps, says plain conversation or not correctly, and decides correctly whether the user asked to SEE pictures or documents.
Every message is understood by the model alone: there is no word-rule fallback to compare against."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .assistant import Assistant, Plan
from .registry import load
from .upstream import Upstreams

DEFAULT_CASES = Path(__file__).resolve().parents[2] / "eval" / "cases.json"


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cases, list):
        raise ValueError(f"{path}: expected a list of cases")
    return cases


def understood(plan: Plan | None, expect: dict[str, Any]) -> bool:
    """Did the plan get the apps, plain-conversation and what-to-show decisions right?"""
    if plan is None:
        return False
    chat = plan.chat or not plan.apps
    return (
        {m.id for m in plan.apps} == set(expect["apps"])
        and chat == bool(expect["chat"])
        and plan.show.get("photos", False) == bool(expect["photos"])
        and plan.show.get("documents", False) == bool(expect["documents"])
    )


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    return ordered[min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1)))]


def run_understanding(assistant: Assistant, cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each case, planned by the model (timed) and scored against what was expected."""
    results = []
    for case in cases:
        history = case.get("history", [])
        started = time.perf_counter()
        model = assistant.model_plan(case["text"], history)
        seconds = time.perf_counter() - started
        results.append(
            {
                "level": case["level"],
                "text": case["text"],
                "model_ok": understood(model, case["expect"]),
                "model_answered": model is not None,
                "seconds": seconds,
                "got": None if model is None else {"apps": [m.id for m in model.apps], "chat": model.chat, "show": model.show},
                "expected": case["expect"],
            }
        )
    return results


def summarise(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for level in sorted({r["level"] for r in results}):
        group = [r for r in results if r["level"] == level]
        times = [r["seconds"] for r in group if r["model_answered"]]
        rows.append(
            {
                "level": level,
                "cases": len(group),
                "model": sum(r["model_ok"] for r in group) / len(group),
                "p50": statistics.median(times) if times else 0.0,
                "p95": percentile(times, 95),
            }
        )
    return rows


def run_live(base_url: str, cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Real questions through a running Atlas (it needs the apps and the model up): which path answered, and how long it took."""
    parts = urlsplit(base_url)
    out = []
    for case in cases:
        body = json.dumps({"text": case["text"], "conv": "evaluation", "history": case.get("history", [])}).encode()
        conn = http.client.HTTPConnection("127.0.0.1", parts.port or 8000, timeout=120)
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
            how = data.get("how", "error") if response.status == 200 else f"http {response.status}"
            answered = sum(1 for p in data.get("parts", []) if p.get("ok"))
        except (OSError, http.client.HTTPException, ValueError):
            how, answered = "unreachable", 0
        finally:
            conn.close()
        out.append({"level": case["level"], "text": case["text"], "how": how, "answered": answered, "seconds": time.perf_counter() - started})
    return out


def print_understanding(rows: list[dict[str, Any]], results: list[dict[str, Any]]) -> None:
    print("\nHow well the model understands (by level)      model   median   slowest")
    names = {1: "1 plain", 2: "2 other wording", 3: "3 several parts", 4: "4 follow-ups", 5: "5 reasoning"}
    for r in rows:
        print(f"  {names.get(r['level'], r['level']):<28} {r['cases']:>3} cases   {r['model']:>5.0%}      {r['p50']:>5.2f}s   {r['p95']:>5.2f}s")
    total = len(results)
    print(f"  {'all':<28} {total:>3} cases   {sum(r['model_ok'] for r in results) / total:>5.0%}")
    if not any(r["model_answered"] for r in results):
        print("\nThe model gave no usable plan for any case: is Ollama running at the address above?")
    for r in results:
        if not r["model_ok"]:
            print(f"\n  MISSED (level {r['level']}): {r['text']}\n     expected {r['expected']}\n     got      {r['got']}")


def print_live(results: list[dict[str, Any]]) -> None:
    print("\nReal questions through Atlas (which path answered, and how long)")
    for how in sorted({r["how"] for r in results}):
        group = [r["seconds"] for r in results if r["how"] == how]
        print(f"  {how:<12} {len(group):>3} questions   median {statistics.median(group):>6.2f}s   slowest {max(group):>6.2f}s")
    slow = [r for r in results if r["seconds"] > 10]
    if slow:
        print(f"\n  Over 10 seconds ({len(slow)}):")
        for r in slow:
            print(f"    {r['seconds']:>6.1f}s  [{r['how']}] {r['text']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Test the model's understanding and the speed of every answer.")
    ap.add_argument("--model-url", default=os.environ.get("ATLAS_MODEL_URL", "http://127.0.0.1:11434"))
    ap.add_argument("--modules", type=Path, default=Path(os.environ.get("ATLAS_MODULES_DIR", "modules.d")))
    ap.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    ap.add_argument("--live", metavar="URL", help="also ask the cases through a running Atlas, for example http://atlas.localhost:8000")
    ap.add_argument("--min-accuracy", type=float, default=0.0, help="exit with an error if the model's overall understanding is below this (0 to 1)")
    args = ap.parse_args(argv)
    modules = load(args.modules)
    assistant = Assistant(modules, Upstreams(modules), args.model_url)
    cases = load_cases(args.cases)
    print(f"Model at {args.model_url}: {assistant.model.model() or 'not reachable'}. {len(cases)} cases.")
    assistant.model.warm()
    results = run_understanding(assistant, cases)
    print_understanding(summarise(results), results)
    if args.live:
        print_live(run_live(args.live, cases))
    accuracy = sum(r["model_ok"] for r in results) / len(results)
    return 0 if accuracy >= args.min_accuracy else 1


if __name__ == "__main__":
    sys.exit(main())
