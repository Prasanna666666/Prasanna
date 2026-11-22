"""WP3.5: the minimal experience, exercised end to end through the real signed contract over the real Unix socket with the reference client. The SwiftUI app itself is Mac-pending."""

from __future__ import annotations

import contextlib
import json
import re
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest
from conftest import KEY, Clock, grant
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from atlas_core import contracts
from atlas_core.access import AllowAll
from atlas_core.api import CoreApi
from atlas_core.documents import DocumentIndex
from atlas_core.errors import TABLE
from atlas_core.events import SafeLog
from atlas_core.identity import ClientRegistry
from atlas_core.intelligence import Gateway, Router, RuntimeFailure, Signals
from atlas_core.models import ModelStore
from atlas_core.policy import InMemoryGrants, PolicyEngine
from atlas_core.service import Deps, TaskService
from atlas_core.tasks import TaskStore
from atlas_core.transport import serve_unix

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "client"), str(ROOT / "evals")]
import atlas_client  # noqa: E402
import harness  # noqa: E402
from atlas_client import CATALOGUE, AtlasClient, ClientError  # noqa: E402
from test_models import entry_dict, signed  # noqa: E402

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="peer credentials are only verified on Linux in this stage")


# ---- the catalogue is complete and plain ----------------------------------------------------------------------------------------------------------------
def defs() -> dict:
    return contracts._document("1.1")["$defs"]


def enum(name: str, *path: str) -> list[str]:
    node = defs()[name]
    for p in path:
        node = node["properties"][p]
    return list(node["enum"])


def test_every_value_of_every_closed_vocabulary_has_a_message():
    d = defs()
    checks = {
        "task_states": enum("TaskState"),
        "errors": enum("ErrorCode"),
        "limitations": enum("Limitation"),
        "verification": enum("Verification", "status"),
        "language_support": enum("LanguageInfo", "support_status"),
        "terminal_reasons": enum("TaskRecord", "terminal_reason"),
        "not_searched_reasons": enum("PolicyDecision", "reason_code"),
        "progress_steps": enum("StreamEvent", "step"),
        "coverage_state": enum("Coverage", "state"),
        "coverage_pending": d["Coverage"]["properties"]["pending"]["items"]["properties"]["category"]["enum"],
        "coverage_failed": d["Coverage"]["properties"]["failed"]["items"]["properties"]["reason_code"]["enum"],
    }
    for section, values in checks.items():
        assert set(values) <= set(CATALOGUE[section]), (section, set(values) - set(CATALOGUE[section]))
    assert set(TABLE) <= set(CATALOGUE["errors"])
    assert set(d["Locator"]["anyOf"][0]["properties"]["kind"]["enum"]) | {"header_field", "attachment_part", "sheet_cell"} <= set(CATALOGUE["locator_kinds"])


def test_catalogue_text_is_plain_words_not_codes_paths_or_traces():
    texts = []
    for section, value in CATALOGUE.items():
        if isinstance(value, dict):
            texts += [t for t in value.values() if isinstance(t, str)]
        elif section not in ("version", "locale", "description"):
            texts.append(value)
    for text in texts:
        assert not re.search(r"[a-z]+_[a-z]+|Traceback|Exception|Error:|0x|/Users|/home|\.py\b", re.sub(r"\{[a-z_]+\}", "", text)), text
    assert all(t.strip() for k, v in CATALOGUE["errors"].items() for t in [v])


# ---- a whole Core behind a socket -----------------------------------------------------------------------------------------------------------------------------
class RunScripted:
    """A runtime that answers like the evaluation harness's scripted model (so the gateway, the identity and the checks are the real ones)."""

    def __init__(self, scripts: dict[str, dict]) -> None:
        self.scripts, self._loaded, self.fail, self.current = scripts, set(), False, ""

    def load(self, verified):
        self._loaded.add(verified.entry.model_id)

    def unload(self, model_id):
        self._loaded.discard(model_id)

    def loaded(self):
        return frozenset(self._loaded)

    def complete(self, model_id, context, max_context, should_stop=lambda: False):
        if self.fail:
            raise RuntimeFailure("x")
        script = self.scripts[self.current]  # several cases share a question and differ in what the model does, so the case is chosen explicitly
        return harness.ScriptedModel(script, script["lang"]).generate(context)


