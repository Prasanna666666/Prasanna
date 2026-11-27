"""The task pipeline: policy, retrieval, model, verification, in that order, each step checkpointed so a restart resumes instead of repeating.

Nothing here talks HTTP and nothing here touches a database directly: the API calls this service, and this service uses the task store, the policy gate and the
evidence checks.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from .answer import NO_EVIDENCE_TEXT, AnswerInput, build_envelope, denied_envelope, stopped_envelope, withheld_envelope
from .coverage import Provider as CoverageProvider
from .coverage import build_coverage, required_limitations
from .egress import Denied, EgressGateway, TaintSet
from .errors import CoreError, user_error
from .events import SafeLog
from .evidence import CitationError, SourceStore, resolve
from .exact import ExactError, compute
from .finance_calc import MONEY_DOMAIN, by_category, by_month, month_over_month, previous_month, transactions
from .gate import ContextBuilder, GatedModel, GatedRetrieval, ModelGateway, ModelUnavailable, Retriever, SourceLabels
from .health_calc import HEALTH_DOMAIN, summarise
from .policy import PermissionRevoked, PermitToken, PolicyEngine, PolicyViolation
from .records import Record
from .review import run_review
from .rules import load_rules
from .tasks import STEPS, TERMINAL, TaskStore
from .values import LanguageIn

HIGHLIGHTS_QUESTION = "What are the most important things in my enabled sources right now? Give a short summary with the key dates and any follow-ups."
FINAL_STATE = {"verified": "completed", "partially_verified": "partially_completed", "unverified": "partially_completed"}
FAIL_REASON = {"failed": "citation_failed"}


class ConsentPort(Protocol):
    """What the API needs for the owner's consent and the index status (implemented by `consent.ConsentService`; every call is audited and single-use by request id)."""

    def state(self) -> dict[str, Any]: ...
    def enable(self, sources: list[str], request_id: str) -> dict[str, Any]: ...
    def revoke(self, grant_id: str, request_id: str) -> dict[str, Any]: ...
    def index_status(self) -> dict[str, Any]: ...


class OpsPort(Protocol):
    """What the API needs for the owner's actions and a device's sync (implemented by `operations.Operations`)."""

    def act(self, action: str, payload: dict[str, Any], idempotency_key: str, approval_id: str | None) -> dict[str, Any]: ...
    def approve(self, approval_id: str) -> dict[str, Any]: ...
    def undo(self, action_id: str) -> dict[str, Any]: ...
    def sync(self, device_id: str, ops: list[dict[str, Any]]) -> dict[str, Any]: ...
    def attention(self) -> dict[str, Any]: ...
    def records(self, domain: str) -> dict[str, Any]: ...


class DevicesPort(Protocol):
    """What the API needs for device pairing and revocation (implemented by `operations.DeviceOperations`)."""

    def offer(self, by_client: str) -> dict[str, Any]: ...
    def pair(self, body: dict[str, Any]) -> dict[str, Any]: ...
    def listing(self) -> dict[str, Any]: ...
    def revoke(self, by_client: str, device_id: str) -> dict[str, Any]: ...


class ConnectorsPort(Protocol):
    """What the API needs for connectors (implemented by `connectors.ConnectorHub`)."""

    def listing(self) -> dict[str, Any]: ...
    def link(self, connector_id: str, fields: Mapping[str, str]) -> dict[str, Any]: ...
    def check(self, connector_id: str) -> dict[str, Any]: ...
    def unlink(self, connector_id: str) -> dict[str, Any]: ...


class WebPort(Protocol):
    """What the API needs for reading a page the owner chose (implemented by `web.WebReader`)."""

    def hosts(self) -> dict[str, Any]: ...
    def add(self, host: str) -> dict[str, Any]: ...
    def remove(self, host: str) -> dict[str, Any]: ...
    def read(self, url: str) -> dict[str, Any]: ...


class UpdatesPort(Protocol):
    """What the API needs for updates (implemented by `updater.UpdateOperations`). A failure raises an object with a `code`."""

    def status(self) -> dict[str, Any]: ...
    def install_from(self, folder: Any) -> dict[str, Any]: ...
    def rollback(self) -> dict[str, Any]: ...


