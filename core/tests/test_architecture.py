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
    "models": 1,
    "coverage": 1,
    "exact": 1,
    "events": 2,
    "identity": 2,
    "policy": 3,
    "gate": 4,
    "evidence": 4,
    "documents": 4,
    "designation": 4,
    "access": 4,
    "mail": 4,
    "intelligence": 4,
    "mlx_runtime": 4,
    "answer": 5,
    "tasks": 5,
    "service": 6,
    "api": 7,
    "transport": 8,
    "app": 9,
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
    forbidden = {
        "tasks",
        "gate",
        "evidence",
        "policy",
        "answer",
        "designation",
        "access",
        "documents",
    }  # consent state is changed by the Core, never reached from the edge
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


# ---- canonical documents (docs/genesis): the owner's decisions are applied in place, the roadmap is single, the approval list is closed -------------------
GENESIS = ROOT.parent / "docs" / "genesis"
HISTORICAL = re.compile(
    r"(?i)\b(superseded|historical|as authorised at the time)\b"
)  # a line or a section heading carrying this is a labelled historical record
SUPERSEDED_RULES = {
    "finance-model-exclusion": re.compile(
        r"(?i)((no|never|not|cannot|must not)\b[^.|]{0,80}raw finance|raw finance[^.|]{0,100}(never|outside|excluded|inaccessible|cannot|not visible)|finance enclave)"
    ),
    "health-lock": re.compile(
        r"(?i)(health[^.|]{0,80}(locked by default|remains? locked|is locked|disabled/locked|excluded and locked)|no health access (by default|or unlock)|health (is |remains )?(excluded|locked))"
    ),
    "approval-beyond-the-closed-list": re.compile(
        r"(?i)(privacy-sensitive|confirm (every|each)|only under the consequential-action approval rule"
        r"|approval[^.|]{0,80}(security changes|consequential access|production systems|declarations|signing)"
        r"|(security changes|consequential access changes|production systems|declarations|signing)[^.|]{0,80}approval)"
    ),
}
# Violations the architect has been told about and has not yet corrected: (file, rule, start of the line). The test requires this list to equal what is found,
# so an entry must be deleted in the same change that fixes its line, and nothing new can slip in.
PENDING_DOC_FIXES: list[tuple[str, str, str]] = []
APPROVAL_CATEGORIES = {
    "send outside the Mac": re.compile(r"(?i)\b(send|sending|forward\w*|shar\w+|publish\w*|upload\w*)\b"),
    "spend money": re.compile(r"(?i)\b(spend\w*|pay\w*|purchas\w+|trad\w+|paid booking\w*)\b"),
    "delete without undo": re.compile(r"(?i)(delet\w+|overwrit\w+|destructive migration)"),
    "physical access or safety": re.compile(r"(?i)(unlock|disarm|safety/security|safety or security|physical access)"),
}


def genesis_files() -> list[Path]:
    return [*sorted(GENESIS.glob("*.md")), ROOT.parent / "CLAUDE.md"]


def stale_phrases() -> list[tuple[str, str, str]]:
    found = []
    for path in genesis_files():
        in_historical_section = False
        for line in path.read_text().splitlines():
            if line.startswith("#"):
                in_historical_section = bool(HISTORICAL.search(line))
            elif not in_historical_section and not HISTORICAL.search(line):
                found += [(path.name, rule, line.strip()[:70]) for rule, pattern in SUPERSEDED_RULES.items() if pattern.search(line)]
    return sorted(set(found))


def section_text(name: str, heading: str) -> str:
    """The text from the heading that matches `heading` to the next heading of the same or a higher level."""
    lines, out, level = (GENESIS / name).read_text().splitlines(), [], 0
    for line in lines:
        if out and line.startswith("#") and len(line) - len(line.lstrip("#")) <= level:
            break
        if not out and line.startswith("#") and re.search(heading, line):
            level = len(line) - len(line.lstrip("#"))
        if level:
            out.append(line)
    return "\n".join(out)


def categories_in(text: str) -> set[str]:
    return {name for name, pattern in APPROVAL_CATEGORIES.items() if pattern.search(text)}


def test_the_owner_decisions_are_applied_in_place_not_only_appended_as_supersession_notes():
    found, pending = stale_phrases(), sorted(PENDING_DOC_FIXES)
    assert found == pending, f"new: {sorted(set(found) - set(pending))}; fixed (delete from PENDING_DOC_FIXES): {sorted(set(pending) - set(found))}"


def test_there_is_exactly_one_delivery_roadmap_and_it_is_in_the_target_architecture():
    stage_tables = [
        (p.name, n) for p in genesis_files() for n, line in enumerate(p.read_text().splitlines(), 1) if re.match(r"^\|\s*Order\s*\|\s*Stage\b", line)
    ]
    assert [name for name, _ in stage_tables] == ["TARGET_ARCHITECTURE.md"], stage_tables
    competing = [
        (p.name, line.strip()[:60])
        for p in genesis_files()
        for line in p.read_text().splitlines()
        if re.search(r"(?i)(release prioritisation|milestone sequence|priority wave|\bwave [1-9]\b)", line) and not HISTORICAL.search(line)
    ]
    assert not competing, f"a second sequence is defined in: {competing}"


