"""Chat must stay fast on an 8 GB Mac: no automatic indexing, preload only when idle, pause indexing while searching."""

import json
import threading
from types import SimpleNamespace

from images.config import Paths, Settings

from aperture import bootstrap
from aperture.ui import state


def test_indexing_does_not_start_by_itself_and_old_choice_resets_once(tmp_path):
    paths = Paths(tmp_path)
    assert Settings.defaults(paths).auto_scan is False
    paths.settings_file.parent.mkdir(parents=True, exist_ok=True)
    paths.settings_file.write_text(json.dumps({"schema": 5, "auto_scan": True, "page_size": 48}))
    s = Settings.load(paths)
    assert s.auto_scan is False and s.page_size == 48 and s.schema == 9
    paths.settings_file.write_text(json.dumps({"schema": 8, "auto_scan": True}))
    assert Settings.load(paths).auto_scan is True  # a deliberate choice made after v6 is kept


class _InlineThread:
    def __init__(self, target, name=None, daemon=None):
        self.target = target

    def start(self):
        self.target()


def _fake_ctx(calls):
    llm = SimpleNamespace(warm=lambda: calls.append("llm"))
    return SimpleNamespace(
        paths=SimpleNamespace(scan_pid="x"),
        embedding_index=lambda: calls.append("index"),
        search_embedder=lambda: calls.append("clip"),
        _prime_library_facts=lambda: calls.append("facts"),
        _fill_places=lambda: calls.append("places"),
        _warm_search=lambda: calls.append("warm"),
        warm_errors={},
        llm=lambda: llm,
    )


def test_warm_up_loads_models_only_when_no_scan_is_running(monkeypatch):
    monkeypatch.setattr(threading, "Thread", _InlineThread)
    for running, expected in ((False, ["index", "places", "facts", "clip", "warm", "llm"]), (True, ["index", "places", "facts"])):
        calls = []
        monkeypatch.setattr("images.indexing.progress.ScanLock.running", lambda self, verify=False, r=running: r)
        bootstrap.AppContext.warm_up(_fake_ctx(calls))
        assert calls == expected


def test_warm_up_survives_a_failing_step(monkeypatch):
    monkeypatch.setattr(threading, "Thread", _InlineThread)
    monkeypatch.setattr("images.indexing.progress.ScanLock.running", lambda self, verify=False: False)
    calls = []
    ctx = _fake_ctx(calls)
    ctx.search_embedder = lambda: (_ for _ in ()).throw(RuntimeError("no model"))
    bootstrap.AppContext.warm_up(ctx)
    assert sorted(calls) == ["facts", "index", "llm", "places", "warm"]  # the image-search model failed; the others still loaded


def test_searching_pauses_a_running_scan_and_remembers_why(monkeypatch):
    stopped = []
    monkeypatch.setattr(state, "st", SimpleNamespace(session_state={}))
    ctx = SimpleNamespace(paths=SimpleNamespace(scan_pid="x"))
    monkeypatch.setattr(state.ScanLock, "running", lambda self: True)
    monkeypatch.setattr(state.ScanLock, "stop", lambda self: stopped.append(1))
    assert state.pause_scan_for_chat(ctx) is True and stopped == [1]
    assert state.st.session_state["paused_for_chat"] is True
    state.st.session_state.clear()
    monkeypatch.setattr(state.ScanLock, "running", lambda self: False)
    assert state.pause_scan_for_chat(ctx) is False and not state.st.session_state


def test_keep_alive_is_thirty_minutes():
    from aperture.agent.llm import OllamaClient

    assert OllamaClient("http://127.0.0.1:11434", "m").keep_alive == "30m"


def test_a_stale_scan_marker_is_not_indexing_and_gets_no_stop_signal(tmp_path, monkeypatch):
    import os

    from images.indexing import progress
    from images.indexing.progress import ScanLock

    marker = tmp_path / "scan.pid"
    marker.write_text(str(os.getpid()))  # a live process, but not an Aperture scan (this test run)
    lock = ScanLock.__new__(ScanLock)
    lock._file = marker
    monkeypatch.setattr(progress, "_is_aperture", lambda pid: False)
    signalled = []
    monkeypatch.setattr(progress.os, "kill", lambda pid, sig: signalled.append(sig) if sig else None)
    assert lock.running() is True and lock.running(verify=True) is False  # alive, but not ours
    lock.stop()
    assert signalled == [] and not marker.exists()  # nobody was signalled; the stale marker was forgotten
    marker.write_text(str(os.getpid()))
    monkeypatch.setattr(progress, "_is_aperture", lambda pid: True)
    lock.stop()
    assert signalled and marker.exists()  # a real Aperture scan does get the polite stop request


