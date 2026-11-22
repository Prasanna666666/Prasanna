"""The Intelligence Gateway: deterministic model routing, capability-preserving fallback, bounded scheduling and the memory degradation order.

Recorded decisions (DECISIONS §8, INTELLIGENCE_AND_PERFORMANCE.md §5, §7.1): one resident primary; a text fallback and a multimodal fallback; the deep tier only when the owner selects
Research mode, with the primary unloaded first (never two large models resident); selection only from explicit structured signals (the owner's mode, the capabilities the request
needs), never from a semantic router; never swap, never cloud, never silently change model or quantisation; every answer carries the identity of the model that produced it.

This module implements the existing `ModelGateway` protocol, so the Core still reaches a model only through `GatedModel` (policy re-checked on every call, including a fallback
switch: a switch happens inside one `generate`, under the same permit and context). Nothing here opens a network connection or reads a path from a request.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from functools import partial
from typing import Protocol

from .events import SafeLog, new_id
from .gate import ModelAnswer, ModelContext, ModelUnavailable
from .models import ManifestEntry, ModelRejected, ModelStore, VerifiedModel

ROUTE_POLICY_VERSION = "1"
MODES = ("default", "research")
MAX_CONCURRENCY = 2  # one interactive plus one background
DEFAULT_CONTEXT = 32768


class RuntimeFailure(Exception):
    """A runtime could not produce an answer (load failure, out of memory, internal error). Never carries content."""


class Preempted(Exception):
    """An inference was stopped, at a safe boundary, because it was asked to yield (an interactive request is waiting, or memory is short). Carries nothing."""


class ModelRuntime(Protocol):
    """What the gateway needs from an inference engine. `complete` may raise RuntimeFailure; `load` is given only verified, read-only files."""

    def load(self, verified: VerifiedModel) -> None: ...
    def unload(self, model_id: str) -> None: ...
    def loaded(self) -> frozenset[str]: ...
    def complete(self, model_id: str, context: ModelContext, max_context: int, should_stop: Callable[[], bool]) -> ModelAnswer: ...


@dataclass(frozen=True)
class Signals:
    """The only inputs to routing: explicit and structured. The question text is never inspected."""

    mode: str = "default"
    priority: str = "interactive"  # or "background"
    needs: frozenset[str] = frozenset({"text"})  # capabilities required by the request's attachments, from their declared types


@dataclass(frozen=True)
class Route:
    chain: tuple[str, ...]  # model ids in order of preference
    reason: str
    policy_version: str = ROUTE_POLICY_VERSION


class Router:
    """A fixed, versioned function of (mode, needs, what is approved). Fallbacks must keep every capability the request needs: never drop image or audio, never go remote."""

    def __init__(self, entries: Sequence[ManifestEntry]) -> None:
        self._entries = {e.model_id: e for e in entries}

    def route(self, signals: Signals) -> Route:
        if signals.mode not in MODES or signals.priority not in ("interactive", "background"):
            raise ModelUnavailable("unknown_mode")
        need = set(signals.needs)
        by_role: dict[str, list[ManifestEntry]] = {}
        for entry in sorted(self._entries.values(), key=lambda e: e.model_id):
            if need <= set(entry.capabilities):
                by_role.setdefault(entry.role, []).append(entry)
        order = (
            ("deep", "primary", "multimodal_fallback", "text_fallback") if signals.mode == "research" else ("primary", "multimodal_fallback", "text_fallback")
        )
        chain = tuple(e.model_id for role in order for e in by_role.get(role, ()))
        if not chain:
            raise ModelUnavailable("capability_required")
        first = self._entries[chain[0]]
        return Route(chain, "research_deep" if first.role == "deep" else ("primary" if first.role == "primary" else "fallback_unavailable"))


class MemoryProbe(Protocol):
    def available_bytes(self) -> int: ...


class Scheduler:
    """At most two concurrent inferences (one interactive, one background); interactive work has priority and background work yields at the next boundary.

    `acquire(kind)` blocks until a slot of that kind is free; a background request waits while an interactive one is waiting or running.
    """

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._running = {"interactive": 0, "background": 0}
        self._waiting_interactive = 0
        self.peak = 0

    def acquire(self, kind: str, timeout: float | None = None) -> bool:
        if kind not in self._running:
            raise ValueError(kind)
        with self._cond:
            if kind == "interactive":
                self._waiting_interactive += 1
            try:
                ok = self._cond.wait_for(lambda: self._free(kind), timeout)
            finally:
                if kind == "interactive":
                    self._waiting_interactive -= 1
                    self._cond.notify_all()  # a background request held back by this waiter must re-check now, not only at the next release
            if not ok:
                return False
            self._running[kind] += 1
            self.peak = max(self.peak, sum(self._running.values()))
            return True

    def _free(self, kind: str) -> bool:
        if self._running[kind] >= 1:
            return False
        if kind == "background" and self._waiting_interactive:
            return False
        return sum(self._running.values()) < MAX_CONCURRENCY

    def release(self, kind: str) -> None:
        with self._cond:
            self._running[kind] -= 1
            self._cond.notify_all()


@dataclass(frozen=True)
class DegradationStep:
    action: str  # one of ORDER
    detail: str = ""


ORDER = ("stop_background", "evict_caches", "pause_background", "shrink_context", "reduced_profile", "refuse")


class DegradationPlanner:
    """Memory pressure handling in the recorded order. Each call returns the NEXT step to take given how many bytes are still missing; the order is fixed, never swap, never cloud."""

    def __init__(self) -> None:
        self._done = 0

    def next_step(self, missing_bytes: int) -> DegradationStep:
        if missing_bytes <= 0:
            self._done = 0
            return DegradationStep("none")
        step = ORDER[min(self._done, len(ORDER) - 1)]
        self._done += 1
        return DegradationStep(step)

    def reset(self) -> None:
        self._done = 0


class Gateway:
    """`ModelGateway` implementation: verified models only, deterministic routing, capability-preserving fallback, one answer per call carrying the model identity.

    Two models are never resident together and a model is never unloaded while an inference is using it. Interactive work has priority IN FLIGHT: a background inference polls
    `should_stop` between pieces of output and is stopped (the background caller gets `ModelUnavailable("preempted")` and may retry) as soon as an interactive request is waiting, an
    interactive request needs a different model, or memory pressure holds background work. An interactive request that must wait for another model waits a bounded time, then gets
    `ModelUnavailable("busy")`. When memory is short the recorded degradation order is followed step by step (`DegradationPlanner`); the need is the weights plus the context
    (`kv_bytes_per_token`, to be set from the Mac benchmark) so shrinking the context really lowers it. Never swap to disk, never go remote.
    """

    MIN_CONTEXT = 4096
    SWITCH_WAIT_SECONDS = 30.0  # how long a request waits for another model's inference to finish before it is refused as busy

    def __init__(  # noqa: PLR0913, PLR0917  (each part is a separate injected seam)
        self,
        store: ModelStore,
        router: Router,
        runtime: ModelRuntime,
        scheduler: Scheduler | None = None,
        memory: MemoryProbe | None = None,
        signals: Callable[[], Signals] | None = None,
        evict: Callable[[], None] | None = None,
        log: SafeLog | None = None,
        kv_bytes_per_token: int = 0,
    ) -> None:
        self._store, self._router, self._rt = store, router, runtime
        self._sched = scheduler or Scheduler()
        self._memory, self._signals, self._evict = memory, signals or Signals, evict or (lambda: None)
        self._log = log
        self._kv = kv_bytes_per_token
        self.context_tokens = DEFAULT_CONTEXT
        self.background_held = (
            False  # set while memory is short: running background inference is stopped and new background requests are refused (ModelUnavailable "held")
        )
        self._planner = DegradationPlanner()
        self._cond = threading.Condition()
        self._active: dict[str, int] = {}  # model id -> inferences running on it
        self._switchers = 0  # interactive requests waiting for another model to become free
        self._staged: dict[str, VerifiedModel] = {}  # model id -> the verified staged folder it was loaded from

    # -- loading ---------------------------------------------------------------------------------------------------------------------------
    def _unload(self, model_id: str) -> None:
        self._rt.unload(model_id)
        staged = self._staged.pop(model_id, None)
        if staged is not None:
            self._store.release(staged)

    def _prepare(self, entry: ManifestEntry) -> None:
        """Make `entry` the one loaded model. Called with the condition held and no other model in use."""
        if entry.model_id in self._rt.loaded():
            staged = self._staged.get(entry.model_id)
            if staged is None or not self._store.still_verified(staged):
                self._unload(entry.model_id)
                raise ModelRejected("identity_changed")
            return
        for other in sorted(self._rt.loaded()):  # one resident model at a time (the deep tier: the primary is unloaded first): a fallback replaces, never joins
            self._unload(other)
        self._make_room(entry)
        staged = self._store.stage(self._store.verify_for_load(entry.model_id))
        try:
            self._rt.load(staged)
            self._staged[entry.model_id] = staged
            if not self._store.still_verified(staged):
                raise ModelRejected("identity_changed")
        except BaseException:
            self._unload(entry.model_id)
            self._store.release(staged)
            raise

    def _needed(self, entry: ManifestEntry) -> int:
        return entry.resident_bytes + min(self.context_tokens, entry.context_tokens) * self._kv

    def _make_room(self, entry: ManifestEntry) -> None:
        if self._memory is None:
            return
        self._planner.reset()
        self.context_tokens = DEFAULT_CONTEXT  # every load starts from the full context; a shrink below lasts as long as this model stays loaded
        while (missing := self._needed(entry) - self._memory.available_bytes()) > 0:
            step = self._planner.next_step(missing).action
            if step in ("stop_background", "pause_background"):
                self.background_held = True  # running background inference sees this at its next piece of output and stops
            elif step == "evict_caches":
                self._evict()
            elif step == "shrink_context":
                self.context_tokens = max(self.MIN_CONTEXT, self.context_tokens // 2)
            else:  # reduced_profile: this model does not fit, the caller moves to the next one in the chain; refuse: there is none (the caller reports unavailable)
                raise RuntimeFailure("memory")
        self.background_held = False  # pressure relieved

    def _only_using(self, model_id: str) -> bool:
        return all(m == model_id for m, n in self._active.items() if n)

    def _entry(self, model_id: str) -> ManifestEntry:
        return self._store.entry(model_id)

    # -- answering -------------------------------------------------------------------------------------------------------------------------
    def generate(self, context: ModelContext) -> ModelAnswer:
        signals = self._signals()
        route = self._router.route(signals)
        background = signals.priority == "background"
        if background and self.background_held:
            raise ModelUnavailable("held")
        if not self._sched.acquire(signals.priority, timeout=30):
            raise ModelUnavailable("busy")
        try:
            return self._run(route, context, background)
        finally:
            self._sched.release(signals.priority)

    def _should_stop(self, background: bool) -> bool:
        """Polled by a running inference. Only background work ever yields."""
        return background and (self.background_held or self._switchers > 0)

    def _acquire_model(self, entry: ManifestEntry, background: bool) -> None:
        """Wait (bounded) until nobody is using a different model, then make `entry` the loaded one and count this inference. Called with the condition held."""
        waiting = not self._only_using(entry.model_id)
        if waiting and not background:
            self._switchers += 1  # tells a running background inference to stop
            self._cond.notify_all()
        try:
            if not self._cond.wait_for(partial(self._only_using, entry.model_id), timeout=self.SWITCH_WAIT_SECONDS):
                raise ModelUnavailable("busy")
        finally:
            if waiting and not background:
                self._switchers -= 1
        self._prepare(entry)
        self._active[entry.model_id] = self._active.get(entry.model_id, 0) + 1

    def _run(self, route: Route, context: ModelContext, background: bool) -> ModelAnswer:
        skipped: str | None = None  # why an earlier model in the chain was not used
        for position, model_id in enumerate(route.chain):
            entry = self._entry(model_id)
            try:
                with self._cond:
                    self._acquire_model(entry, background)
                context_tokens = min(self.context_tokens, entry.context_tokens)
                try:
                    answer = self._rt.complete(model_id, context, context_tokens, partial(self._should_stop, background))
                finally:
                    with self._cond:
                        self._active[entry.model_id] -= 1
                        self._cond.notify_all()
            except Preempted:
                raise ModelUnavailable("preempted") from None
            except (RuntimeFailure, ModelRejected) as error:
                skipped = "memory_fallback" if str(error) == "memory" else "fallback_model"
                continue
            first = "deep_model" if route.reason == "research_deep" else "primary_model"
            reason = (skipped or "fallback_model") if position else first  # position > 0 only after a failure, which set `skipped`
            self._routed(context, reason, entry)
            return replace(answer, identity=(entry.model_id, entry.role, entry.runtime))
        self._routed(context, "model_refused", None)
        raise ModelUnavailable("no_model")

    def _routed(self, context: ModelContext, reason: str, entry: ManifestEntry | None) -> None:
        """One content-free `model.routed` event per answer: which model, in which role, and why (a closed vocabulary). Never a prompt, path or passage."""
        if self._log is None:
            return
        fields: dict[str, str] = {"reason_code": reason}
        if entry is not None:
            fields |= {"role": entry.role, "model_id": entry.model_id}
        self._log.emit("model.routed", "model", context.permit_id or new_id(), **fields)


__all__ = [
    "DEFAULT_CONTEXT", "MAX_CONCURRENCY", "MODES", "ORDER", "ROUTE_POLICY_VERSION", "DegradationPlanner", "DegradationStep", "Gateway", "MemoryProbe",
    "ModelRuntime", "Preempted", "Route", "Router", "RuntimeFailure", "Scheduler", "Signals",
]  # fmt: skip