class Core:
    def __init__(self, tmp: Path, start_worker: bool = True) -> None:
        data = json.loads(harness.SET_FILE.read_text(encoding="utf-8"))
        self.lines: list[str] = []
        self.folder = Path(tempfile.mkdtemp(prefix="atl"))
        docs = tmp / "docs"
        docs.mkdir()
        for name, doc in data["documents"].items():
            (docs / name).write_text(doc["text"], encoding="utf-8")
        self.index = DocumentIndex(tmp / "index.db", KEY, docs, "documents", access=AllowAll())
        self.index.scan()
        while self.index.run(5)["pending"]:
            pass
        model = tmp / "models" / "primary-1"
        model.mkdir(parents=True)
        (model / "w.safetensors").write_bytes(b"w")
        manifest = signed([entry_dict("primary-1", {"w.safetensors": b"w"}, runtime="stub")])
        store = ModelStore(tmp / "models", manifest, b"k" * 32)
        store.import_model("primary-1")
        self.runtime = RunScripted({c["id"]: {**c["model"], "lang": c["language"]} for c in data["cases"]})
        self.grants = InMemoryGrants([grant("documents")])
        self.clock = Clock()
        self.tasks = TaskStore(tmp / "tasks.db", KEY)
        self.service = TaskService(
            Deps(
                self.tasks,
                PolicyEngine(self.grants),
                self.index,
                Gateway(store, Router(manifest.entries()), self.runtime, signals=Signals),
                self.index,
                SafeLog(self.lines.append),
                clock=self.clock,
                coverage={"documents": self.index.coverage},
            )
        )
        self.key = Ed25519PrivateKey.generate()
        registry = ClientRegistry()
        registry.register("client-mac-0001", self.key.public_key())
        self.registry = registry
        self.api = CoreApi(self.service, registry, SafeLog(self.lines.append), self.clock, check_responses=True)
        self.server = None
        self.stop = threading.Event()
        self.worker = threading.Thread(target=self._work, daemon=True)
        self.paused = not start_worker
        self.worker.start()

    def serve(self, api=None) -> str:
        self.server = serve_unix(self.folder / "run" / "core.sock", api or self.api, None)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return str(self.folder / "run" / "core.sock")

    def _work(self) -> None:
        while not self.stop.is_set():
            if not self.paused:
                for tid in self.tasks.ids_in(("queued",)):
                    with contextlib.suppress(Exception):  # the test worker never dies; the outcome is read from the task
                        self.service.run(tid)
            time.sleep(0.01)

    def q(self, cid: str) -> tuple[str, list[str]]:
        self.runtime.current = cid
        case = next(c for c in json.loads(harness.SET_FILE.read_text(encoding="utf-8"))["cases"] if c["id"] == cid)
        return case["question"], case.get("scope", ["documents"])

    def client(self, path: str, **kw) -> AtlasClient:
        return AtlasClient(path, kw.pop("key", self.key), "client-mac-0001", clock=self.clock, **kw)

    def close(self) -> None:
        self.stop.set()
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        shutil.rmtree(self.folder, ignore_errors=True)


@pytest.fixture
def core(tmp_path):
    c = Core(tmp_path)
    yield c
    c.close()


def test_a_question_is_answered_with_progress_citations_model_identity_and_coverage(core):
    client = core.client(core.serve())
    assert client.discover()["supported"] == ["1.0", "1.1"]
    steps: list[str] = []
    view = client.run_question(*core.q("en-total"), on_progress=steps.append)
    assert (
        steps[0] == CATALOGUE["task_states"]["policy_checked"]
        and CATALOGUE["progress_steps"]["verified"] in steps
        and steps[-1] == CATALOGUE["task_states"]["completed"]
    )
    assert "1250.50" in view["text"] and view["citations"][0]["quote"] == "1250.50" and view["citations"][0]["label"].startswith("Document")
    assert "primary-1" in view["model_line"] and "main model" in view["model_line"] and "Nothing left your computer" in view["model_line"]
    assert view["coverage_line"] and "Searched" in view["coverage_line"] and CATALOGUE["limitations"]["language_unmeasured"] in view["notices"]


def test_dutch_and_hindi_questions_round_trip_through_the_whole_path(core):
    client = core.client(core.serve())
    for cid, needle in (("nl-total", "480,00"), ("hi-total", "750.00"), ("ru-total", "3200,00")):
        view = client.run_question(*core.q(cid))
        assert needle in view["text"] and view["citations"][0]["quote"] == needle


def test_a_missing_answer_and_a_hallucinated_figure_are_shown_as_not_confirmed_never_as_checked(core):
    client = core.client(core.serve())
    hallucinated = client.run_question(*core.q("hallucinated-figure"))
    assert hallucinated["unproven_figures"] == [777.77] and CATALOGUE["limitations"]["figures_unproven"] in hallucinated["notices"]
    assert hallucinated["trust"] != CATALOGUE["verification"]["verified"]
    rejected = client.run_question(*core.q("ja-total"))
    assert rejected["citations"] == CATALOGUE["no_citations"]


def test_cancel_stops_a_queued_task_with_plain_words(tmp_path):
    c = Core(tmp_path, start_worker=False)
    try:
        client = c.client(c.serve())
        task_id = client.ask(*c.q("en-total"))
        assert client.cancel(task_id)["state"] == "cancelled"
        with pytest.raises(ClientError) as e:
            client.result(task_id)  # the stream of a cancelled task ends with its error event
        assert e.value.code == "task_cancelled"
    finally:
        c.close()


def test_an_unavailable_model_is_reported_in_plain_words_without_a_trace(core):
    core.runtime.fail = True
    client = core.client(core.serve())
    with pytest.raises(ClientError) as e:
        client.run_question(*core.q("en-total"))
    assert e.value.code == "model_unavailable" and e.value.message == CATALOGUE["errors"]["model_unavailable"] and "Traceback" not in e.value.message