def test_the_page_says_why_search_is_not_ready(tmp_path, monkeypatch):
    from images.config import Paths

    from aperture.bootstrap import AppContext

    monkeypatch.setenv("APERTURE_ALLOW_INTERNAL", "1")
    paths = Paths(tmp_path / "Expansion")
    paths.ensure()
    ctx = AppContext(paths)
    assert ctx.warm_problem() == ""
    ctx.warm_errors["image search model"] = "OSError: cannot read model"
    assert "cannot read model" in ctx.warm_problem()
    ctx.embedder_error = "CLIP model unavailable (no weights)"
    assert ctx.warm_problem() == "CLIP model unavailable (no weights)"


def test_model_calls_are_recorded_with_what_the_model_saw_and_said(monkeypatch):
    import json as _json
    import urllib.request

    from aperture.agent.llm import CALL_LOG, OllamaClient

    class Resp:
        def __init__(self, lines):
            self.lines = lines

        def __iter__(self):
            return iter(self.lines)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"".join(self.lines)

    chunks = [
        {"message": {"content": "Hi "}},
        {"message": {"content": "there", "tool_calls": [{"function": {"name": "find_photos", "arguments": {"what": "dog"}}}]}},
        {"done": True},
    ]
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda req, timeout=None: Resp([_json.dumps(c).encode() + b"\n" for c in chunks])
    )
    client = OllamaClient("http://127.0.0.1:11434", "ministral-3:3b")
    list(client.stream_chat("SYS", [{"role": "user", "content": "hello"}]))  # no log active: nothing is recorded, nothing breaks
    log = []
    token = CALL_LOG.set(log)
    try:
        list(client.stream_chat("SYS PROMPT", [{"role": "user", "content": "hello"}]))
        monkeypatch.setattr(
            urllib.request,
            "urlopen",
            lambda req, timeout=None: Resp([_json.dumps({"message": {"content": '{"route": "chat"}'}}).encode()]),
        )
        client.complete_json("ROUTER PROMPT", "Message: hi", {"type": "object"})
    finally:
        CALL_LOG.reset(token)
    assert (
        log[0]["system"] == "SYS PROMPT"
        and log[0]["output"] == "Hi there"
        and log[0]["messages"] == [{"role": "user", "text": "hello"}]
    )
    assert log[0]["tool_calls"] == [{"name": "find_photos", "arguments": {"what": "dog"}}]
    assert log[1]["system"] == "ROUTER PROMPT" and log[1]["output"] == '{"route": "chat"}'


def test_worked_out_locations_are_off_unless_asked_for():
    from images.config import Settings

    assert Settings().estimate_locations is False


def test_warming_up_runs_one_real_search_so_the_first_question_is_not_the_slow_one(scanned):
    scanned._warm_search()  # must run end to end on a real (small) library without raising


def test_switching_the_picture_model_throws_away_everything_derived_from_the_old_one(scanned):
    from images.config import Settings
    from images.db import meta_set
    from images.indexing.runner import Scanner

    conn = scanned.db.connect()
    meta_set(conn, "clip_model", "ViT-B-32/laion2b_s34b_b79k")
    conn.execute("INSERT INTO photo_labels VALUES (1, 'baby', 0.9, 'face')")
    conn.execute("INSERT INTO photo_labels VALUES (1, 'baby', 0.9, 'age')")  # a different model's work is kept
    settings = Settings(clip_model="ViT-L-14", clip_pretrained="laion2b_s32b_b82k")
    scanner = Scanner.__new__(Scanner)
    scanner.settings = settings
    scanner._check_embedding_model(conn)
    assert conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0] == 0
    assert {r[0] for r in conn.execute("SELECT source FROM photo_labels")} == {"age"}  # only the old picture model's labels went
    assert conn.execute("SELECT COUNT(*) FROM items WHERE clip_done=0 AND kind='image'").fetchone()[0] > 0
