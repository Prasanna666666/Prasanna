"""Overhead of the foundation itself, measured with stubs (no model, no retrieval, no ingestion): policy decision, contract validation, task lifecycle, and an API round trip.

Usage (from core/):  python bench/overhead.py [--runs N] [--json]

This is NOT a measurement of answer latency. Real first-useful-output and typical-answer times (retrieval + model) belong to Stage 3 and must be measured on the named
target Mac. The numbers printed here describe only the machine and Python it ran on, which are printed with them.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from conftest import World, grant, request, signed
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from atlas_core.api import CoreApi, Request
from atlas_core.contracts import validate
from atlas_core.identity import ClientRegistry

DEFAULT_RUNS = 300


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def timed(fn, runs: int) -> dict[str, float]:
    samples = []
    for _ in range(runs):
        began = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - began) * 1000)
    return {"p50_ms": round(statistics.median(samples), 4), "p95_ms": round(percentile(samples, 0.95), 4), "max_ms": round(max(samples), 4), "runs": runs}


def measure(runs: int) -> dict:
    with tempfile.TemporaryDirectory() as folder:
        world = World(Path(folder), [grant("documents")])
        key = Ed25519PrivateKey.generate()
        registry = ClientRegistry()
        registry.register("client-mac-0001", key.public_key())
        api = CoreApi(world.service, registry, world.log, world.clock)
        body = json.dumps(request(key="idem-bench-0000")).encode()
        counter = iter(range(10**9))
        sample = {"objective": "q", "source_scope": ["documents"], "budget": {"max_seconds": 10, "max_retries": 1}, "idempotency_key": "idem-key-0001"}
        results = {
            "contract_validate_TaskRequest": timed(lambda: validate("TaskRequest", sample), runs),
            "policy_decide": timed(lambda: world.service._d.policy.decide(["documents"], world.clock()), runs),
            "task_submit_and_run_with_stubs": timed(lambda: world.run_new(request(key=f"idem-{next(counter):08d}")), runs),
            "api_signed_version_roundtrip": timed(
                lambda: api.handle(Request("GET", "/v1/version", signed(key, "GET", "/v1/version", b"", world.clock()))), runs
            ),
            "api_signed_create_task": timed(lambda: api.handle(Request("POST", "/v1/tasks", signed(key, "POST", "/v1/tasks", body, world.clock()), body)), 1),
        }
    return {
        "machine": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor() or platform.machine(),
            "role": "developer container (NOT the target Mac)",
        },
        "scope": "foundation overhead with stubs; not answer latency",
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = measure(args.runs)
    print(json.dumps(report, indent=2) if args.json else report)


if __name__ == "__main__":
    main()
