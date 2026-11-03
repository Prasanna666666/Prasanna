"""Chat must stay fast on an 8 GB Mac: no automatic indexing, preload only when idle, pause indexing while searching."""

import json
import threading
from types import SimpleNamespace

from aperture import bootstrap
from aperture.config import Paths, Settings
from aperture.ui import state


def test_indexing_does_not_start_by_itself_and_old_choice_resets_once(tmp_path):
    paths = Paths(tmp_path)
    assert Settings.defaults(paths).auto_scan is False
    paths.settings_file.parent.mkdir(parents=True, exist_ok=True)
    paths.settings_file.write_text(json.dumps({"schema": 5, "auto_scan": True, "page_size": 48}))
    s = Settings.load(paths)
    assert s.auto_scan is False and s.page_size == 48 and s.schema == 8
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
        llm=lambda: llm,
    )


def test_warm_up_loads_models_only_when_no_scan_is_running(monkeypatch):
    monkeypatch.setattr(threading, "Thread", _InlineThread)
    for running, expected in ((False, ["llm", "index", "facts", "clip"]), (True, ["index", "facts"])):
        calls = []
        monkeypatch.setattr("aperture.indexing.progress.ScanLock.running", lambda self, r=running: r)
        bootstrap.AppContext.warm_up(_fake_ctx(calls))
        assert calls == expected


def test_warm_up_survives_a_failing_step(monkeypatch):
    monkeypatch.setattr(threading, "Thread", _InlineThread)
    monkeypatch.setattr("aperture.indexing.progress.ScanLock.running", lambda self: False)
    calls = []
    ctx = _fake_ctx(calls)
    ctx.search_embedder = lambda: (_ for _ in ()).throw(RuntimeError("no model"))
    bootstrap.AppContext.warm_up(ctx)
    assert calls == ["llm", "index", "facts"]  # the image-search model failed; the others still loaded


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
