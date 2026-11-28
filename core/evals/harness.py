"""The evaluation harness (WP3.4d). It runs a versioned synthetic set through the REAL pipeline (document index, policy gate, task service, citation and figure checks).

What a result means: with the scripted model used in CI, every number describes the PIPELINE (does retrieval find the right source, does a hallucinated figure, a wrong quote, an
injected instruction or a stale document get caught). It says nothing about how good a real model is; that needs the same set run on the target Mac with the real model, and the
report says so. Retrieval quality and answer quality are reported separately, per language and script. A case with a `known_gap` documents a limitation instead of hiding it.

Usage (from core/):  python evals/harness.py [--json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tests"))

from conftest import KEY, Clock, grant  # noqa: E402  (synthetic test fixtures)

from atlas_core.access import AllowAll  # noqa: E402
from atlas_core.answer import NO_EVIDENCE_TEXT  # noqa: E402
from atlas_core.documents import DocumentIndex  # noqa: E402
from atlas_core.events import SafeLog  # noqa: E402
from atlas_core.gate import ModelAnswer, ModelContext  # noqa: E402
from atlas_core.policy import InMemoryGrants, PolicyEngine  # noqa: E402
from atlas_core.service import Deps, TaskService  # noqa: E402
from atlas_core.tasks import TaskStore  # noqa: E402
from atlas_core.values import LanguageIn  # noqa: E402

SET_FILE = HERE / "set_v4.json"  # v4: a year-like amount; v3 (UC-L22): mixed-language documents and verbatim names and units; v2: bigram index
TOP_K = 8


def set_sha256(path: Path = SET_FILE) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class ScriptedModel:
    """A deterministic stand-in for a model: its behaviour is the case's `model` script. It only ever sees what the gate gives it (and records it)."""

    script: dict[str, Any]
    language: str
    seen: list[ModelContext] = field(default_factory=list)

    def generate(self, context: ModelContext) -> ModelAnswer:
        self.seen.append(context)
        mode, answer = self.script["mode"], self.script["answer"]
        lang = LanguageIn(detected=self.language, requested=self.language, confidence=0.9)
        if mode in ("abstain", "obey_injection"):
            return ModelAnswer(answer, (), lang)
        quotes = self.script.get("quotes") or [self.script["quote"]]
        citations = []
        for quote in quotes:
            hit = next((p for p in context.passages if quote in p["text"]), None)
            if hit is not None:
                shown = self.script.get("claimed_quote", quote) if mode == "wrong_quote" else quote
                citations.append({"evidence": hit["evidence"], "quote": shown})
        return ModelAnswer(answer, tuple(citations), lang)


class Retriever:
    def __init__(self, index: DocumentIndex) -> None:
        self.index, self.calls = index, []

    def search(self, source_type: str, query: str) -> Any:
        self.calls.append(source_type)
        return self.index.search(source_type, query)


def _outcome(envelope: dict[str, Any]) -> str:
    v = envelope["verification"]
    if envelope["answer"] == NO_EVIDENCE_TEXT:
        return "no_evidence"
    if v["status"] == "failed" or v["citation_failures"]:
        return "rejected"
    if not envelope["citations"] or v["unproven_figures"] or v["unproven_dates"]:
        return "ungrounded"
    return "grounded"


def _build(root: Path, data: dict[str, Any]) -> DocumentIndex:
    folder = root / "docs"
    folder.mkdir()
    for name, doc in data["documents"].items():
        (folder / name).write_text(doc["text"], encoding="utf-8")
    index = DocumentIndex(root / "index.db", KEY, folder, "documents", access=AllowAll())
    index.scan()
    while index.run(5)["pending"]:
        pass
    return index


def _check(case: dict[str, Any], envelope: dict[str, Any], model: ScriptedModel, retriever: Retriever, names: dict[str, str]) -> list[str]:
    expect, failures = case["expect"], []
    outcome = _outcome(envelope)
    if outcome != expect["outcome"]:
        failures.append(f"outcome {outcome} != {expect['outcome']}")
    cited = sorted(names.get(c["evidence"]["source_id"], "?") for c in envelope["citations"])
    if "cited" in expect and cited != sorted(expect["cited"]):
        failures.append(f"cited {cited}")
    if "unproven_figures" in expect and envelope["verification"]["unproven_figures"] != expect["unproven_figures"]:
        failures.append("unproven figures differ")
    if "not_searched" in expect and sorted(n["source_type"] for n in envelope["not_searched"]) != sorted(expect["not_searched"]):
        failures.append("not_searched differs")
    if "searched_types" in expect and sorted(set(retriever.calls)) != sorted(expect["searched_types"]):
        failures.append("searched types differ")
    if "context_must_not_contain" in expect and any(expect["context_must_not_contain"] in p["text"] for c in model.seen for p in c.passages):
        failures.append("forbidden text reached the model")
    for text in expect.get("preserved", []):  # names and units are kept exactly as the source writes them: never translated or normalised
        if not any(text in p["text"] for c in model.seen for p in c.passages):
            failures.append(f"not verbatim in the passages the model saw: {text}")
        if not any(text in c["quote"] for c in envelope["citations"]) and text not in envelope["answer"]:
            failures.append(f"not verbatim in the cited quote or the answer: {text}")
    if "answer_must_not_match" in expect and re.search(expect["answer_must_not_match"], envelope["answer"]):
        failures.append("answer matched a forbidden pattern")
    return failures


