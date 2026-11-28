"""WP3.4c: derived content is not kept longer than it is needed, a revocation purges it from the task store, and the task service is safe under concurrency."""

from __future__ import annotations

import json
import threading

import pytest
from conftest import CORPUS, World, grant, request

SENTINEL = CORPUS[0].text[:24]  # words that exist only in the source document


def dump(w: World) -> str:
    c = w.store._conn
    return "\n".join(str(tuple(r)) for t in ("tasks", "task_events", "answers") for r in c.execute(f"SELECT * FROM {t}"))


def run(w: World, **kw) -> str:
    return w.run_new(request(**kw))["task_id"]


def test_a_finished_task_keeps_no_passage_text_draft_or_quote_but_the_answer_is_still_served(tmp_path):
    w = World(tmp_path, [grant("documents")])
    tid = run(w)
    data = w.store.checkpoint(tid)[1]
    assert "draft" not in data and all(set(p) == {"evidence"} for p in data["passages"]) and all(set(c) == {"evidence"} for c in data["citations"])
    assert w.service.answer(tid)["citations"] and w.service.answer_v11(tid)["coverage"]
    assert SENTINEL not in json.dumps(data)


@pytest.mark.parametrize("how", ["cancelled_before_run", "failed_model", "expired"])
def test_every_terminal_path_scrubs(tmp_path, how):
    w = World(tmp_path, [grant("documents")])
    if how == "failed_model":
        w.model.mode = "unavailable"
        tid = run(w)
    elif how == "cancelled_before_run":
        tid = w.service.submit(request())[0]["task_id"]
        w.service.cancel(tid)
    else:
        tid = w.service.submit(request())[0]["task_id"]
        w.clock.advance(10_000)
        w.store.expire_due(w.clock())
    assert w.store.record(tid)["state"] in ("failed", "cancelled", "expired")
    assert SENTINEL not in dump(w)


def test_purge_removes_the_content_of_a_revoked_type_from_answers_events_and_checkpoints_and_is_idempotent(tmp_path):
    w = World(tmp_path, [grant("documents")])
    doc = run(w)
    assert "Totaal" not in w.store.checkpoint(doc)[1].get("draft", "")
    assert SENTINEL in dump(w) or w.service.answer(doc)["answer"]  # the saved answer is where the content lives
    answer_text = w.service.answer(doc)["answer"]
    assert w.service.purge_source_type("documents") == 1
    assert answer_text not in dump(w) and SENTINEL not in dump(w)
    env = w.service.answer(doc)
    assert env["verification"]["status"] != "verified" and "answer_withheld" in env["limitations"] and env["citations"] == []
    events = w.store.events_after(doc, 0)
    assert not [e for e in events if e["type"] == "final"] and any(e["type"] == "error" and e["error"]["code"] == "source_denied" for e in events)
    assert w.service.purge_source_type("documents") == 1  # idempotent: the same task is found again and stays withheld


def test_a_regrant_does_not_bring_purged_content_back(tmp_path):
    w = World(tmp_path, [grant("documents")])
    tid = run(w)
    w.service.purge_source_type("documents")
    w.grants._grants[:] = [grant("documents")]
    assert w.service.answer(tid)["citations"] == [] and "answer_withheld" in w.service.answer(tid)["limitations"]


def test_purging_one_type_leaves_tasks_of_another_type_alone(tmp_path):
    w = World(tmp_path, [grant("documents"), grant("mail")])
    d = run(w, scope=["documents"], key="idem-key-doc1")
    m = run(w, scope=["mail"], key="idem-key-mail")
    before = w.service.answer(m)
    assert w.service.purge_source_type("documents") == 1
    assert w.service.answer(m) == before and w.service.answer(d)["citations"] == []


def test_purge_is_atomic_when_it_fails_midway(tmp_path):
    w = World(tmp_path, [grant("documents")])
    tid = run(w)
    before = dump(w)

    def boom(task_id, used):
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        w.store.purge_type("documents", boom)
    assert dump(w) == before and w.service.answer(tid)["citations"]


# ---- concurrency ------------------------------------------------------------------------------------------------------------------------------------------
def test_concurrent_submits_with_one_idempotency_key_create_one_task(tmp_path):
    w = World(tmp_path, [grant("documents")])
    ids, errors = [], []

    def go():
        try:
            ids.append(w.service.submit(request())[0]["task_id"])
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=go) for _ in range(12)]
    [t.start() for t in threads]
    [t.join(10) for t in threads]
    assert not errors and len(set(ids)) == 1 and len(w.store.ids_in(("queued",))) == 1


def test_concurrent_runs_of_different_tasks_all_complete_with_their_own_answers(tmp_path):
    w = World(tmp_path, [grant("documents")])
    tids = [w.service.submit(request(key=f"idem-key-{i:04d}"))[0]["task_id"] for i in range(8)]
    errors = []

    def go(t):
        try:
            w.service.run(t)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=go, args=(t,)) for t in tids]
    [t.start() for t in threads]
    [t.join(20) for t in threads]
    assert not errors and {w.store.record(t)["state"] for t in tids} == {"completed"}
    assert all(len([e for e in w.store.events_after(t, 0) if e["type"] == "final"]) == 1 for t in tids)


def test_a_cancel_racing_a_run_ends_in_exactly_one_consistent_terminal_state(tmp_path):
    for i in range(10):
        (tmp_path / f"w{i}").mkdir()
        w = World(tmp_path / f"w{i}", [grant("documents")])
        tid = w.service.submit(request())[0]["task_id"]
        t = threading.Thread(target=w.service.run, args=(tid,))
        c = threading.Thread(target=w.service.cancel, args=(tid,))
        t.start(), c.start(), t.join(10), c.join(10)
        rec = w.store.record(tid)
        closing = [e for e in w.store.events_after(tid, 0) if e["type"] in ("final", "error")]
        assert rec["state"] in ("completed", "partially_completed", "cancelled") and len(closing) == 1


def test_a_cancel_between_the_queued_check_and_the_start_leaves_the_cancelled_outcome_untouched(tmp_path):
    w = World(tmp_path, [grant("documents")])
    tid = w.service.submit(request())[0]["task_id"]
    real = w.service._to

    def cancel_first(task_id, state, **kw):
        if state == "running":
            w.store.request_cancel(task_id, w.clock())
        return real(task_id, state, **kw)

    w.service._to = cancel_first
    assert w.service.run(tid)["state"] == "cancelled" and w.retriever.calls == []
