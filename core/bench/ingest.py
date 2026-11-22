"""Ingestion and search benchmark over SYNTHETIC data at the owner's stated scale (about 26,000 mail messages and 1,400 documents), WP3.6.

Usage (from core/):  python bench/ingest.py [--mail N] [--docs N] [--queries N] [--json]

What the numbers are: wall-clock times of the Python reference Core's indexes on the machine named in the report (printed with it). They are NOT target-Mac numbers: the Mac mini
with a real Mail store, a real disk and FileVault is a different machine, and no claim about it follows from a run on Linux. They are also not quality figures. The data is
generated (invented words, no real text); the mailbox is in memory, so the reading cost of a real Mail store is not included.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import random
import resource
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from conftest import KEY

from atlas_core.access import AllowAll
from atlas_core.documents import DocumentIndex
from atlas_core.mail import InMemoryMailbox, MailIndex

OWNER_MAIL, OWNER_DOCS = 26_000, 1_400
WORDS = (
    "invoice",
    "meeting",
    "budget",
    "report",
    "contract",
    "payment",
    "schedule",
    "review",
    "travel",
    "support",
    "project",
    "delivery",
    "quote",
    "renewal",
    "agenda",
    "notes",
)


def sentence(rng: random.Random, n: int) -> str:
    return " ".join(rng.choice(WORDS) + str(rng.randrange(1000)) for _ in range(n))


def make_mail(rng: random.Random, count: int) -> list[dict]:
    return [
        {
            "message_id": f"m{i:07d}@example.invalid",
            "sender": f"person{i % 300}@example.invalid",
            "date": f"{2015 + i % 11}-{1 + i % 12:02d}-{1 + i % 27:02d}T09:00:00+00:00",
            "subject": sentence(rng, 4),
            "body": "\n\n".join(sentence(rng, 25) for _ in range(3)),
        }
        for i in range(count)
    ]


def make_docs(rng: random.Random, folder: Path, count: int) -> None:
    for i in range(count):
        sub = folder / f"d{i % 40:02d}"
        sub.mkdir(exist_ok=True)
        (sub / f"doc{i:05d}.txt").write_text("\n\n".join(sentence(rng, 40) for _ in range(6)), encoding="utf-8")


def drain(index, step: int = 200) -> int:
    index.scan()
    slices = 0
    while index.run(step)["pending"]:
        slices += 1
    return slices + 1


def percentile(values: list[float], q: float) -> float:
    return sorted(values)[min(len(values) - 1, int(q * len(values)))]


def queries(index, source_type: str, rng: random.Random, count: int) -> dict:
    samples = []
    for _ in range(count):
        q = " ".join(rng.choice(WORDS) + str(rng.randrange(1000)) for _ in range(3)) + " " + rng.choice(WORDS)
        began = time.perf_counter()
        list(index.search(source_type, q))
        samples.append((time.perf_counter() - began) * 1000)
    return {"queries": count, "p50_ms": round(statistics.median(samples), 2), "p95_ms": round(percentile(samples, 0.95), 2), "max_ms": round(max(samples), 2)}


def measure(mail: int, docs: int, query_count: int, seed: int = 1) -> dict:
    rng = random.Random(seed)
    out: dict = {
        "label": {
            "machine": f"{platform.system()} {platform.machine()}, Python {platform.python_version()}, {os.cpu_count()} CPUs",
            "data": "synthetic, generated; in-memory mailbox; local temp disk",
            "meaning": "developer-machine wall-clock of the Python reference Core. NOT target-Mac evidence (Mail store, disk and FileVault differ) and NOT a quality measure.",
            "scale": {"mail": mail, "docs": docs, "owner_scale": {"mail": OWNER_MAIL, "docs": OWNER_DOCS}},
        }
    }
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        began = time.perf_counter()
        index = MailIndex(root / "mail.db", KEY, InMemoryMailbox(make_mail(rng, mail)), "mail", access=AllowAll())
        slices = drain(index)
        out["mail"] = {
            "index_seconds": round(time.perf_counter() - began, 2),
            "slices": slices,
            "coverage": {k: v for k, v in index.coverage().items() if k in ("total", "searched", "pending", "failed", "complete")},
        }
        out["mail"]["search"] = queries(index, "mail", rng, query_count)
        index.close()
        folder = root / "docs"
        folder.mkdir()
        make_docs(rng, folder, docs)
        began = time.perf_counter()
        dindex = DocumentIndex(root / "docs.db", KEY, folder, "documents", access=AllowAll())
        slices = drain(dindex)
        out["documents"] = {
            "index_seconds": round(time.perf_counter() - began, 2),
            "slices": slices,
            "coverage": {k: v for k, v in dindex.coverage().items() if k in ("total", "searched", "pending", "failed", "complete")},
        }
        out["documents"]["search"] = queries(dindex, "documents", rng, query_count)
        dindex.close()
        out["db_bytes"] = {p.name: p.stat().st_size for p in sorted(root.glob("*.db"))}
    out["peak_rss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mail", type=int, default=OWNER_MAIL)
    parser.add_argument("--docs", type=int, default=OWNER_DOCS)
    parser.add_argument("--queries", type=int, default=50)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = measure(args.mail, args.docs, args.queries)
    print(json.dumps(report, indent=None if args.json else 2))


if __name__ == "__main__":
    main()
