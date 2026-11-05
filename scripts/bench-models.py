#!/usr/bin/env python3
"""Compare local Ollama models on speed and memory, on THIS Mac. Talks only to your local Ollama; prints a table.

    python3 scripts/bench-models.py                      # compares ministral-3:3b and llama3.2:3b (must be installed)
    python3 scripts/bench-models.py MODEL [MODEL ...]    # any installed models
    python3 scripts/bench-models.py --no-plan            # skip the Aperture search-plan test (no aperture import needed)

Safety: it never stops a model that is already running. If one is loaded it tells you and exits (stop it yourself with
`ollama stop MODEL`, or pass --unload to let this script do it). It only unloads the model it loaded itself.

For each model, one at a time:
  load      seconds to load the model into memory from cold
  tok/s     generation speed (higher is better)
  plan s    average seconds for a real Aperture search plan (3 sample requests; needs `aperture` importable)
  model MB  memory Ollama reports for the loaded model
  peak MB   highest total memory used by Ollama processes while testing
  swap +MB  how much the Mac started swapping to disk (high = the system will feel hung)
  min free  lowest "memory free" percentage macOS reported (low = memory pressure)
Close other big apps first so the numbers are fair. Accuracy is measured separately: `aperture eval-plans`.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import date

DEFAULT_MODELS = ["ministral-3:3b", "llama3.2:3b"]
SAMPLE_REQUESTS = ["show me photos of Anna at the beach last summer", "how many pictures do I have from 2019?", "sunset photos"]


def post(url: str, path: str, body: dict | None = None, timeout: int = 900) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def swap_used_mb() -> float | None:
    m = re.search(r"used = ([\d.]+)M", _run(["sysctl", "-n", "vm.swapusage"]))
    return float(m.group(1)) if m else None


def free_percent() -> float | None:
    m = re.search(r"free percentage: (\d+)%", _run(["memory_pressure"]))
    return float(m.group(1)) if m else None


def ollama_rss_mb() -> float:
    total = 0
    for line in _run(["ps", "-axo", "rss=,comm="]).splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and "ollama" in parts[1].lower() and parts[0].isdigit():
            total += int(parts[0])
    return total / 1024


class Poller(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.stop_flag = threading.Event()
        self.peak_mb = 0.0
        self.min_free: float | None = None

    def run(self) -> None:
        while not self.stop_flag.is_set():
            self.peak_mb = max(self.peak_mb, ollama_rss_mb())
            f = free_percent()
            if f is not None:
                self.min_free = f if self.min_free is None else min(self.min_free, f)
            self.stop_flag.wait(0.5)


def running_models(url: str) -> list[str]:
    return [m.get("name") or m.get("model") for m in post(url, "/api/ps").get("models", [])]


def unload(url: str, model: str) -> None:
    post(url, "/api/generate", {"model": model, "prompt": "", "keep_alive": 0, "stream": False})
    time.sleep(2)


def plan_seconds(url: str, model: str) -> float | None:
    try:
        from aperture.agent import planner
        from aperture.agent.llm import OllamaClient
        from aperture.agent.schema import plan_schema
    except ImportError:
        return None
    style = planner.plan_style()
    client = OllamaClient(url, model, timeout=600.0, keep_alive="2m")
    ctx = planner.PlannerContext(today=date.today())
    times = []
    for req in SAMPLE_REQUESTS:
        t = time.time()
        client.complete_json(planner.system_prompt(style), planner.Planner._user_prompt(req, ctx), plan_schema(style))
        times.append(time.time() - t)
    return sum(times) / len(times)


def bench(url: str, model: str, with_plan: bool) -> dict:
    swap0, poller = swap_used_mb(), Poller()
    poller.start()
    t = time.time()
    post(url, "/api/generate", {"model": model, "prompt": "", "keep_alive": "2m", "stream": False})
    load_s = time.time() - t
    running = [m for m in post(url, "/api/ps").get("models", []) if model in (m.get("name"), m.get("model"))]
    model_mb = (running[0].get("size", 0) / 1e6) if running else None
    out = post(
        url,
        "/api/generate",
        {
            "model": model,
            "prompt": "Write 80 words about Paris.",
            "stream": False,
            "options": {"temperature": 0, "num_ctx": 4096},
        },
    )
    tok_s = out["eval_count"] / (out["eval_duration"] / 1e9) if out.get("eval_duration") else 0.0
    plan_s = plan_seconds(url, model) if with_plan else None
    poller.stop_flag.set()
    poller.join(timeout=2)
    swap1 = swap_used_mb()
    unload(url, model)  # only the model this script loaded
    return {
        "model": model,
        "load_s": load_s,
        "tok_s": tok_s,
        "plan_s": plan_s,
        "model_mb": model_mb,
        "peak_mb": poller.peak_mb,
        "swap_mb": (swap1 - swap0) if swap0 is not None and swap1 is not None else None,
        "min_free": poller.min_free,
    }


def fmt(v, spec: str, none: str = "n/a") -> str:
    return none if v is None else format(v, spec)


def table(rows: list[dict]) -> str:
    head = f"{'model':20} {'load s':>7} {'tok/s':>7} {'plan s':>7} {'model MB':>9} {'peak MB':>8} {'swap +MB':>9} {'min free':>9}"
    lines = [head, "-" * len(head)]
    for r in rows:
        lines.append(
            f"{r['model']:20} {fmt(r['load_s'], '7.1f')} {fmt(r['tok_s'], '7.1f')} {fmt(r['plan_s'], '7.1f')} "
            f"{fmt(r['model_mb'], '9.0f')} {fmt(r['peak_mb'], '8.0f')} {fmt(r['swap_mb'], '9.0f')} "
            f"{fmt(r['min_free'], '8.0f') + ('%' if r['min_free'] is not None else '')}".rstrip()
        )
    return "\n".join(lines)


def verdict(rows: list[dict]) -> str:
    if not rows:
        return "No model could be measured."
    fastest = max(rows, key=lambda r: r["tok_s"])
    lightest = min(rows, key=lambda r: r["peak_mb"] or float("inf"))
    notes = [
        f"Fastest: {fastest['model']} ({fastest['tok_s']:.1f} tok/s).",
        f"Lightest on memory: {lightest['model']} (peak {lightest['peak_mb']:.0f} MB).",
    ]
    for r in rows:
        bad = []
        if r["swap_mb"] is not None and r["swap_mb"] > 300:
            bad.append(f"started swapping (+{r['swap_mb']:.0f} MB)")
        if r["min_free"] is not None and r["min_free"] < 15:
            bad.append(f"memory free dropped to {r['min_free']:.0f}%")
        notes.append(f"{r['model']}: " + ("RISK of hanging the system: " + ", ".join(bad) if bad else "stayed comfortable."))
    return "\n".join(notes)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Compare local Ollama models on speed and memory")
    ap.add_argument("models", nargs="*", default=DEFAULT_MODELS)
    ap.add_argument("--url", default="http://127.0.0.1:11434")
    ap.add_argument("--no-plan", action="store_true")
    ap.add_argument("--unload", action="store_true", help="allow stopping models that are already running")
    a = ap.parse_args(argv)
    try:
        installed = {m["name"] for m in post(a.url, "/api/tags").get("models", [])}
    except OSError as e:
        print(f"Cannot reach Ollama at {a.url} ({e}). Open the Ollama app first.")
        return 2
    busy = running_models(a.url)
    if busy and not a.unload:
        print(
            "A model is already running: " + ", ".join(busy) + ".\nI will not stop it (something may be using it, and the "
            "memory numbers would be wrong).\nStop it yourself with:  ollama stop " + busy[0] + "\n...or run again with --unload."
        )
        return 3
    for m in busy:
        unload(a.url, m)
    rows = []
    for model in a.models:
        if model not in installed and f"{model}:latest" not in installed:
            print(f"SKIPPED {model}: not installed (ollama pull {model})")
            continue
        print(f"measuring {model} ...", flush=True)
        rows.append(bench(a.url, model, not a.no_plan))
    print("\n" + table(rows) + "\n\n" + verdict(rows))
    if rows and rows[0]["plan_s"] is None and not a.no_plan:
        print("\n(plan s is n/a: run this from your Aperture virtual environment to include the search-plan test)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