def run(path: Path = SET_FILE) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    results, retrieval = [], []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for number, case in enumerate(data["cases"]):
            work = root / f"c{number}"
            work.mkdir()
            index = _build(work, data)
            for name, text in case.get("mutate_after_index", {}).items():
                (work / "docs" / name).write_text(text, encoding="utf-8")  # the file changes after it was indexed: it must not be answered from
            names = {row["source_id"]: row["rel_path"] for row in index._conn.execute("SELECT source_id, rel_path FROM docs")}
            retriever = Retriever(index)
            model = ScriptedModel(case["model"], case["language"])
            store = TaskStore(work / "tasks.db", KEY)
            clock = Clock()
            service = TaskService(
                Deps(store, PolicyEngine(InMemoryGrants([grant("documents")])), retriever, model, index, SafeLog(lambda _: None), clock=clock)
            )
            record, _ = service.submit(
                {
                    "objective": case["question"],
                    "source_scope": case.get("scope", ["documents"]),
                    "budget": {"max_seconds": 120, "max_retries": 1},
                    "idempotency_key": f"eval-{number:04d}",
                }
            )
            service.run(record["task_id"])
            envelope = service.answer(record["task_id"])
            failures = _check(case, envelope, model, retriever, names)
            texts = {name: doc["text"] for name, doc in data["documents"].items()}
            for context in model.seen:  # every passage reaches the model exactly as the source writes it (no case folding, NFKC or translation)
                for passage in context.passages:
                    if passage["text"] not in texts.get(names.get(passage["evidence"]["source_id"], "?"), ""):
                        failures.append("a passage is not a verbatim part of its source")
            ranked = [names.get(p["evidence"]["source_id"], "?") for p in index.search("documents", case["question"])][:TOP_K]
            gold = case.get("gold", [])
            if gold:
                first = next((i for i, n in enumerate(ranked, 1) if n in gold), None)
                retrieval.append(
                    {
                        "id": case["id"],
                        "language": case["language"],
                        "script": case["script"],
                        "recall": len({n for n in ranked if n in gold}) / len(gold),
                        "rr": 1 / first if first else 0.0,
                    }
                )
            results.append(
                {
                    "id": case["id"],
                    "category": case["category"],
                    "language": case["language"],
                    "script": case["script"],
                    "outcome": _outcome(envelope),
                    "passed": not failures,
                    "failures": failures,
                    "known_gap": case.get("known_gap"),
                }
            )
            store.close()
            index.close()
    return _report(data, results, retrieval)


def _group(rows: list[dict[str, Any]], key: str, fields: tuple[str, ...]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[row[key]].append(row)
    for name, group in sorted(buckets.items()):
        out[name] = {"n": len(group), **{f: round(sum(float(r[f]) for r in group) / len(group), 3) for f in fields}}
    return out


def _report(data: dict[str, Any], results: list[dict[str, Any]], retrieval: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "set": {
            "version": data["version"],
            "sha256": set_sha256(),
            "cases": len(results),
            "documents": len(data["documents"]),
            "languages": sorted({r["language"] for r in results}),
            "scripts": sorted({r["script"] for r in results}),
        },
        "label": {
            "machine": f"{platform.system()} {platform.machine()}, Python {platform.python_version()}",
            "model": "scripted deterministic stub (no real model)",
            "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "meaning": "pipeline behaviour only: retrieval and the checks that catch bad answers. NOT real-model answer quality, speed or memory (target-Mac evidence is pending).",
        },
        "retrieval_quality": {
            "by_language": _group(retrieval, "language", ("recall", "rr")),
            "by_script": _group(retrieval, "script", ("recall", "rr")),
            "top_k": TOP_K,
        },
        "answer_quality": {
            "pass_rate": round(sum(r["passed"] for r in results) / len(results), 3),
            "by_category": _group(results, "category", ("passed",)),
            "by_language": _group(results, "language", ("passed",)),
            "outcomes": {o: sum(r["outcome"] == o for r in results) for o in ("grounded", "no_evidence", "ungrounded", "rejected")},
        },
        "known_gaps": [{"id": r["id"], "gap": r["known_gap"]} for r in results if r["known_gap"]],
        "not_applicable": data["not_applicable"],
        "failed_cases": [{"id": r["id"], "failures": r["failures"]} for r in results if not r["passed"]],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    report = run()
    print(json.dumps(report, indent=None if parser.parse_args().json else 1, ensure_ascii=False))
    return 0 if not report["failed_cases"] else 1


if __name__ == "__main__":
    sys.exit(main())