class ModePort(Protocol):
    """The owner's selected model mode (`default` or `research`); kept by the composition root and read by the gateway on every call."""

    def get(self) -> str: ...
    def set(self, mode: str) -> None: ...


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


@dataclass(frozen=True)
class ResearchGate:
    """Public web research is OFF unless both a gateway is configured AND `enabled` is set: an explicit live-network gate that nothing in the Core sets by itself."""

    gateway: EgressGateway | None = None
    enabled: bool = False


# the gateway's refusal codes, mapped to the closed vocabulary of the `egress.decision` event
EGRESS_REASON = {
    "private_content_in_request": "leak_check",
    "identifier_in_request": "leak_check",
    "restricted_context": "restricted_domain",
    "destination_not_allowed": "url_not_permitted",
    "unsupported_response": "url_not_permitted",
    "destination_not_public": "private_address",
    "too_many_redirects": "redirect_blocked",
    "bad_request": "length_cap",
    "unavailable": "failed",
}


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
    coverage: Mapping[str, CoverageProvider] = field(default_factory=dict)  # per source type: what that index reports (used only to build the API 1.1 coverage)
    research: ResearchGate = field(default_factory=ResearchGate)
    health_records: Callable[[], list[Record]] | None = None  # the Health records, when this Core has a Health source (read only after the grant check)
    scope: Callable[[], list[str]] = (
        list  # the source types a question may use right now (a current grant and the platform permission; never a restricted domain)
    )
    finance_records: Callable[[], list[Record]] | None = None  # the Finance records, when this Core has a Finance source (read only under a current grant)


