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
from typing import Protocol

from .gate import ModelAnswer, ModelContext, ModelUnavailable
from .models import ManifestEntry, ModelRejected, ModelStore, VerifiedModel

ROUTE_POLICY_VERSION = "1"
MODES = ("default", "research")
REASONS = (  # closed; content-free
    "primary", "research_deep", "fallback_unavailable", "fallback_memory", "fallback_failed", "capability_required", "reduced_context", "refused_memory",
)  # fmt: skip
MAX_CONCURRENCY = 2  # one interactive plus one background
DEFAULT_CONTEXT = 32768


class RuntimeFailure(Exception):
    """A runtime could not produce an answer (load failure, out of memory, internal error). Never carries content."""


class ModelRuntime(Protocol):
    """What the gateway needs from an inference engine. `complete` may raise RuntimeFailure; `load` is given only verified, read-only files."""

    def load(self, verified: VerifiedModel) -> None: ...
    def unload(self, model_id: str) -> None: ...
    def loaded(self) -> frozenset[str]: ...
    def complete(self, model_id: str, context: ModelContext, max_context: int) -> ModelAnswer: ...


@dataclass(frozen=True)
class Identity:
    """Content-free description of the model that answered (maps to the API 1.1 ModelDescriptor)."""

    model_id: str
    role: str
    runtime: str


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

    `acquire(kind)` blocks until a slot of that kind is free; a background request waits while an interactive one is waiting or running. `should_yield()` is polled by background work.
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

    def should_yield(self) -> bool:
        with self._cond:
            return self._waiting_interactive > 0


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
    """`ModelGateway` implementation: verified models only, deterministic routing, capability-preserving fallback, one answer per call carrying the model identity."""

    def __init__(
        self,
        store: ModelStore,
        router: Router,
        runtime: ModelRuntime,
        scheduler: Scheduler | None = None,
        memory: MemoryProbe | None = None,
        signals: Callable[[], Signals] | None = None,
        deep_extra_bytes: int = 0,
    ) -> None:
        self._store, self._router, self._rt = store, router, runtime
        self._sched = scheduler or Scheduler()
        self._memory, self._signals = memory, signals or Signals
        self.context_tokens = DEFAULT_CONTEXT
        self._lock = threading.Lock()
        self._deep_extra = deep_extra_bytes

    def _ensure_loaded(self, entry: ManifestEntry) -> None:
        if entry.model_id in self._rt.loaded():
            if not self._store.still_verified(self._store.verify_for_load(entry.model_id)):
                self._rt.unload(entry.model_id)
                raise ModelRejected("identity_changed")
            return
        for other in sorted(self._rt.loaded()):  # one resident model at a time (the deep tier: the primary is unloaded first): a fallback replaces, never joins
            self._rt.unload(other)
        if self._memory is not None and self._memory.available_bytes() < entry.resident_bytes + self._deep_extra:
            raise RuntimeFailure("memory")
        verified = self._store.verify_for_load(entry.model_id)
        self._rt.load(verified)
        if not self._store.still_verified(verified):
            self._rt.unload(entry.model_id)
            raise ModelRejected("identity_changed")

    def _entry(self, model_id: str) -> ManifestEntry:
        return self._store._manifest.get(model_id)

    def generate(self, context: ModelContext) -> ModelAnswer:
        signals = self._signals()
        route = self._router.route(signals)
        kind = signals.priority
        if not self._sched.acquire(kind, timeout=30):
            raise ModelUnavailable("busy")
        try:
            return self._run(route, context)
        finally:
            self._sched.release(kind)

    def _run(self, route: Route, context: ModelContext) -> ModelAnswer:
        for model_id in route.chain:
            entry = self._entry(model_id)
            try:
                with self._lock:
                    self._ensure_loaded(entry)
                answer = self._rt.complete(model_id, context, min(self.context_tokens, entry.context_tokens))
            except (RuntimeFailure, ModelRejected):
                continue
            return replace(answer, identity=(entry.model_id, entry.role, entry.runtime))
        raise ModelUnavailable("no_model")


__all__ = [
    "DEFAULT_CONTEXT", "MAX_CONCURRENCY", "MODES", "ORDER", "REASONS", "ROUTE_POLICY_VERSION", "DegradationPlanner", "DegradationStep", "Gateway", "Identity", "MemoryProbe",
    "ModelRuntime", "Route", "Router", "RuntimeFailure", "Scheduler", "Signals",
]  # fmt: skip
