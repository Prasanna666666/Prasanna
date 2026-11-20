"""Synthetic fixtures only: invented sources, invented sentinels. No real data of the owner is used anywhere in these tests."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from atlas_core.answer import LanguageIn
from atlas_core.events import SafeLog
from atlas_core.evidence import StoredSource, sha256_text
from atlas_core.gate import ModelAnswer, ModelContext, ModelUnavailable
from atlas_core.identity import ClientRegistry, sign_request
from atlas_core.policy import InMemoryGrants, PolicyEngine
from atlas_core.service import Deps, FaultInjector, TaskService
from atlas_core.tasks import TaskStore

KEY = "test-only-task-store-key-0001"
T0 = datetime(2026, 11, 20, 12, 0, 0, tzinfo=UTC)

SENTINEL_QUESTION = "QUESTION-SENTINEL-what-is-the-secret-total"
SENTINEL_DOC = "DOCTEXT-SENTINEL-4471"
SENTINEL_FIN = "FINANCE-SENTINEL-8841"
SENTINEL_HEALTH = "HEALTH-SENTINEL-2207"
SENTINEL_ATTACH = "ATTACH-SENTINEL-5530"
SENTINEL_SUBJECT = "SUBJECT-SENTINEL-6612"
SENTINEL_EMAIL = "owner.sentinel@example.invalid"
SENTINEL_FILENAME = "filename-sentinel-9035.pdf"
ALL_SENTINELS = (SENTINEL_QUESTION, SENTINEL_DOC, SENTINEL_FIN, SENTINEL_HEALTH, SENTINEL_ATTACH, SENTINEL_SUBJECT, SENTINEL_EMAIL, SENTINEL_FILENAME, KEY)

DOC_PAGE1 = f"Invoice {SENTINEL_DOC}: the total due is 1250.50 euro."
DOC_PAGE2 = "Payment received on 2026-03-14."
DOC_TEXT = DOC_PAGE1 + "\n" + DOC_PAGE2
MAIL_HEADERS = f"Subject: {SENTINEL_SUBJECT} From: {SENTINEL_EMAIL}"
MAIL_BODY = "Hello, the meeting is on 2026-04-02."
MAIL_TEXT = MAIL_HEADERS + "\n" + MAIL_BODY
DUTCH_TEXT = "Totaal bedrag: 1.250,50 euro. 支払い期限は2026-03-31です。"


def source(source_id: str, source_type: str, text: str, **extra: Any) -> StoredSource:
    return StoredSource(source_id, source_type, text, **extra)


CORPUS = [
    source("doc00001", "documents", DOC_TEXT, page_starts=(0, len(DOC_PAGE1) + 1), blocks=((0, len(DOC_PAGE1)), (len(DOC_PAGE1) + 1, len(DOC_TEXT)))),
    source("docnl001", "documents", DUTCH_TEXT),
    source("mail0001", "mail", MAIL_TEXT, parts={"headers": (0, len(MAIL_HEADERS)), "body": (len(MAIL_HEADERS) + 1, len(MAIL_TEXT))}),
    source("att00001", "mail_attachment", f"Attachment {SENTINEL_ATTACH}"),
    source("fin00001", "finance", f"Statement {SENTINEL_FIN} balance 99999.99"),
    source("hlth0001", "health", f"Result {SENTINEL_HEALTH} blood pressure 120"),
]


class FixtureStore:
    def __init__(self, sources: Iterable[StoredSource] = CORPUS) -> None:
        self.sources = {s.source_id: s for s in sources}

    def get(self, source_id: str) -> StoredSource | None:
        return self.sources.get(source_id)


def evidence(src: StoredSource, start: int, end: int, locator: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "source_id": src.source_id,
        "source_type": src.source_type,
        "version_sha256": sha256_text(src.text),
        "locator": locator or {"kind": "span_only"},
        "span": {"start": start, "end": end},
    }


def passage(src: StoredSource, start: int, end: int, locator: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"evidence": evidence(src, start, end, locator), "text": src.text[start:end]}


@dataclass
class StubRetriever:
    """Returns the first passage of every source of the asked type. `misbehave` makes it return a passage of another type (a hostile retriever)."""

    store: FixtureStore
    calls: list[str] = field(default_factory=list)
    misbehave: str | None = None
    only: set[str] | None = None  # return passages only for these source types (the others are searched but find nothing)

    def search(self, source_type: str, query: str) -> list[dict[str, Any]]:
        self.calls.append(source_type)
        wanted = self.misbehave or source_type
        out = []
        for src in self.store.sources.values():
            if src.source_type != wanted or (self.only is not None and src.source_type not in self.only):
                continue
            if src.page_starts:
                out.append(passage(src, 0, len(DOC_PAGE1), {"kind": "page", "page": 1}))
                out.append(passage(src, src.page_starts[1], len(src.text), {"kind": "page", "page": 2}))
            elif src.parts:
                start, end = src.parts["body"]
                out.append(passage(src, start, end, {"kind": "message_part", "message_part": "body"}))
            else:
                out.append(passage(src, 0, len(src.text)))
        return out


@dataclass
class StubModel:
    """A model that answers from the first passage it is given. `mode` selects a failure to test."""

    mode: str = "ok"
    answer_text: str = "The total due is 1250.50 euro."
    quote: str = "1250.50"
    calls: list[ModelContext] = field(default_factory=list)
    on_call: Any = None
    language: LanguageIn = field(default_factory=lambda: LanguageIn(detected="en", requested="en", confidence=0.95))

    def generate(self, context: ModelContext) -> ModelAnswer:
        self.calls.append(context)
        if self.on_call:
            self.on_call()
        if self.mode == "unavailable":
            raise ModelUnavailable
        first = context.passages[0]
        ev = first["evidence"]
        text, quote = self.answer_text, self.quote
        if self.mode == "extra_figure":
            text = "The total due is 1250.50 euro and 777.77 was paid."
        if self.mode == "bad_quote":
            quote = "not in the source"
        if self.mode == "stale":
            ev = {**ev, "version_sha256": "0" * 64}
        if self.mode == "not_retrieved":
            ev = evidence(CORPUS[1], 0, 5)
        if self.mode == "no_citation":
            return ModelAnswer(text, (), self.language)
        if self.mode == "dates":
            text = "Payment was received on 2026-03-14 and again on 2026-05-05."
            quote = "2026-03-14"
            ev = evidence(CORPUS[0], len(DOC_PAGE1) + 1, len(DOC_TEXT), {"kind": "page", "page": 2})
        return ModelAnswer(text, ({"evidence": ev, "quote": quote},), self.language)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def grant(source_type: str, *, sensitivity: str = "high", revoked: bool = False, expires: str | None = None) -> dict[str, Any]:
    return {"grant_id": f"grant-{source_type}-01", "source_type": source_type, "max_sensitivity": sensitivity, "designated_by": "owner", "purpose": "answer_question",
            "issued_at": "2026-11-01T00:00:00+00:00", "expires_at": expires, "revoked": revoked}  # fmt: skip


def request(
    scope: list[str] | None = None, key: str = "idem-key-0001", objective: str = SENTINEL_QUESTION, max_retries: int = 2, seconds: int = 120
) -> dict[str, Any]:
    return {
        "objective": objective,
        "source_scope": scope or ["documents"],
        "budget": {"max_seconds": seconds, "max_retries": max_retries},
        "idempotency_key": key,
    }


class World:
    """One running Core on an encrypted store in a temp folder; `restart()` builds a new service on the same store, as after a crash."""

    def __init__(self, folder: Path, grants: list[dict[str, Any]], model: StubModel | None = None) -> None:
        self.folder = folder
        self.lines: list[str] = []
        self.log = SafeLog(self.lines.append)
        self.clock, self.faults = Clock(), FaultInjector()
        self.sources, self.model = FixtureStore(), model or StubModel()
        self.retriever = StubRetriever(self.sources)
        self.grants = InMemoryGrants(grants)
        self.store = TaskStore(folder / "tasks.db", KEY)
        self.service = self._service()

    def _service(self) -> TaskService:
        deps = Deps(self.store, PolicyEngine(self.grants), self.retriever, self.model, self.sources, self.log, self.faults, self.clock)
        return TaskService(deps)

    def restart(self) -> None:
        self.store.close()
        self.store = TaskStore(self.folder / "tasks.db", KEY)
        self.service = self._service()
        self.service.recover()

    def run_new(self, req: dict[str, Any]) -> dict[str, Any]:
        record, _ = self.service.submit(req)
        return self.service.run(record["task_id"]) if record["state"] == "queued" else record


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path, [grant("documents")])


@pytest.fixture
def registry_and_key() -> tuple[ClientRegistry, Ed25519PrivateKey]:
    key = Ed25519PrivateKey.generate()
    registry = ClientRegistry()
    registry.register("client-mac-0001", key.public_key())
    return registry, key


def signed(
    key: Ed25519PrivateKey, method: str, target: str, body: bytes, now: datetime, client: str = "client-mac-0001", nonce: str | None = None
) -> dict[str, str]:
    return sign_request(key, client, method, target, body, now, nonce)


def all_output(world: World, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]) -> str:
    """Everything the Core could have written anywhere during a test: its event sink, Python logging at every level, standard output and error."""
    captured = capsys.readouterr()
    return "\n".join([*world.lines, *(r.getMessage() for r in caplog.records), captured.out, captured.err])


@pytest.fixture(autouse=True)
def _everything_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)


def parse_events(lines: list[str]) -> list[dict[str, Any]]:
    return [json.loads(line) for line in lines]