class TaskService:
    def __init__(self, deps: Deps) -> None:
        self._d = deps
        labels = self._labels = SourceLabels(deps.sources)
        self._retrieval, self._builder = GatedRetrieval(labels), ContextBuilder(labels)
        self._model = GatedModel(deps.model, labels, deps.policy, deps.clock)

    # -- submitting, cancelling, recovering ------------------------------------------------------------------------------------------------
    def device_may_ask(self, sources: list[str]) -> bool:
        """Whether a paired (non-owner) device may put a task over these sources: the policy data names the device ceiling."""
        return load_rules().device_may_ask(sources)

    def creator(self, task_id: str) -> str | None:
        return self._d.store.creator(task_id)

    def submit(self, request: dict[str, Any], client: str | None = None) -> tuple[dict[str, Any], bool]:
        d, now = self._d, self._d.clock()
        decision, token = d.policy.decide(request["source_scope"], now)
        record, created = d.store.create(request, decision, now, client)
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
        self._to(
            task_id, "failed", reason="denied", events=[{"type": "error", "error": user_error("source_denied", task_id)}], answer=envelope
        )  # the safe answer commits with the state

    def cancel(self, task_id: str) -> dict[str, Any]:
        return self._d.store.request_cancel(task_id, self._d.clock())  # an immediate cancellation and its event commit together

    def recover(self) -> list[tuple[str, str]]:
        """Run once at start-up, before serving: interrupted tasks resume from their checkpoint or end as needs-attention."""
        done = self._d.store.recover(self._d.clock())
        for task_id, action in done:  # the state events were written in the same transactions as the recovery transitions
            self._d.log.emit("task.recovered", "tasks", task_id, reason_code=action, state_to=self._d.store.record(task_id)["state"])
        return done

    def expire_due(self) -> list[str]:
        return self._d.store.expire_due(self._d.clock())

    # -- running -----------------------------------------------------------------------------------------------------------------------------
    def run(self, task_id: str) -> dict[str, Any]:
        """Run a queued task to a terminal state, or resume one that recovery queued again. Returns the task as it ends."""
        try:
            return self._run(task_id)
        except _Stop as stop:
            return stop.record
        except (
            PermissionRevoked
        ) as revoked:  # a grant was revoked after the task started: stop before anything more is read or sent, and say what actually happened
            record = self._d.store.record(task_id)
            self._deny(task_id, record["source_scope"], revoked.denied)
            return self._d.store.record(task_id)
        except PolicyViolation:  # a retriever or a caller tried to go around the policy: the task ends, nothing it found is used
            self._fail(task_id, "needs_attention")
            return self._d.store.record(task_id)
        except CoreError as error:
            record = self._d.store.record(task_id)
            if (
                error.code == "conflict" and record["state"] in TERMINAL
            ):  # cancelled or expired by someone else between two steps: that outcome stands, nothing is overwritten
                return record
            raise

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
        revoked = frozenset(
            touched - self._valid_types(data, token, now)
        )  # same grant identity and ceiling as at retrieval, and every saved item still covered
        if revoked:
            self._deny(task_id, scope, _denied_now(decision, revoked))
            raise _Stop(d.store.record(task_id))

    def _valid_types(self, data: dict[str, Any], token: PermitToken, now: datetime) -> frozenset[str]:
        """The source types whose SAVED material may still be used under this token. A type qualifies only if the token's grant for it has the same identity and ceiling as the one the
        material was retrieved under (a revoke and re-grant, or a changed ceiling, never lets old data through, broader or not), and every saved passage of that type still has a
        trusted label (re-read from the source store) that the current ceiling covers. A missing binding or label fails closed."""
        bound = data.get("grant_binding", {})
        passages = data.get("passages", [])
        ok = set()
        for source_type in token.permitted:
            same = source_type in bound and tuple(bound[source_type]) == token.grants[source_type]
            covered = all(token.allows_item(source_type, self._labels.of(p), now) for p in passages if p["evidence"]["source_type"] == source_type)
            if same and covered:
                ok.add(source_type)
        return frozenset(ok)

    def _boundary(self, task_id: str) -> None:
        d, now = self._d, self._d.clock()
        record = d.store.record(task_id)
        if record["cancel_requested"]:
            self._to(task_id, "cancelled", reason="cancelled", events=[{"type": "error", "error": user_error("task_cancelled", task_id)}])
            raise _Stop(d.store.record(task_id))
        if now >= datetime.fromisoformat(record["deadline"]):
            self._to(task_id, "expired", reason="expired", events=[{"type": "error", "error": user_error("task_expired", task_id)}])
            raise _Stop(d.store.record(task_id))

    def _retrieve(self, task_id: str, token: PermitToken, question: str) -> list[dict[str, Any]]:
        d = self._d
        self._boundary(task_id)
        d.faults.hit("before:retrieved")
        d.store.note(
            task_id, {"retrieval_started": sorted(token.permitted)}, d.clock()
        )  # durable BEFORE the search: a crash after it must not look untouched (source types only, no content); it proves an ATTEMPT, not a retrieval
        d.faults.hit("after:attempt")
        result = self._retrieval.fetch(token, d.retriever, question, d.clock(), d.policy, d.clock)  # grants re-checked immediately before each source is read
        d.log.emit("retrieval.finished", "gate", task_id, count=len(result.passages))
        d.faults.hit("mid:retrieved")
        binding = {
            t: list(g) for t, g in token.grants.items()
        }  # the grant (identity, ceiling) this material was retrieved under: kept with it, never overwritten
        self._to(
            task_id,
            "retrieved",
            step="retrieved",
            data={"passages": result.passages, "excluded_sensitive": result.excluded_sensitive, "grant_binding": binding},
        )
        d.faults.hit("after:retrieved")
        return result.passages

    def _no_evidence(self, task_id: str) -> None:
        """Retrieval produced nothing usable (no match, or every item excluded by sensitivity): the model is never called. The 'draft' is a fixed plain statement with no citation
        and no source content, and the answer is marked partial and unverified, so nothing reads as an answer from sources."""
        payload = {"draft": NO_EVIDENCE_TEXT, "citations": [], "truncated": False, "language": vars(LanguageIn()), "partial": True}
        self._to(task_id, "drafted", step="drafted", data=payload)
        self._d.faults.hit("after:drafted")

    def _draft(self, task_id: str, token: PermitToken, question: str, passages: list[dict[str, Any]]) -> None:
        d = self._d
        self._boundary(task_id)
        d.faults.hit("before:drafted")
        if not passages:
            return self._no_evidence(task_id)
        context = self._builder.build(token, question, passages, d.clock())
        d.log.emit("model.requested", "gate", task_id, count=len(context.passages))
        try:
            answer = self._model.generate(token, context, d.clock())
        except ModelUnavailable:
            self._fail(task_id, "model_unavailable")
            raise _Stop(d.store.record(task_id)) from None
        d.faults.hit("mid:drafted")
        payload = {"draft": answer.text, "citations": list(answer.citations), "truncated": context.truncated, "language": vars(answer.language)}
        if answer.identity is not None:
            payload["model"] = dict(zip(("model_id", "role", "runtime"), answer.identity, strict=True))  # which local model wrote it (content-free)
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
            saved.get("partial", False),
            LanguageIn(**saved["language"]),
            saved.get("excluded_sensitive", 0),
        )
        envelope = build_envelope(item, d.sources)
        d.log.emit("answer.verified", "answer", task_id, reason_code=envelope["verification"]["status"])
        d.store.save_answer(task_id, envelope)
        d.faults.hit("mid:verified")
        covered = {p["evidence"]["source_type"] for p in passages} | (set(record["source_scope"]) - {x["source_type"] for x in denied})
        coverage = build_coverage(covered, d.coverage, d.clock())
        self._to(
            task_id, "verified", step="verified", data={"coverage": coverage, "coverage_types": sorted(covered)}
        )  # which sources the counts came from, so delivery can tell if one has since been withdrawn
        d.faults.hit("after:verified")
        return envelope

    def _finish(self, task_id: str, envelope: dict[str, Any]) -> dict[str, Any]:
        d = self._d
        status = envelope["verification"]["status"]
        d.faults.hit("before:final")
        if status == "failed":
            self._to(task_id, "failed", reason=FAIL_REASON[status], events=[{"type": "error", "error": user_error("citation_failed", task_id)}])
        else:
            self._to(task_id, FINAL_STATE[status], reason="completed" if status == "verified" else "partial", events=[{"type": "final", "answer": envelope}])
        return d.store.record(task_id)

    def _fail(self, task_id: str, reason: str) -> None:
        self._to(task_id, "failed", reason=reason, events=[{"type": "error", "error": user_error(reason, task_id)}])

    def _to(
        self,
        task_id: str,
        state: str,
        *,
        step: str | None = None,
        data: dict[str, Any] | None = None,
        reason: str | None = None,
        events: Sequence[dict[str, Any]] = (),
        answer: dict[str, Any] | None = None,
    ) -> None:
        """Change state; the state event, a progress event, any extra events and the answer (when given) are committed in the SAME transaction as the change."""
        d = self._d
        before = d.store.record(task_id)["state"]
        if before == state:
            return
        journal: list[dict[str, Any]] = [{"type": "state", "state": state}]
        if step in ("retrieved", "drafted", "verified"):
            journal.append({"type": "progress", "step": step})
        d.store.transition(task_id, state, d.clock(), step=step, data=data, reason=reason, events=[*journal, *events], answer=answer)
        d.log.emit("task.transition", "tasks", task_id, state_from=before, state_to=state)

    # -- reading (what the API serves) -----------------------------------------------------------------------------------------------------
    def get(self, task_id: str) -> dict[str, Any]:
        return self._d.store.record(task_id)

    def answer(self, task_id: str) -> dict[str, Any]:
        """The saved answer, unless a source it was built from is no longer permitted: then the owner gets a plain 'not allowed any more' answer, never the old content.
        'Built from' is every source type of the passages retrieved for the task, not only the cited ones: an uncited draft still came from them."""
        record = self._d.store.record(task_id)
        if record["state"] not in TERMINAL:
            raise CoreError(
                "conflict"
            )  # an answer is served only once the task has finished: a saved envelope of an unfinished task is a checkpoint, not a result
        envelope = self._d.store.answer(task_id)
        if record["terminal_reason"] == "denied":
            return envelope  # already a safe answer (nothing searched, stopped, or withheld): it carries no source content
        scope = record["source_scope"]
        decision, token = self._d.policy.decide(scope, self._d.clock())
        permitted = self._valid_types(self._d.store.checkpoint(task_id)[1], token, self._d.clock()) if token is not None else frozenset()
        used = self._used_types(task_id, envelope)
        if used <= permitted:
            return envelope
        return withheld_envelope(task_id, _denied_now(decision, used - permitted), used)

    def research(self, task_id: str, query: str) -> dict[str, Any]:
        """A public web search for one task (API 1.1), through the egress gateway and only when the live-network gate is on. The task's private context (its question and every passage retrieved for it)
        becomes the taint set, so a query that repeats anything private is refused before anything is sent, and a task whose scope or context holds Finance or Health data may not use the network at all.
        The result is untrusted data with provenance: it is returned to the owner's client and is never added to the task's evidence, its answer or its citations."""
        d = self._d
        gate = d.research
        if gate.gateway is None or not gate.enabled:
            d.log.emit("egress.decision", "egress", task_id, decision="deny", reason_code="provider_disabled", destination_class="search_provider")
            raise CoreError("forbidden", task_id)
        d.store.record(task_id)  # an unknown task is not_found
        rules = load_rules()
        taint = TaintSet()
        taint.add(d.store.objective(task_id), question=True)
        taint.restricted_in_context = any(rules.is_restricted(t) for t in d.store.record(task_id)["source_scope"])
        for passage in d.store.checkpoint(task_id)[1].get("passages", []):
            evidence = passage["evidence"]
            try:
                text = resolve(evidence, d.sources)  # the exact private text the model saw
            except CitationError:
                continue  # the source changed or went: that text can no longer be sent anywhere from here
            taint.add(text, restricted=rules.is_restricted(evidence["source_type"]))
        try:
            doc = gate.gateway.search(query, taint)
        except Denied as refused:
            d.log.emit(
                "egress.decision",
                "egress",
                task_id,
                decision="deny",
                reason_code=EGRESS_REASON.get(refused.code, "leak_check"),
                destination_class="search_provider",
            )
            raise CoreError("timeout" if refused.code == "unavailable" else "forbidden", task_id) from None
        d.log.emit("egress.decision", "egress", task_id, decision="allow", reason_code="allowed", destination_class="search_provider")
        return {
            "url": doc.url,
            "domain": doc.domain,
            "retrieved_at": doc.retrieved_at,
            "content_hash": doc.content_hash,
            "text": doc.text,
            "truncated": doc.truncated,
            "injection_flags": list(doc.injection_flags),
            "trust": doc.trust,
            "authority": doc.authority,
        }

    def library_search(self, query: str, scope: list[str]) -> dict[str, Any]:
        """Library (API 1.1): search what the owner enabled, through the same policy decision and the same gated retrieval a question uses, so nothing outside a current grant is read. Results are one entry per
        source with its best passage; the coverage of each source says how much has been read so far, so an incomplete index is never presented as a complete search. Access is checked once more after the last
        read and before anything is returned, against the exact grants the operation was authorised under."""
        d = self._d
        decision, token = d.policy.decide(scope, d.clock())
        if token is None:
            return {"state": "denied", "results": [], "coverage": []}
        found = self._retrieval.fetch(token, d.retriever, query, d.clock(), d.policy, d.clock).passages
        coverage = self._library_coverage(scope, decision)
        results = self._library_results(found)
        still_permitted, _withdrawn = d.policy.revalidate(token, d.clock())  # the final check: after the last material read, before delivery
        results = [r for r in results if r["source_type"] in still_permitted]
        for entry in coverage:
            if entry["source_type"] not in still_permitted:
                entry.update(total=0, searched=0, complete=False)
        incomplete = any(not c["complete"] for c in coverage)
        state = ("partial" if results else "partial_no_results") if incomplete else ("results" if results else "no_results")
        return {"state": state, "results": results, "coverage": coverage}

    def _library_coverage(self, scope: list[str], decision: dict[str, Any]) -> list[dict[str, Any]]:
        """One entry per requested source. A source that was not searched (no current grant, or no provider) is listed as unsearched with its counts withheld, so a no-match never reads as covering it."""
        coverage = []
        for source_type in sorted(set(scope)):
            provider = self._d.coverage.get(source_type)
            if provider is not None and source_type in decision["permitted_source_types"]:
                c = provider()
                coverage.append(
                    {
                        "source_type": source_type,
                        "total": int(c.get("total", 0)),
                        "searched": int(c.get("searched", 0)),
                        "complete": bool(c.get("complete", False)),
                    }
                )
            else:
                coverage.append({"source_type": source_type, "total": 0, "searched": 0, "complete": False})
        return coverage

    def _library_results(self, found: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        for passage in found:
            evidence = passage["evidence"]
            if evidence["source_id"] in seen:
                continue
            seen.add(evidence["source_id"])
            source = self._d.sources.get(evidence["source_id"])
            if source is None:
                continue
            results.append(
                {
                    "source_id": evidence["source_id"],
                    "source_type": evidence["source_type"],
                    "title": _title_of(source.text),
                    "excerpt": _tidy(str(passage.get("text", "")), 300),
                    "locator_kind": str(evidence["locator"].get("kind", "span_only")),
                }
            )
            if len(results) == LIBRARY_LIMIT:
                break
        return results

    def finance_summary(self) -> dict[str, Any]:
        """Spending by month and category (API 1.1), computed by code from the owner's Finance records and served only under a current grant for exactly that domain. Every figure is an exact sum of the
        transactions it names; the one percentage is rounded and labelled so. Without a Finance source the route does not exist; without a grant the answer is `denied` and nothing was read."""
        d = self._d
        if d.finance_records is None:
            raise CoreError("not_found")
        blank: dict[str, Any] = {"currency": "EUR", "transaction_count": 0, "months": [], "latest": None, "computed_by_code": True}
        _decision, token = d.policy.decide([MONEY_DOMAIN], d.clock())
        if token is None:
            return {"state": "denied", **blank}
        txs = transactions(d.finance_records())
        if MONEY_DOMAIN not in d.policy.revalidate(token, d.clock())[0]:
            return {"state": "denied", **blank}  # the final check, after the last read: a grant withdrawn while the records were read withholds the summary
        spending = by_month(txs)
        if not spending:
            return {"state": "empty", **blank, "transaction_count": len(txs)}
        month = max(spending)
        change = month_over_month(txs, month)
        has_previous = previous_month(month) in spending
        latest = {
            "month": month,
            "total": str(spending[month]),
            "categories": [{"category": c, "total": str(t)} for c, t in sorted(by_category(txs, month).items(), key=lambda kv: (-kv[1], kv[0]))],
            "previous_total": str(change.previous) if has_previous else None,
            "delta": str(change.delta) if has_previous else None,
            "percent": None if change.percent is None else str(change.percent),
        }
        return {
            "state": "ready",
            "currency": "EUR",
            "transaction_count": len(txs),
            "months": [{"month": m, "total": str(t)} for m, t in list(spending.items())[-12:]],
            "latest": latest,
            "computed_by_code": True,
        }

    def health_summary(self) -> dict[str, Any]:
        """Health readings summarised by code (API 1.1): per measure and unit the exact latest, minimum and maximum and a rounded, labelled average, each reading marked measured, estimated or unlabelled. Served only
        under a current grant for exactly the Health domain; without a Health source the route does not exist; without a grant the answer is `denied` and nothing was read. No advice is given."""
        d = self._d
        if d.health_records is None:
            raise CoreError("not_found")
        _decision, token = d.policy.decide([HEALTH_DOMAIN], d.clock())
        if token is None:
            return {"state": "denied", "reading_count": 0, "measures": [], "computed_by_code": True}
        records = [r for r in d.health_records() if r.domain == HEALTH_DOMAIN]
        if HEALTH_DOMAIN not in d.policy.revalidate(token, d.clock())[0]:
            return {"state": "denied", "reading_count": 0, "measures": [], "computed_by_code": True}  # the final check, after the last read
        if not records:
            return {"state": "empty", "reading_count": 0, "measures": [], "computed_by_code": True}
        return {"state": "ready", "reading_count": len(records), "measures": summarise(records)[:50], "computed_by_code": True}

    def highlights(self) -> dict[str, Any]:
        """Start (or find, for today) the owner's highlights: an ordinary question over the sources the owner has enabled, so the model sees only what the gate allows, every claim is cited and checked, and the answer is
        fetched with the task like any other. Nothing here reads a source or calls the model itself; the question is the same for everyone, so the same day gives the same task."""
        d = self._d
        scope = d.scope()
        if not scope:
            return {"state": "denied"}
        today = d.clock().strftime("%Y%m%d")
        request = {
            "objective": HIGHLIGHTS_QUESTION,
            "source_scope": sorted(scope),
            "budget": {"max_seconds": 300, "max_retries": 1},
            "idempotency_key": f"highlights-{today}-{'-'.join(sorted(scope))}"[:120],
        }
        record, _created = self.submit(request)
        return {"state": "ready", "task_id": record["task_id"]}

    def review(self, attention: Callable[[], dict[str, Any]] | None) -> dict[str, Any]:
        """The owner's review (API 1.1): the orchestrator over fixed code agents for calendar, finance and health. Each area answers only under its own grant and says plainly when it is off, empty or not offered."""
        return run_review(self.finance_summary, self.health_summary, attention, self.highlights)

    @staticmethod
    def compute(kind: str, args: list[str]) -> dict[str, Any]:
        """A typed deterministic computation (API 1.1 `/v1/compute`): exact arithmetic, units and dates by code, never a model. Reads no source; the text of an error is never echoed."""
        try:
            return compute(kind, args)
        except ExactError:
            raise CoreError("invalid_request") from None

    def passage(self, task_id: str, index: int) -> dict[str, Any]:
        """The text of one cited span of a finished task's answer (API 1.1), for the owner to inspect a citation. Fails closed: an unfinished task is a conflict, an answer withheld because
        a source is no longer permitted is `source_denied`, a missing citation is `not_found`, and a span that no longer resolves exactly (the source changed or went) is a conflict."""
        envelope = self.answer(task_id)
        if envelope != self._d.store.answer(task_id):
            raise CoreError("source_denied", task_id)
        if not 0 <= index < len(envelope["citations"]):
            raise CoreError("not_found", task_id)
        evidence = envelope["citations"][index]["evidence"]
        try:
            text = resolve(evidence, self._d.sources)
        except CitationError:
            raise CoreError("conflict", task_id) from None
        if (
            self.answer(task_id) != envelope
        ):  # the final check, after the last read and before the text leaves: a source withdrawn while it was being read is not delivered
            raise CoreError("source_denied", task_id)
        return {"citation_index": index, "text": text, "evidence": evidence}

    def purge_source_type(self, source_type: str) -> int:
        """Called when the owner revokes a source type (register it with `DesignationStore.register_purge`): the content that came from it is removed from every task."""
        denied = [{"source_type": source_type, "reason_code": "grant_revoked"}]
        return self._d.store.purge_type(source_type, lambda task_id, used: withheld_envelope(task_id, denied, used))

    def answer_v11(self, task_id: str) -> dict[str, Any]:
        """The API 1.1 form of the answer: the same envelope plus the coverage the answer was made under and, when a model wrote it, which model. The coverage limitations the
        1.1 contract ties to that coverage are added. An answer that was withheld, denied or stopped carries an empty coverage, never the index size of a source no longer permitted."""
        return self._upgrade(task_id, self.answer(task_id))

    def _upgrade(self, task_id: str, envelope: dict[str, Any]) -> dict[str, Any]:
        saved = self._d.store.checkpoint(task_id)[1]
        own = envelope == self._d.store.answer(task_id)  # the saved answer itself, not a withheld/denied replacement
        coverage = self._coverage_for_delivery(task_id, saved) if own and "coverage" in saved else build_coverage((), self._d.coverage, self._d.clock())
        out = {**envelope, "coverage": coverage, "limitations": list(dict.fromkeys([*envelope["limitations"], *required_limitations(coverage)]))}
        if own and "model" in saved:
            out["model"] = saved["model"]
        return out

    def _coverage_for_delivery(self, task_id: str, saved: dict[str, Any]) -> dict[str, Any]:
        """The coverage saved when the answer was made, if every source whose counts it holds is still permitted under the grants it was made
        under. Otherwise a conservative, incomplete coverage: unknown total, nothing claimed as searched, the answer-time timestamp, and no
        re-read of the live indexes. So a withdrawn source's counts are never delivered, and indexing done after the question is never
        reported as work the question searched."""
        d = self._d
        covered = frozenset(saved.get("coverage_types") or d.store.record(task_id)["source_scope"])
        _, token = d.policy.decide(d.store.record(task_id)["source_scope"], d.clock())
        permitted = self._valid_types(saved, token, d.clock()) if token is not None else frozenset()
        if covered <= permitted:
            return saved["coverage"]
        return {
            "state": "partial",
            "searched": 0,
            "total": None,
            "pending": [{"category": "not_yet_indexed", "count": 0}],
            "failed": [],
            "as_of": saved["coverage"]["as_of"],
        }

    def _used_types(self, task_id: str, envelope: dict[str, Any]) -> frozenset[str]:
        """Every source type the answer was constructed from: the retrieved passages saved with the task's checkpoint plus whatever the answer cites."""
        passages = self._d.store.checkpoint(task_id)[1].get("passages", [])
        return frozenset(p["evidence"]["source_type"] for p in passages) | _cited_types(envelope)

    def receipt(self, task_id: str) -> dict[str, Any]:
        return self._d.store.receipt(task_id)

    def guard_delivery(self, task_id: str, event: dict[str, Any]) -> dict[str, Any]:
        """The check made at the moment an event is handed to the client: a final answer whose sources are no longer permitted NOW is replaced by the plain error event (same sequence number), even if the
        batch it came in was judged a moment earlier."""
        if event["type"] != "final":
            return event
        scope = self._d.store.record(task_id)["source_scope"]
        _, token = self._d.policy.decide(scope, self._d.clock())
        permitted = self._valid_types(self._d.store.checkpoint(task_id)[1], token, self._d.clock()) if token is not None else frozenset()
        if not self._used_types(task_id, event["answer"]) <= permitted:
            return {"seq": event["seq"], "task_id": task_id, "type": "error", "error": user_error("source_denied", task_id)}
        if "coverage" in event["answer"]:  # an API 1.1 final event: its coverage is authorised again now, not when the batch was read
            event = {**event, "answer": self._upgrade(task_id, self._d.store.answer(task_id))}
        return event

    def events_after(self, task_id: str, after: int, version: str = "1.0") -> list[dict[str, Any]]:
        """Stream events; a final answer built from a source no longer permitted is replaced by a plain error event (same sequence number)."""
        scope = self._d.store.record(task_id)["source_scope"]
        _, token = self._d.policy.decide(scope, self._d.clock())
        permitted = self._valid_types(self._d.store.checkpoint(task_id)[1], token, self._d.clock()) if token is not None else frozenset()
        out = []
        for stored in self._d.store.events_after(task_id, after):
            event = stored
            if event["type"] == "final" and not self._used_types(task_id, event["answer"]) <= permitted:
                event = {"seq": stored["seq"], "task_id": task_id, "type": "error", "error": user_error("source_denied", task_id)}
            elif version == "1.1" and event["type"] == "final":
                event = {**event, "answer": self._upgrade(task_id, event["answer"])}
            out.append(event)
        return out


LIBRARY_LIMIT = 20
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


def _tidy(text: str, limit: int) -> str:
    """One line, no control characters, shortened: what a result row may show of a passage."""
    return _CONTROL.sub(" ", text).strip()[:limit]


def _title_of(text: str) -> str:
    """A human name for a source: its subject line if it has one (a message), otherwise its first non-empty line."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    subject = next((ln[len("Subject:") :].strip() for ln in lines if ln.startswith("Subject:")), "")
    return _tidy(subject or (lines[0] if lines else ""), 120)


def _cited_types(envelope: dict[str, Any]) -> frozenset[str]:
    return frozenset(c["evidence"]["source_type"] for c in envelope["citations"])


def _denied_now(decision: dict[str, Any], revoked: frozenset[str]) -> list[dict[str, str]]:
    known = {d["source_type"] for d in decision["denied"]}
    return [*decision["denied"], *({"source_type": t, "reason_code": "grant_revoked"} for t in sorted(revoked) if t not in known)]
