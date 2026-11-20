"""The task pipeline: policy, retrieval, model, verification, in that order, each step checkpointed so a restart resumes instead of repeating.

Nothing here talks HTTP and nothing here touches a database directly: the API calls this service, and this service uses the task store, the policy gate and the
evidence checks.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .answer import AnswerInput, build_envelope, denied_envelope, stopped_envelope, withheld_envelope
from .errors import CoreError, user_error
from .events import SafeLog
from .evidence import SourceStore
from .gate import ContextBuilder, GatedModel, GatedRetrieval, ModelGateway, ModelUnavailable, Retriever
from .policy import PermitToken, PolicyEngine, PolicyViolation
from .tasks import STEPS, TERMINAL, TaskStore
from .values import LanguageIn

FINAL_STATE = {"verified": "completed", "partially_verified": "partially_completed", "unverified": "partially_completed"}
FAIL_REASON = {"failed": "citation_failed"}


class SimulatedCrash(Exception):
    """Raised by the fault injector in tests: the process 'dies' here."""


class FaultInjector:
    """Tests arm a boundary name; the pipeline 'crashes' the first time it passes it."""

    def __init__(self) -> None:
        self.armed: set[str] = set()
        self.passed: list[str] = []

    def hit(self, name: str) -> None:
        self.passed.append(name)
        if name in self.armed:
            self.armed.discard(name)
            raise SimulatedCrash(name)


class _Stop(Exception):
    def __init__(self, record: dict[str, Any]) -> None:
        super().__init__("stopped")
        self.record = record


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class Deps:
    store: TaskStore
    policy: PolicyEngine
    retriever: Retriever
    model: ModelGateway
    sources: SourceStore
    log: SafeLog = field(default_factory=SafeLog)
    faults: FaultInjector = field(default_factory=FaultInjector)
    clock: Callable[[], datetime] = _now


class TaskService:
    def __init__(self, deps: Deps) -> None:
        self._d = deps
        self._retrieval, self._builder, self._model = GatedRetrieval(), ContextBuilder(), GatedModel(deps.model)

    # -- submitting, cancelling, recovering ------------------------------------------------------------------------------------------------
    def submit(self, request: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        d, now = self._d, self._d.clock()
        decision, token = d.policy.decide(request["source_scope"], now)
        record, created = d.store.create(request, decision, now)
        task_id = record["task_id"]
        if not created:
            return record, False
        d.log.emit("task.created", "service", task_id)
        d.log.emit(
            "policy.decision",
            "policy",
            task_id,
            decision=decision["decision"],
            reason_code=decision["reason_code"],
            count=len(decision["permitted_source_types"]),
        )
        self._to(task_id, "policy_checked", step="policy_checked")
        if token is None:
            self._deny(task_id, request["source_scope"], decision["denied"])
        else:
            self._to(task_id, "queued")
        return d.store.record(task_id), True

    def _deny(self, task_id: str, requested: list[str], denied: list[dict[str, str]]) -> None:
        """End a task whose sources are not permitted, saying what actually happened: before retrieval 'nothing was searched'; after retrieval but before a draft the task 'was
        stopped, no answer produced'; once a draft or answer existed it is 'withheld'."""
        step, data = self._d.store.checkpoint(task_id)
        rank = STEPS.index(step)
        attempted = frozenset(data.get("retrieval_started", []))
        # CONFIRMED means retrieved content from that source type is durably recorded (it appears in the saved passages). The marker alone proves only that a search was attempted:
        # a source that returned nothing, or whose passages were never saved, stays 'attempted'; it is never promoted to confirmed.
        confirmed = frozenset(p["evidence"]["source_type"] for p in data.get("passages", []))
        if rank < STEPS.index("retrieved") and not attempted:
            envelope = denied_envelope(task_id, requested, denied)
        elif rank < STEPS.index("drafted"):
            envelope = stopped_envelope(task_id, denied, confirmed, attempted)
        else:
            envelope = withheld_envelope(task_id, denied, confirmed, attempted)
        self._d.store.save_answer(task_id, envelope)
        self._to(task_id, "failed", reason="denied")
        self._d.store.append_event(task_id, {"type": "error", "error": user_error("source_denied", task_id)})

    def cancel(self, task_id: str) -> dict[str, Any]:
        record = self._d.store.request_cancel(task_id, self._d.clock())
        if record["state"] == "cancelled":
            self._d.store.append_event(task_id, {"type": "state", "state": "cancelled"})
        return record

    def recover(self) -> list[tuple[str, str]]:
        """Run once at start-up, before serving: interrupted tasks resume from their checkpoint or end as needs-attention."""
        done = self._d.store.recover(self._d.clock())
        for task_id, action in done:
            state = self._d.store.record(task_id)["state"]
            self._d.store.append_event(task_id, {"type": "state", "state": state})
            if action == "needs_attention":
                self._d.store.append_event(task_id, {"type": "error", "error": user_error("needs_attention", task_id)})
            self._d.log.emit("task.recovered", "tasks", task_id, reason_code=action, state_to=state)
        return done

    def expire_due(self) -> list[str]:
        expired = self._d.store.expire_due(self._d.clock())
        for task_id in expired:
            self._d.store.append_event(task_id, {"type": "error", "error": user_error("task_expired", task_id)})
        return expired

    # -- running -----------------------------------------------------------------------------------------------------------------------------
    def run(self, task_id: str) -> dict[str, Any]:
        """Run a queued task to a terminal state, or resume one that recovery queued again. Returns the task as it ends."""
        try:
            return self._run(task_id)
        except _Stop as stop:
            return stop.record
        except PolicyViolation:  # a retriever or a caller tried to go around the policy: the task ends, nothing it found is used
            self._fail(task_id, "needs_attention")
            return self._d.store.record(task_id)

    def _run(self, task_id: str) -> dict[str, Any]:
        d = self._d
        record = d.store.record(task_id)
        if record["state"] in TERMINAL:
            return record
        if record["state"] != "queued":
            raise CoreError("conflict")
        self._to(task_id, "running")
        step, data = d.store.checkpoint(task_id)
        done = STEPS.index(step)
        self._catch_up(task_id, done)
        decision, token = self._token(task_id, record["source_scope"])
        self._revalidate(task_id, record["source_scope"], decision, token, data, done)
        question = d.store.objective(task_id)
        passages = data["passages"] if done >= STEPS.index("retrieved") else self._retrieve(task_id, token, question)
        if done < STEPS.index("drafted"):
            self._draft(task_id, token, question, passages)
        envelope = d.store.answer(task_id) if done >= STEPS.index("verified") else self._verify(task_id, record, passages, decision["denied"])
        return self._finish(task_id, envelope)

    def _catch_up(self, task_id: str, done: int) -> None:
        """A resumed task walks through the states it had already reached (nothing is recomputed) so the lifecycle stays strict."""
        for state in ("retrieved", "drafted", "verified")[: max(0, done - 1)]:
            self._to(task_id, state)

    def _token(self, task_id: str, scope: list[str]) -> tuple[dict[str, Any], PermitToken]:
        decision, token = self._d.policy.decide(scope, self._d.clock())  # decided again now: a grant may have been revoked since the task was made
        if token is None:
            self._deny(task_id, scope, decision["denied"])
            raise _Stop(self._d.store.record(task_id))
        return decision, token

    def _revalidate(self, task_id: str, scope: list[str], decision: dict[str, Any], token: PermitToken, data: dict[str, Any], done: int) -> None:
        """Work saved under an earlier permission (retrieved passages, a draft's citations, a verified answer) is used only if every source it touches is still permitted now.
        If any is not (a grant was revoked while another stayed), the task fails closed: nothing saved is reused and the stale answer is replaced."""
        d, now = self._d, self._d.clock()
        touched = {p["evidence"]["source_type"] for p in data.get("passages", [])} | {c["evidence"]["source_type"] for c in data.get("citations", [])}
        if done >= STEPS.index("verified"):
            touched |= _cited_types(d.store.answer(task_id))
        revoked = frozenset(t for t in touched if not token.allows(t, now))
        if revoked:
            self._deny(task_id, scope, _denied_now(decision, revoked))
            raise _Stop(d.store.record(task_id))

    def _boundary(self, task_id: str) -> None:
        d, now = self._d, self._d.clock()
        record = d.store.record(task_id)
        if record["cancel_requested"]:
            self._to(task_id, "cancelled", reason="cancelled")
            d.store.append_event(task_id, {"type": "error", "error": user_error("task_cancelled", task_id)})
            raise _Stop(d.store.record(task_id))
        if now >= datetime.fromisoformat(record["deadline"]):
            self._to(task_id, "expired", reason="expired")
            d.store.append_event(task_id, {"type": "error", "error": user_error("task_expired", task_id)})
            raise _Stop(d.store.record(task_id))

    def _retrieve(self, task_id: str, token: PermitToken, question: str) -> list[dict[str, Any]]:
        d = self._d
        self._boundary(task_id)
        d.faults.hit("before:retrieved")
        d.store.note(
            task_id, {"retrieval_started": sorted(token.permitted)}, d.clock()
        )  # durable BEFORE the search: a crash after it must not look untouched (source types only, no content); it proves an ATTEMPT, not a retrieval
        d.faults.hit("after:attempt")
        passages = self._retrieval.fetch(token, d.retriever, question, d.clock())
        d.log.emit("retrieval.finished", "gate", task_id, count=len(passages))
        d.faults.hit("mid:retrieved")
        self._to(task_id, "retrieved", step="retrieved", data={"passages": passages})
        d.faults.hit("after:retrieved")
        return passages

    def _draft(self, task_id: str, token: PermitToken, question: str, passages: list[dict[str, Any]]) -> None:
        d = self._d
        self._boundary(task_id)
        d.faults.hit("before:drafted")
        context = self._builder.build(token, question, passages, d.clock())
        d.log.emit("model.requested", "gate", task_id, count=len(context.passages))
        try:
            answer = self._model.generate(token, context, d.clock())
        except ModelUnavailable:
            self._fail(task_id, "model_unavailable")
            raise _Stop(d.store.record(task_id)) from None
        d.faults.hit("mid:drafted")
        payload = {"draft": answer.text, "citations": list(answer.citations), "truncated": context.truncated, "language": vars(answer.language)}
        self._to(task_id, "drafted", step="drafted", data=payload)
        d.faults.hit("after:drafted")

    def _verify(self, task_id: str, record: dict[str, Any], passages: list[dict[str, Any]], denied: list[dict[str, str]]) -> dict[str, Any]:
        d = self._d
        self._boundary(task_id)
        d.faults.hit("before:verified")
        saved = d.store.checkpoint(task_id)[1]
        item = AnswerInput(
            task_id,
            saved["draft"],
            saved["citations"],
            record["source_scope"],
            denied,
            [p["evidence"] for p in passages],
            saved["truncated"],
            False,
            LanguageIn(**saved["language"]),
        )
        envelope = build_envelope(item, d.sources)
        d.log.emit("answer.verified", "answer", task_id, reason_code=envelope["verification"]["status"])
        d.store.save_answer(task_id, envelope)
        d.faults.hit("mid:verified")
        self._to(task_id, "verified", step="verified")
        d.faults.hit("after:verified")
        return envelope

    def _finish(self, task_id: str, envelope: dict[str, Any]) -> dict[str, Any]:
        d = self._d
        status = envelope["verification"]["status"]
        d.faults.hit("before:final")
        if status == "failed":
            self._to(task_id, "failed", reason=FAIL_REASON[status])
            d.store.append_event(task_id, {"type": "error", "error": user_error("citation_failed", task_id)})
        else:
            self._to(task_id, FINAL_STATE[status], reason="completed" if status == "verified" else "partial")
            d.store.append_event(task_id, {"type": "final", "answer": envelope})
        return d.store.record(task_id)

    def _fail(self, task_id: str, reason: str) -> None:
        self._to(task_id, "failed", reason=reason)
        self._d.store.append_event(task_id, {"type": "error", "error": user_error(reason, task_id)})

    def _to(self, task_id: str, state: str, *, step: str | None = None, data: dict[str, Any] | None = None, reason: str | None = None) -> None:
        d = self._d
        before = d.store.record(task_id)["state"]
        if before == state:
            return
        d.store.transition(task_id, state, d.clock(), step=step, data=data, reason=reason)
        d.store.append_event(task_id, {"type": "state", "state": state})
        if step in ("retrieved", "drafted", "verified"):
            d.store.append_event(task_id, {"type": "progress", "step": step})
        d.log.emit("task.transition", "tasks", task_id, state_from=before, state_to=state)

    # -- reading (what the API serves) -----------------------------------------------------------------------------------------------------
    def get(self, task_id: str) -> dict[str, Any]:
        return self._d.store.record(task_id)

    def answer(self, task_id: str) -> dict[str, Any]:
        """The saved answer, unless a source it was built from is no longer permitted: then the owner gets a plain 'not allowed any more' answer, never the old content.
        'Built from' is every source type of the passages retrieved for the task, not only the cited ones: an uncited draft still came from them."""
        envelope = self._d.store.answer(task_id)
        record = self._d.store.record(task_id)
        if record["terminal_reason"] == "denied":
            return envelope  # already a safe answer (nothing searched, stopped, or withheld): it carries no source content
        scope = record["source_scope"]
        decision, token = self._d.policy.decide(scope, self._d.clock())
        permitted = token.permitted if token is not None else frozenset()
        used = self._used_types(task_id, envelope)
        if used <= permitted:
            return envelope
        return withheld_envelope(task_id, _denied_now(decision, used - permitted), used)

    def _used_types(self, task_id: str, envelope: dict[str, Any]) -> frozenset[str]:
        """Every source type the answer was constructed from: the retrieved passages saved with the task's checkpoint plus whatever the answer cites."""
        passages = self._d.store.checkpoint(task_id)[1].get("passages", [])
        return frozenset(p["evidence"]["source_type"] for p in passages) | _cited_types(envelope)

    def receipt(self, task_id: str) -> dict[str, Any]:
        return self._d.store.receipt(task_id)

    def events_after(self, task_id: str, after: int) -> list[dict[str, Any]]:
        """Stream events; a final answer built from a source no longer permitted is replaced by a plain error event (same sequence number)."""
        scope = self._d.store.record(task_id)["source_scope"]
        _, token = self._d.policy.decide(scope, self._d.clock())
        permitted = token.permitted if token is not None else frozenset()
        out = []
        for event in self._d.store.events_after(task_id, after):
            leaks = event["type"] == "final" and not self._used_types(task_id, event["answer"]) <= permitted
            out.append({"seq": event["seq"], "task_id": task_id, "type": "error", "error": user_error("source_denied", task_id)} if leaks else event)
        return out


def _cited_types(envelope: dict[str, Any]) -> frozenset[str]:
    return frozenset(c["evidence"]["source_type"] for c in envelope["citations"])


def _denied_now(decision: dict[str, Any], revoked: frozenset[str]) -> list[dict[str, str]]:
    known = {d["source_type"] for d in decision["denied"]}
    return [*decision["denied"], *({"source_type": t, "reason_code": "grant_revoked"} for t in sorted(revoked) if t not in known)]
