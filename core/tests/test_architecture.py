"""Criteria 8 and 12: the dependency direction is enforced by tests, nothing reaches storage or a model around the policy, and every acceptance criterion has evidence."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "atlas_core"
TESTS = ROOT / "tests"
LAYER = {
    "__init__": 0,
    "errors": 1,
    "contracts": 1,
    "rules": 1,
    "values": 1,
    "events": 2,
    "identity": 2,
    "policy": 3,
    "gate": 4,
    "evidence": 4,
    "answer": 5,
    "tasks": 5,
    "service": 6,
    "api": 7,
    "transport": 8,
}
SOURCE_TYPE_NAMES = {"documents", "mail", "mail_attachment", "finance", "health"}


def imports(module: str) -> set[str]:
    tree = ast.parse((SRC / f"{module}.py").read_text())
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 1:
            found |= {node.module.split(".")[0]} if node.module else {a.name if a.name in LAYER else "__init__" for a in node.names}
    return found


@pytest.mark.criterion(8)
def test_every_module_has_a_layer_and_imports_only_from_below_or_its_own_layer():
    assert {p.stem for p in SRC.glob("*.py")} == set(LAYER)
    for module, layer in LAYER.items():
        for target in imports(module):
            assert target in LAYER and LAYER[target] <= layer, f"{module} (layer {layer}) imports {target} (layer {LAYER.get(target)})"


@pytest.mark.criterion(8)
def test_there_are_no_import_cycles():
    graph = {m: imports(m) for m in LAYER}
    state: dict[str, int] = {}

    def visit(node: str, trail: tuple[str, ...]) -> None:
        assert state.get(node) != 1, f"cycle: {' -> '.join((*trail, node))}"
        if state.get(node) == 2:
            return
        state[node] = 1
        for nxt in graph[node]:
            visit(nxt, (*trail, node))
        state[node] = 2

    for module in graph:
        visit(module, ())


@pytest.mark.criterion(8)
def test_the_api_and_the_transport_cannot_reach_storage_retrieval_policy_or_a_model_directly():
    forbidden = {"tasks", "gate", "evidence", "policy", "answer"}
    assert not (imports("api") & forbidden) and not (imports("transport") & (forbidden | {"service"}))
    assert imports("api") <= {"contracts", "errors", "events", "identity", "service", "__init__"}


@pytest.mark.criterion(8)
def test_a_model_is_reachable_only_through_the_gate_and_a_context_is_built_only_there():
    for path in SRC.glob("*.py"):
        text = path.read_text()
        if path.stem not in ("gate", "service"):
            assert ".generate(" not in text, path.name
        if path.stem != "gate":
            assert (
                "ModelContext(" not in text and "_CONTEXT_MINT" not in text and "PermitToken(" not in text.replace("PermitToken(frozenset", "")
            ) or path.stem == "policy"
    assert len(re.findall(r"\.generate\(", (SRC / "service.py").read_text())) == 1
    assert "self._model.generate(token, context" in (SRC / "service.py").read_text()


@pytest.mark.criterion(8)
def test_there_is_one_policy_one_task_store_and_one_pipeline_no_second_copy():
    def classes_with(method: str) -> list[str]:
        out = []
        for path in SRC.glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ClassDef) and any(isinstance(n, ast.FunctionDef) and n.name == method for n in node.body):
                    out.append(f"{path.stem}.{node.name}")
        return out

    assert classes_with("decide") == ["policy.PolicyEngine"]
    assert classes_with("transition") == ["tasks.TaskStore"]
    assert classes_with("submit") == ["service.TaskService"]


@pytest.mark.criterion(8)
def test_no_source_type_is_named_in_code_the_policy_is_data():
    for path in SRC.glob("*.py"):
        tree = ast.parse(path.read_text())
        docstrings = {
            id(n.body[0].value)
            for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef)) and n.body and isinstance(n.body[0], ast.Expr)
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
                assert node.value not in SOURCE_TYPE_NAMES, f"{path.name}: the source type {node.value!r} is written in code, not in policy-rules.json"


def _criteria_in_tests() -> dict[int, list[str]]:
    found: dict[int, list[str]] = {}
    for path in sorted(TESTS.glob("test_*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.FunctionDef):
                for deco in node.decorator_list:
                    if isinstance(deco, ast.Call) and getattr(deco.func, "attr", "") == "criterion":
                        found.setdefault(deco.args[0].value, []).append(f"tests/{path.name}::{node.name}")  # type: ignore[attr-defined]
    return found


@pytest.mark.criterion(12)
def test_every_acceptance_criterion_has_at_least_one_test_that_provides_evidence():
    assert sorted(_criteria_in_tests()) == list(range(1, 17))


@pytest.mark.criterion(12)
def test_the_traceability_matrix_names_every_criterion_and_only_tests_that_exist():
    doc = (ROOT / "docs" / "TRACEABILITY.md").read_text()
    existing = {t for tests in _criteria_in_tests().values() for t in tests}
    for number in range(1, 17):
        assert re.search(rf"^\| {number} \|", doc, re.MULTILINE), f"criterion {number} is missing from docs/TRACEABILITY.md"
    named = set(re.findall(r"tests/test_[a-z_]+\.py::test_[a-z0-9_]+", doc))
    assert named and named <= existing, sorted(named - existing)
    for gap in ("G-2", "G-3", "G-5", "G-9", "G-13"):
        assert gap in doc
