"""WP3.4a: routing, capability-preserving fallback, one resident model, deep tier, scheduling, degradation order. Deterministic stub runtime; no model is loaded."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from conftest import CORPUS, T0, grant, labels, passage
from test_models import RECORD_KEY, entry_dict, signed

from atlas_core.gate import ContextBuilder, GatedModel, ModelAnswer, ModelUnavailable
from atlas_core.intelligence import DegradationPlanner, Gateway, Router, RuntimeFailure, Scheduler, Signals
from atlas_core.models import ModelRejected, ModelStore
from atlas_core.policy import InMemoryGrants, PolicyEngine


class FakeRuntime:
    def __init__(self) -> None:
        self._loaded: set[str] = set()
        self.fail: set[str] = set()
        self.history: list[tuple[str, str]] = []
        self.max_resident = 0
        self.delay = 0.0

    def load(self, verified) -> None:
        self.history.append(("load", verified.entry.model_id))
        self._loaded.add(verified.entry.model_id)
        self.max_resident = max(self.max_resident, len(self._loaded))

    def unload(self, model_id: str) -> None:
        self.history.append(("unload", model_id))
        self._loaded.discard(model_id)

    def loaded(self) -> frozenset[str]:
        return frozenset(self._loaded)

    def complete(self, model_id, context, max_context):
        if self.delay:
            time.sleep(self.delay)
        if model_id in self.fail:
            raise RuntimeFailure("x")
        return ModelAnswer(f"from {model_id}")


class Mem:
    def __init__(self, free: int) -> None:
        self.free = free

    def available_bytes(self) -> int:
        return self.free


SPECS = [
    ("prim", "primary", ["text", "image", "audio"]),
    ("tfb", "text_fallback", ["text"]),
    ("mfb", "multimodal_fallback", ["text", "image", "audio"]),
    ("deep", "deep", ["text", "image"]),
]


def world(tmp_path: Path, specs=SPECS, sizes=None, **kw):
    entries = []
    for mid, role, caps in specs:
        files = {"w.safetensors": mid.encode()}
        d = tmp_path / mid
        d.mkdir()
        (d / "w.safetensors").write_bytes(files["w.safetensors"])
        entries.append(entry_dict(mid, files, role=role, capabilities=caps, resident_bytes=(sizes or {}).get(mid, 100)))
    manifest = signed(entries)
    store = ModelStore(tmp_path, manifest, RECORD_KEY)
    for mid, *_ in specs:
        store.import_model(mid)
    rt = FakeRuntime()
    sig = {"s": Signals()}
    gw = Gateway(store, Router(manifest.entries()), rt, signals=lambda: sig["s"], **kw)
    return gw, rt, sig, store


def context():
    _, token = PolicyEngine(InMemoryGrants([grant("documents")])).decide(["documents"], T0)
    return ContextBuilder(labels()).build(token, "q", [passage(CORPUS[0], 0, 10)], T0), token


def test_default_uses_the_primary_and_the_answer_carries_its_identity(tmp_path):
    gw, _rt, _, _ = world(tmp_path)
    answer = gw.generate(context()[0])
    assert answer.text == "from prim" and answer.identity == ("prim", "primary", "stub")


def test_the_gate_remains_the_only_door_and_the_identity_survives_it(tmp_path):
    gw, *_ = world(tmp_path)
    ctx, token = context()
    assert GatedModel(gw, labels()).generate(token, ctx, T0).identity[0] == "prim"


def test_routing_ignores_the_question_text_and_is_deterministic(tmp_path):
    gw, *_ = world(tmp_path)
    r1 = gw._router.route(Signals())
    assert r1 == gw._router.route(Signals())
    assert r1.chain == ("prim", "mfb", "tfb") and r1.reason == "primary"
    assert "question" not in Signals.__dataclass_fields__


def test_research_mode_selects_the_deep_tier_and_unloads_the_primary_first(tmp_path):
    gw, rt, sig, _ = world(tmp_path)
    gw.generate(context()[0])
    sig["s"] = Signals(mode="research")
    assert gw.generate(context()[0]).identity[0] == "deep"
    assert rt.history.index(("unload", "prim")) < rt.history.index(("load", "deep"))
    assert rt.max_resident == 1


def test_never_two_models_resident_even_across_fallbacks(tmp_path):
    gw, rt, *_ = world(tmp_path)
    rt.fail = {"prim"}
    assert gw.generate(context()[0]).identity[0] == "mfb"
    assert rt.max_resident == 1 and rt.loaded() == {"mfb"}


def test_text_requests_may_fall_back_to_the_text_model_but_image_requests_never_do(tmp_path):
    gw, rt, sig, _ = world(tmp_path)
    rt.fail = {"prim", "mfb"}
    assert gw.generate(context()[0]).identity[0] == "tfb"
    sig["s"] = Signals(needs=frozenset({"text", "image"}))
    before = len(rt.history)
    with pytest.raises(ModelUnavailable):  # the only remaining image-capable models failed: never drop the image, never go remote
        gw.generate(context()[0])
    assert ("load", "tfb") not in rt.history[before:]


def test_a_request_needing_a_capability_nobody_has_is_unavailable_not_degraded(tmp_path):
    gw, *_ = world(tmp_path, specs=[("prim", "primary", ["text"])])
    gw._signals = lambda: Signals(needs=frozenset({"text", "audio"}))
    with pytest.raises(ModelUnavailable, match="capability_required"):
        gw.generate(context()[0])


def test_an_unknown_mode_or_priority_is_refused(tmp_path):
    gw, *_ = world(tmp_path)
    for s in (Signals(mode="turbo"), Signals(priority="vip")):
        with pytest.raises(ModelUnavailable):
            gw._router.route(s)


def test_a_model_not_imported_or_tampered_never_loads_and_the_chain_moves_on(tmp_path):
    gw, rt, _, _ = world(tmp_path)
    p = tmp_path / "prim" / "w.safetensors"
    p.chmod(0o644)
    p.write_bytes(b"EVIL")
    assert gw.generate(context()[0]).identity[0] == "mfb"
    assert ("load", "prim") not in rt.history


def test_all_models_failing_is_model_unavailable(tmp_path):
    gw, rt, *_ = world(tmp_path)
    rt.fail = {"prim", "mfb", "tfb"}
    with pytest.raises(ModelUnavailable, match="no_model"):
        gw.generate(context()[0])


def test_a_swap_between_verify_and_use_unloads_and_refuses(tmp_path):
    gw, rt, _, _ = world(tmp_path)
    gw.generate(context()[0])
    p = tmp_path / "prim" / "w.safetensors"
    p.chmod(0o644)
    p.write_bytes(b"SWAPPED")
    answer = gw.generate(context()[0])  # the loaded primary no longer matches: unloaded, and the chain continues
    assert answer.identity[0] != "prim" and "prim" not in rt.loaded()


def test_not_enough_memory_skips_the_model_never_swaps(tmp_path):
    gw, rt, *_ = world(tmp_path, memory=Mem(50))
    with pytest.raises(ModelUnavailable):
        gw.generate(context()[0])
    assert rt.loaded() == frozenset() and not any(h[0] == "load" for h in rt.history)


def test_concurrency_is_capped_at_two_with_one_interactive_and_one_background(tmp_path):
    s = Scheduler()
    assert s.acquire("interactive") and s.acquire("background")
    assert not s.acquire("interactive", timeout=0.05) and not s.acquire("background", timeout=0.05)
    s.release("background")
    assert s.acquire("background") and s.peak == 2


def test_a_waiting_interactive_request_holds_back_new_background_work(tmp_path):
    s = Scheduler()
    assert s.acquire("interactive") and s.acquire("background")  # both slots busy
    started: list[str] = []

    def waiter(kind: str) -> None:
        if s.acquire(kind, timeout=3):
            started.append(kind)

    c = threading.Thread(target=waiter, args=("interactive",))
    c.start()
    time.sleep(0.05)
    assert s.should_yield()  # running background work polls this and yields at a safe boundary
    s.release("background")  # a slot frees up: the waiting interactive request is ahead of any new background request
    d = threading.Thread(target=waiter, args=("background",))
    d.start()
    time.sleep(0.1)
    assert started == []  # background must not take the slot while an interactive request waits
    s.release("interactive")
    s.release("interactive")  # A finishes: C (waiting longer, and interactive) starts, then D
    c.join(2)
    d.join(2)
    assert started == ["interactive", "background"]  # the waiting interactive request went first


def test_a_released_slot_after_a_failure_is_not_leaked(tmp_path):
    gw, rt, *_ = world(tmp_path)
    rt.fail = {"prim", "mfb", "tfb"}
    for _ in range(3):
        with pytest.raises(ModelUnavailable):
            gw.generate(context()[0])
    assert gw._sched.acquire("interactive", timeout=0.1)


def test_degradation_follows_the_recorded_order_and_resets_when_pressure_ends():
    p = DegradationPlanner()
    steps = [p.next_step(1).action for _ in range(8)]
    assert steps[:6] == ["stop_background", "evict_caches", "pause_background", "shrink_context", "reduced_profile", "refuse"] and steps[6:] == [
        "refuse",
        "refuse",
    ]
    assert p.next_step(0).action == "none" and p.next_step(1).action == "stop_background"
    assert "swap" not in str(steps) and "cloud" not in str(steps)


def test_gateway_never_opens_a_network_connection(tmp_path, monkeypatch):
    import socket

    def boom(*a, **k):
        raise AssertionError("network")

    monkeypatch.setattr(socket.socket, "connect", boom)
    gw, *_ = world(tmp_path)
    assert gw.generate(context()[0]).text == "from prim"


def test_rejection_reasons_are_codes_not_paths(tmp_path):
    _, _, _, store = world(tmp_path)
    p = tmp_path / "tfb" / "w.safetensors"
    p.chmod(0o644)
    p.write_bytes(b"x")
    with pytest.raises(ModelRejected) as e:
        store.import_model("tfb")
    assert str(tmp_path) not in str(e.value) and e.value.reason == "digest_mismatch"


class Shrinking:
    """Free memory that grows by one step each time the gateway takes a degradation action."""

    def __init__(self, free: int, gain: int) -> None:
        self.free, self.gain, self.log = free, gain, []

    def available_bytes(self) -> int:
        return self.free

    def freed(self, action: str) -> None:
        self.log.append(action)
        self.free += self.gain


def test_memory_pressure_follows_the_recorded_order_and_stops_as_soon_as_the_model_fits(tmp_path):
    mem = Shrinking(0, 40)  # the primary needs 100: three actions free enough
    gw, *_ = world(tmp_path, memory=mem, evict=lambda: mem.freed("evict_caches"))
    gw._memory = mem
    real_next = gw._planner.next_step

    def next_step(missing):
        step = real_next(missing)
        if step.action != "evict_caches":
            mem.freed(step.action)
        return step

    gw._planner.next_step = next_step
    assert gw.generate(context()[0]).identity[0] == "prim"
    assert mem.log == ["stop_background", "evict_caches", "pause_background"] and gw.background_held is False and gw.context_tokens == 32768


def test_when_nothing_frees_enough_the_next_smaller_model_is_tried_then_the_request_is_refused(tmp_path):
    class Fixed:
        def available_bytes(self):
            return 50  # every model in this world needs 100

    gw, rt, *_ = world(tmp_path, memory=Fixed())
    with pytest.raises(ModelUnavailable):
        gw.generate(context()[0])
    assert (
        gw.context_tokens == 4096 and gw.background_held is True and rt.loaded() == frozenset()
    )  # shrunk, background held, nothing loaded; never swapped, never remote
    bg = Signals(priority="background")
    gw._signals = lambda: bg
    with pytest.raises(ModelUnavailable, match="held"):
        gw.generate(context()[0])


def test_a_model_is_never_unloaded_while_another_request_is_using_it(tmp_path):
    gw, rt, *_ = world(tmp_path)
    inside, release, order = threading.Event(), threading.Event(), []
    real = rt.complete

    def slow(model_id, ctx, n):
        order.append(("start", model_id))
        if model_id == "prim":
            inside.set()
            release.wait(5)
        order.append(("end", model_id))
        return real(model_id, ctx, n)

    rt.complete = slow
    first = threading.Thread(target=lambda: gw.generate(context()[0]))
    first.start()
    assert inside.wait(5)
    results = {}

    def deep():
        gw._signals = lambda: Signals(mode="research", priority="background")
        results["x"] = gw.generate(context()[0]).identity[0]

    second = threading.Thread(target=deep)
    second.start()
    time.sleep(0.2)
    assert ("unload", "prim") not in rt.history and rt.max_resident == 1  # the deep model waits for the primary's inference to finish
    release.set()
    first.join(5)
    second.join(5)
    assert results["x"] == "deep" and order.index(("end", "prim")) < order.index(("start", "deep")) and rt.max_resident == 1


def routed_events(lines):
    import json as _json

    return [_json.loads(x) for x in lines if '"model.routed"' in x]


def test_every_answer_logs_one_content_free_routing_event_with_a_closed_reason(tmp_path):
    from atlas_core import contracts
    from atlas_core.events import SafeLog

    lines: list[str] = []
    gw, rt, sig, _ = world(tmp_path)
    gw._log = SafeLog(lines.append)
    gw.generate(context()[0])  # the primary
    rt.fail = {"prim"}
    gw.generate(context()[0])  # a fallback after the primary failed
    sig["s"] = Signals(mode="research")
    rt.fail = set()
    gw.generate(context()[0])  # the deep tier
    rt.fail = {"deep", "prim", "mfb", "tfb"}
    with pytest.raises(ModelUnavailable):
        gw.generate(context()[0])
    events = routed_events(lines)
    assert [(e.get("model_id"), e["reason_code"]) for e in events] == [
        ("prim", "primary_model"),
        ("mfb", "fallback_model"),
        ("deep", "deep_model"),
        (None, "model_refused"),
    ]
    for e in events:
        contracts.validate("SafeEvent", e, "1.1")
    assert "from prim" not in "".join(lines) and "question" not in "".join(lines)


def test_a_memory_driven_fallback_is_logged_as_such(tmp_path):
    from atlas_core.events import SafeLog

    class Tight:
        def available_bytes(self):
            return 200  # the primary needs 500 and nothing the gateway can do frees more; the next model needs 100

    lines: list[str] = []
    gw, *_ = world(tmp_path, sizes={"prim": 500}, memory=Tight())
    gw._log = SafeLog(lines.append)
    assert gw.generate(context()[0]).identity[0] == "mfb"
    assert [e["reason_code"] for e in routed_events(lines)] == ["memory_fallback"]
    assert gw.context_tokens == 32768 and gw.background_held is False  # relieved once a model fitted