def test_every_document_that_states_the_approval_list_states_the_same_closed_list():
    stated = {
        "PRD.md §4.4": section_text("PRD.md", r"4\.4"),
        "DECISIONS.md G-022": next(line for line in (GENESIS / "DECISIONS.md").read_text().splitlines() if line.startswith("| G-022")),
        "USE_CASE_REGISTER.md §7": section_text("USE_CASE_REGISTER.md", r"^## 7\."),
        "INTERNET_AND_NETWORK_POLICY.md §6": section_text("INTERNET_AND_NETWORK_POLICY.md", r"^## 6\."),
    }
    wrong = {where: sorted(set(APPROVAL_CATEGORIES) ^ categories_in(text)) for where, text in stated.items() if categories_in(text) != set(APPROVAL_CATEGORIES)}
    assert not wrong, f"these differ from the four closed categories: {wrong}"


# The approval matrix. No Action Runtime exists yet, so this locks the specification: each row is an action, the effect it has, and whether the owner is asked. When the
# runtime is built, `requires_approval` is replaced by the real decision and the same table drives the real test. Only these effects ever prompt (PRD section 4.4).
PROMPTING_EFFECTS = {"external_send", "spend", "irreversible_delete", "destructive_migration", "physical_security"}
APPROVAL_MATRIX = [  # (action, effect, owner is asked)
    ("read, search, summarise, analyse, compute", "read", False),
    ("draft an email, a letter or a reply", "draft", False),
    ("create or move the owner's own calendar event", "local_change", False),
    ("send a calendar invitation or update", "external_send", True),
    ("create, edit, rename or organise files and notes with undo", "local_change", False),
    ("delete or overwrite with reliable undo", "local_change", False),
    ("delete or overwrite without reliable undo", "irreversible_delete", True),
    ("destructive migration or retiring a legacy store", "destructive_migration", True),
    ("send, forward, reply or post a message outside the Mac", "external_send", True),
    ("share or upload a file or contact data outside the Mac", "external_send", True),
    ("pay, transfer, trade, purchase or place a paid booking", "spend", True),
    ("complete, create or reprioritise a task or reminder", "local_change", False),
    ("ordinary device control (lights, heating, media)", "local_change", False),
    ("unlock an external door, disarm an alarm or disable a safety system", "physical_security", True),
    ("public web search or page fetch with a sanitised query", "read", False),
    ("connect a read-only source after first-run consent", "read", False),
    ("cancel a booking without any external message or payment", "local_change", False),
    ("run a rule the owner stated that only changes local data with undo", "local_change", False),
]


def requires_approval(effect: str) -> bool:
    return effect in PROMPTING_EFFECTS


def register_matrix_rows() -> dict[str, bool]:
    rows = section_text("USE_CASE_REGISTER.md", r"^## 7\.").splitlines()
    cells = [[c.strip() for c in row.strip("|").split("|")] for row in rows if row.startswith("| ") and not row.startswith("| Action") and "---" not in row]
    return {cell[0]: cell[1] == "Yes" for cell in cells if len(cell) >= 2 and cell[1] in ("Yes", "No")}


def test_routine_actions_never_prompt_and_only_the_closed_categories_do():
    wrong = [(action, effect) for action, effect, asked in APPROVAL_MATRIX if requires_approval(effect) != asked]
    assert not wrong, wrong
    assert {effect for _, effect, asked in APPROVAL_MATRIX if asked} == PROMPTING_EFFECTS  # every closed category has a case, and no case adds one
    assert all(effect in PROMPTING_EFFECTS or not asked for _, effect, asked in APPROVAL_MATRIX)


def test_the_prompt_table_in_the_use_case_register_agrees_with_the_matrix_on_every_row_it_has():
    table = register_matrix_rows()
    assert table, "the table in USE_CASE_REGISTER.md section 7 was not found"
    asked_in_register = {action for action, asked in table.items() if asked}
    never_asked_in_register = {action for action, asked in table.items() if not asked}
    for action in asked_in_register:
        assert categories_in(action), f"the register asks for approval on {action!r}, which is not in the closed list"
    for action in never_asked_in_register:
        assert not categories_in(action) or "with reliable undo" in action.lower(), f"{action!r} sounds like a prompting action but is marked No"
    assert any("Create/move own calendar event" in a for a in never_asked_in_register)  # the case the owner objected to is prompt-free


@pytest.mark.criterion(11)
def test_only_the_mlx_adapter_names_the_inference_library_and_no_model_module_can_reach_the_network_or_unpickle():
    forbidden = ("socket", "urllib", "http.client", "requests", "httpx", "aiohttp", "pickle", "marshal", "torch", "transformers", "huggingface_hub")
    for module in ("models", "intelligence", "mlx_runtime", "coverage"):
        tree = ast.parse((SRC / f"{module}.py").read_text())
        names = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | {
            n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
        }
        assert not {x for x in names if x.split(".")[0] in {f.split(".")[0] for f in forbidden}}, module
    for path in SRC.glob("*.py"):
        text = path.read_text()
        assert 'trust_remote_code": True' not in text and "trust_remote_code=True" not in text, path.name
        if path.stem != "mlx_runtime":
            assert "mlx_lm" not in text and "import mlx" not in text, path.name
