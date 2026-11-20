"""Criterion 7: no question text, file name, subject, address, passage, secret or raw personal record is ever written, on any path."""

from __future__ import annotations

import json

import pytest
from conftest import ALL_SENTINELS, KEY, SENTINEL_FILENAME, World, all_output, grant, request

from atlas_core.contracts import _document
from atlas_core.events import SafeLog, UnsafeEvent, new_id
from atlas_core.service import SimulatedCrash

ALLOWED_KEYS = set(_document()["$defs"]["SafeEvent"]["properties"])
GRANTS = [grant("documents"), grant("mail"), grant("finance", sensitivity="restricted")]


def _scan(w: World, caplog, capsys) -> str:
    out = all_output(w, caplog, capsys)
    for sentinel in ALL_SENTINELS:
        assert sentinel not in out, f"{sentinel!r} was written to a log"
    assert SENTINEL_FILENAME not in out
    for line in w.lines:
        assert set(json.loads(line)) <= ALLOWED_KEYS
    return out


@pytest.mark.criterion(7)
def test_a_normal_run_over_documents_and_mail_writes_no_content(tmp_path, caplog, capsys):
    w = World(tmp_path, GRANTS)
    w.run_new(request(["documents", "mail", "finance"]))
    assert w.lines and _scan(w, caplog, capsys)


@pytest.mark.criterion(7)
@pytest.mark.parametrize("mode", ["unavailable", "bad_quote", "stale", "extra_figure", "no_citation", "not_retrieved"])
def test_failure_paths_write_no_content(tmp_path, caplog, capsys, mode):
    w = World(tmp_path, GRANTS)
    w.model.mode = mode
    w.run_new(request(["documents"]))
    _scan(w, caplog, capsys)


@pytest.mark.criterion(7)
def test_denied_cancelled_expired_and_hostile_retriever_paths_write_no_content(tmp_path, caplog, capsys):
    denied = World(tmp_path / "a", []) if (tmp_path / "a").mkdir() is None else None
    assert denied is not None
    denied.run_new(request(["documents", "mail"]))
    _scan(denied, caplog, capsys)
    w = World(tmp_path / "b", GRANTS) if (tmp_path / "b").mkdir() is None else None
    assert w is not None
    queued, _ = w.service.submit(request(key="idem-key-0001"))
    w.service.cancel(queued["task_id"])
    late, _ = w.service.submit(request(key="idem-key-0002", seconds=5))
    w.clock.advance(100)
    w.service.run(late["task_id"])
    w.retriever.misbehave = "finance"
    w.clock.advance(-100)
    w.run_new(request(key="idem-key-0003"))
    _scan(w, caplog, capsys)


@pytest.mark.criterion(7)
def test_the_retry_path_after_a_crash_writes_no_content(tmp_path, caplog, capsys):
    w = World(tmp_path, GRANTS)
    record, _ = w.service.submit(request(["documents", "mail"]))
    w.faults.armed.add("mid:drafted")
    with pytest.raises(SimulatedCrash):
        w.service.run(record["task_id"])
    w.restart()
    w.service.run(record["task_id"])
    out = _scan(w, caplog, capsys)
    assert "task.recovered" in out


@pytest.mark.criterion(7)
@pytest.mark.parametrize(
    "fields",
    [
        {"objective": "free text"},
        {"reason_code": "Has Spaces And Capitals"},
        {"reason_code": "contains-a-dash"},
        {"filename": SENTINEL_FILENAME},
        {"status": 99999},
        {"state_to": "not_a_state"},
        {"error_code": "free text error"},
    ],
)
def test_an_event_with_a_field_outside_the_allow_list_or_a_value_outside_its_shape_is_refused(fields):
    sink: list[str] = []
    with pytest.raises(UnsafeEvent) as error:
        SafeLog(sink.append).emit("task.created", "service", new_id(), **fields)
    assert sink == [] and not any(str(v) in str(error.value) for v in fields.values() if isinstance(v, str))


@pytest.mark.criterion(7)
def test_an_unknown_event_name_or_component_or_a_content_shaped_correlation_id_is_refused():
    log = SafeLog(lambda _line: None)
    for event, component, cid in (
        ("free.text.event", "service", new_id()),
        ("task.created", "elsewhere", new_id()),
        ("task.created", "service", SENTINEL_FILENAME),
    ):
        with pytest.raises(UnsafeEvent):
            log.emit(event, component, cid)


@pytest.mark.criterion(7)
def test_the_task_store_key_and_client_keys_are_never_written(tmp_path, caplog, capsys):
    w = World(tmp_path, GRANTS)
    w.run_new(request())
    assert KEY not in all_output(w, caplog, capsys)