def test_no_server_a_wrong_key_and_an_unknown_task_give_catalogue_messages(core, tmp_path):
    with pytest.raises(ClientError) as gone:
        AtlasClient(str(tmp_path / "none.sock"), core.key, "client-mac-0001").discover()
    assert gone.value.code == "connection" and "not running" in gone.value.message
    path = core.serve()
    wrong = core.client(path, key=Ed25519PrivateKey.generate())
    with pytest.raises(ClientError) as e:
        wrong.ask("x", ["documents"])
    assert e.value.code == "unauthenticated" and e.value.message == CATALOGUE["errors"]["unauthenticated"]
    with pytest.raises(ClientError) as e:
        core.client(path).status("aaaaaaaaaaaa")
    assert e.value.code == "not_found"


def test_a_response_without_the_version_echo_is_rejected_by_a_1_1_client(core):
    class StripEcho:
        def handle(self, request):
            response = core.api.handle(request)
            response.headers.pop("x-atlas-api-version", None)
            return response

    client = core.client(core.serve(StripEcho()))
    with pytest.raises(ClientError):
        client.ask(*core.q("en-total"))


def test_a_1_0_client_still_works_against_the_same_core(core):
    client = core.client(core.serve(), version="1.0")
    view = client.run_question(*core.q("en-total"))
    assert "1250.50" in view["text"] and view["coverage_line"] is None and "Nothing left your computer" in view["model_line"]


def test_revoking_a_source_hides_the_answer_with_an_explanation(core):
    client = core.client(core.serve())
    task_id = client.ask(*core.q("en-total"))
    list(client.events(task_id))
    core.grants._grants[:] = []
    view = atlas_client.render(client.answer(task_id))
    assert CATALOGUE["limitations"]["answer_withheld"] in view["notices"] and "1250.50" not in json.dumps(view)


def shown(view: dict) -> str:
    """Everything a screen would print (the `evidence` of a citation is for the 'show the source passage' action, not for display)."""
    parts = [view["text"], view["trust"], view["model_line"], view["coverage_line"] or "", *view["notices"], *view["not_searched"]]
    parts += [view["citations"]] if isinstance(view["citations"], str) else [f"{c['label']} {c['quote'] or ''}" for c in view["citations"]]
    return "\n".join(parts)


def test_nothing_the_owner_sees_contains_a_path_a_trace_or_raw_identifiers(core, tmp_path):
    client = core.client(core.serve())
    for cid in ("en-total", "missing-en", "prompt-injection"):
        text = shown(client.run_question(*core.q(cid)))
        assert str(tmp_path) not in text and "Traceback" not in text and not re.search(r"[0-9a-f]{24,}|source_id|version_sha256", text)


def test_the_cited_passage_can_be_opened_exactly_and_stops_opening_when_the_source_changes_or_is_revoked(core):
    client = core.client(core.serve())
    task_id = client.ask(*core.q("en-total"))
    view = client.result(task_id)
    text = client.passage(task_id, 0)
    assert "1250.50" in text and view["citations"][0]["quote"] in text
    with pytest.raises(ClientError) as missing:
        client.passage(task_id, 5)
    assert missing.value.code == "not_found"
    path = next(Path(core.index.scanner.root).glob("invoice_en.txt"))
    path.write_text("changed after the answer", encoding="utf-8")
    with pytest.raises(ClientError) as changed:  # a changed source withholds the whole answer: nothing of it is shown, not even the passage
        client.passage(task_id, 0)
    assert changed.value.code == "source_denied"
    path.write_text(json.loads(harness.SET_FILE.read_text(encoding="utf-8"))["documents"]["invoice_en.txt"]["text"], encoding="utf-8")
    core.grants._grants[:] = []
    with pytest.raises(ClientError) as revoked:
        client.passage(task_id, 0)
    assert revoked.value.code == "source_denied"


def test_the_passage_route_does_not_exist_for_1_0_and_for_an_unfinished_task(tmp_path):
    c = Core(tmp_path, start_worker=False)
    try:
        path = c.serve()
        task_id = c.client(path).ask(*c.q("en-total"))
        with pytest.raises(ClientError) as early:
            c.client(path).passage(task_id, 0)
        assert early.value.code == "conflict"
        with pytest.raises(ClientError) as old:
            c.client(path, version="1.0").passage(task_id, 0)
        assert old.value.code == "not_found"
    finally:
        c.close()


def test_exact_computations_go_through_the_signed_contract_and_never_through_a_model(core):
    client = core.client(core.serve())
    assert client.compute("arithmetic", "1250.50 + 3.25")["value"] == "1253.75"
    assert client.compute("add_months", "2026-01-31", "1") == {"kind": "add_months", "value": "2026-02-28", "exact": True, "approximate": None, "clamped": True}
    with pytest.raises(ClientError) as bad:
        client.compute("arithmetic", "1 / 0")
    assert bad.value.code == "invalid_request" and "0" not in bad.value.message
    assert core.runtime.loaded() == frozenset()  # no model was loaded or asked
