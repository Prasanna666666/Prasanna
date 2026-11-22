"""The composition root: the one place that builds a running Core from its parts and connects them (WP3 hardening).

It adds no behaviour of its own. It wires what the other modules already guarantee: the owner's designation gates every index and the policy; a revocation purges the index AND
everything the task store derived from it; the model is reached only through the gateway behind the policy gate; coverage comes from the indexes; the API is served on the owner-only
socket. Everything platform-specific is injected (the secure-storage anchor, the OS-permission provider, the real mailbox adapter, the MLX runtime, the Keychain-backed keys), so
this file is verified on Linux with the deterministic fakes and the Mac pieces plug into the same seams.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .access import OSPermissionProvider, SourceAccess
from .api import CoreApi
from .designation import DesignationStore, RollbackAnchor
from .documents import DocumentIndex
from .events import SafeLog
from .evidence import StoredSource
from .identity import ClientRegistry
from .intelligence import Gateway, ModelRuntime, Router, Signals
from .mail import Mailbox, MailIndex
from .models import Manifest, ModelStore
from .policy import PolicyEngine
from .service import Deps, TaskService
from .tasks import TaskStore
from .transport import UnixServer, serve_unix

INDEX_SLICE = 20
RESCAN_SECONDS = 300  # how often a permitted source is listed again to notice changes


@dataclass
class CoreConfig:
    """Everything that varies by machine. Keys are separate per store (a database key is never shared)."""

    data_dir: Path
    socket_path: Path
    task_key: str
    designation_key: str
    documents_key: str
    mail_key: str
    anchor: RollbackAnchor
    os_permissions: OSPermissionProvider
    clients: ClientRegistry
    manifest: Manifest
    model_record_key: bytes
    runtime: ModelRuntime
    documents: tuple[str, Path] | None = None  # (source type name from the policy rules, folder)
    mailbox: tuple[str, Mailbox] | None = None  # (source type name, adapter)
    owner_mode: Callable[[], str] = lambda: "default"  # the owner's selected mode ("default" or "research"); never inferred from a question
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    allowed_uids: Iterable[int] | None = None
    log: SafeLog = field(default_factory=SafeLog)


class _Retriever:
    def __init__(self, indexes: dict[str, Any]) -> None:
        self._indexes = indexes

    def search(self, source_type: str, query: str) -> Iterable[dict[str, Any]]:
        index = self._indexes.get(source_type)
        return [] if index is None else index.search(source_type, query)


class _Sources:
    """The evidence store: a source id belongs to exactly one index, and an index resolves only its own."""

    def __init__(self, indexes: dict[str, Any]) -> None:
        self._indexes = indexes

    def get(self, source_id: str) -> StoredSource | None:
        for index in self._indexes.values():
            found = index.get(source_id)
            if found is not None:
                return found
        return None


class Core:
    def __init__(self, config: CoreConfig) -> None:
        c = config
        c.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.config, self.clock = c, c.clock
        self.designation = DesignationStore(c.data_dir / "designation.db", c.designation_key, c.clock, anchor=c.anchor)
        self.designation.verify()
        self.access = SourceAccess(self.designation, c.os_permissions, c.clock)
        self.indexes: dict[str, Any] = {}
        if c.documents is not None:
            name, root = c.documents
            self.indexes[name] = DocumentIndex(c.data_dir / "documents.db", c.documents_key, root, name, access=self.access)
        if c.mailbox is not None:
            name, adapter = c.mailbox
            self.indexes[name] = MailIndex(c.data_dir / "mail.db", c.mail_key, adapter, name, access=self.access)
        self.tasks = TaskStore(c.data_dir / "tasks.db", c.task_key)
        models = ModelStore(c.data_dir / "models", c.manifest, c.model_record_key)
        self.gateway = Gateway(models, Router(c.manifest.entries()), c.runtime, signals=lambda: Signals(mode=c.owner_mode()))
        self.service = TaskService(
            Deps(
                self.tasks,
                PolicyEngine(self.access),
                _Retriever(self.indexes),
                self.gateway,
                _Sources(self.indexes),
                c.log,
                clock=c.clock,
                coverage={t: index.coverage for t, index in self.indexes.items()},
            )
        )
        for source_type, index in self.indexes.items():  # a revocation removes the index AND what tasks derived from it
            self.designation.register_purge(source_type, self._purger(source_type, index))
        self.api = CoreApi(self.service, c.clients, c.log, c.clock)
        self.server: UnixServer | None = None
        self._scanned: dict[str, datetime] = {}
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def _purger(self, source_type: str, index: Any) -> Callable[[], None]:
        def purge() -> None:
            self._scanned.pop(source_type, None)  # a new grant starts from an empty index and a fresh scan at once
            index.purge()
            self.service.purge_source_type(source_type)

        return purge

    # -- running -------------------------------------------------------------------------------------------------------------------------------
    def start(self) -> str:
        """Finish owed purges, recover interrupted tasks, bind the socket and start the worker. Returns the socket path."""
        self.designation.run_pending_purges()
        self.service.recover()
        self.server = serve_unix(self.config.socket_path, self.api, self.config.allowed_uids)
        for target in (self.server.serve_forever, self._work):
            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            self._threads.append(thread)
        return str(self.config.socket_path)

    def tick(self) -> None:
        """One round of background work: expire what is overdue, run a queued task, and take one bounded slice of each index that is currently permitted."""
        self.service.expire_due()
        for task_id in self.tasks.ids_in(("queued",)):
            self.service.run(task_id)
        for source_type, index in self.indexes.items():
            if not self.access.permitted(source_type):  # nothing is scanned or read without a current grant and platform permission
                self._scanned.pop(source_type, None)
                continue
            now = self.clock()
            last = self._scanned.get(source_type)
            if last is None or (now - last).total_seconds() >= RESCAN_SECONDS:
                index.scan()
                self._scanned[source_type] = now
            index.run(INDEX_SLICE)

    def _work(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:  # noqa: BLE001  (the worker never dies; a failing round is simply tried again)
                self.config.log.emit("api.request", "service", "worker-loop", error_code="internal_error")
            self._stop.wait(0.05)

    def close(self) -> None:
        self._stop.set()
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
        for thread in self._threads:
            thread.join(5)
        for index in self.indexes.values():
            index.close()
        self.tasks.close()
        self.designation.close()
