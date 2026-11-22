"""The composition root: the one place that builds a running Core from its parts and connects them (WP3 hardening).

It adds no behaviour of its own. It wires what the other modules already guarantee: the owner's designation gates every index and the policy; a revocation purges the index AND
everything the task store derived from it; the model is reached only through the gateway behind the policy gate; coverage comes from the indexes; the API is served on the owner-only
socket. Everything platform-specific is injected (the secure-storage anchor, the OS-permission provider, the real mailbox adapter, the MLX runtime, the Keychain-backed keys), so
this file is verified on Linux with the deterministic fakes and the Mac pieces plug into the same seams.
"""

from __future__ import annotations

import fcntl
import os
import threading
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .access import OSPermissionProvider, SourceAccess
from .actions import ActionGateway
from .api import CoreApi
from .consent import ConsentService
from .designation import DesignationStore, RollbackAnchor
from .documents import DocumentIndex
from .egress import EgressGateway
from .events import SafeLog
from .evidence import StoredSource
from .identity import BootstrapGate, ClientRegistry
from .intelligence import Gateway, ModelRuntime, Router, Signals
from .mail import Mailbox, MailIndex
from .models import Manifest, ModelStore
from .operations import Operations
from .policy import PolicyEngine
from .record_actions import register_record_actions
from .recordstore import RecordStore, StoreError
from .service import Deps, ResearchGate, TaskService
from .sync import SyncService
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
    manifest: Manifest
    model_record_key: bytes
    runtime: ModelRuntime
    bootstrap_code: str | None = (
        None  # the single-use first-run code, known only to the process that starts the Core; required while no owner client is enrolled
    )
    open_bootstrap: bool = False  # DEVELOPMENT ONLY: accept the first owner with no code (what the first version did); never set it in a real run
    clients: ClientRegistry | None = None  # None: a durable registry in the data folder (the normal case); tests inject one
    documents: tuple[str, Path] | None = None  # (source type name from the policy rules, folder)
    mailbox: tuple[str, Mailbox] | None = None  # (source type name, adapter)
    records: Mapping[str, tuple[Mailbox, str]] = field(
        default_factory=dict
    )  # Stage 5 domains: source type -> (read-only record source, that store's own key); one encrypted index per type
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    allowed_uids: Iterable[int] | None = None
    egress: EgressGateway | None = None  # public-web research; None (the default) means the Core makes no outbound request at all
    edits_key: str | None = None  # the key of the owner's own edits store (Calendar, Contacts, Notes); None means the Core has no owner actions and no sync
    outbox: Callable[[dict[str, Any]], dict[str, Any]] | None = (
        None  # the platform sender for `calendar.send_invitation` (a real adapter is not built; None means the action does not exist)
    )
    erase: Callable[[str], None] | None = None  # the platform's irreversible removal behind the approval-gated `*.erase` actions (None: they do not exist)
    live_network: bool = False  # the explicit live-network gate: even with a gateway configured, no public search is made unless this is True (off by default)
    log: SafeLog = field(default_factory=SafeLog)


class CoreAlreadyRunning(RuntimeError):
    """Another Core already owns this data folder (its stores, its socket). The second one must not start, bind, or unlink anything."""


def _lock_data_dir(data_dir: Path) -> int:
    fd = os.open(data_dir / "core.lock", os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # released by the OS if the holder dies, so a crash never leaves a stale lock
    except OSError:
        os.close(fd)
        raise CoreAlreadyRunning("another Core owns this data folder") from None
    return fd


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


class _Mode:
    """The owner's selected model mode, in memory only: it starts as `default` every time the Core starts (the deep tier is never on by accident)."""

    def __init__(self) -> None:
        self._mode, self._lock = "default", threading.Lock()

    def get(self) -> str:
        with self._lock:
            return self._mode

    def set(self, mode: str) -> None:
        with self._lock:
            self._mode = mode


class Core:
    def __init__(self, config: CoreConfig) -> None:
        c = config
        c.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._lock_fd = _lock_data_dir(c.data_dir)  # one Core per data folder: taken before any store is opened, held until close() or the process ends
        try:
            self._build(c)
        except BaseException:
            self._release_lock()
            raise

    def _build_indexes(self, c: CoreConfig) -> dict[str, Any]:
        """One encrypted, guarded index per configured source type: documents, Mail, and the Stage 5 domains (the same exact, purgeable index as Mail, one store and one key per type)."""
        indexes: dict[str, Any] = {}
        if c.documents is not None:
            name, root = c.documents
            indexes[name] = DocumentIndex(c.data_dir / "documents.db", c.documents_key, root, name, access=self.access)
        if c.mailbox is not None:
            name, adapter = c.mailbox
            indexes[name] = MailIndex(c.data_dir / "mail.db", c.mail_key, adapter, name, access=self.access)
        for name, (source, key) in c.records.items():
            indexes[name] = MailIndex(c.data_dir / f"{name}.db", key, source, name, access=self.access)
        return indexes

    def _build(self, c: CoreConfig) -> None:
        self.mode = _Mode()
        self.egress = c.egress
        self.config, self.clock = c, c.clock
        self.designation = DesignationStore(c.data_dir / "designation.db", c.designation_key, c.clock, anchor=c.anchor)
        self.designation.verify()
        self.access = SourceAccess(self.designation, c.os_permissions, c.clock)
        self.indexes = self._build_indexes(c)
        self.designation.allow_adapter_types(c.records)
        self.tasks = TaskStore(c.data_dir / "tasks.db", c.task_key)
        models = ModelStore(c.data_dir / "models", c.manifest, c.model_record_key)
        self.gateway = Gateway(models, Router(c.manifest.entries()), c.runtime, signals=lambda: Signals(mode=self.mode.get()), log=c.log)
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
                research=ResearchGate(c.egress, c.live_network),
            )
        )
        for source_type, index in self.indexes.items():  # a revocation removes the index AND what tasks derived from it
            self.designation.register_purge(source_type, self._purger(source_type, index))
        self.consent = ConsentService(self.designation, self.access, self.indexes)
        self.clients = c.clients or ClientRegistry(path=c.data_dir / "clients.json")
        self.operations = self._build_operations(c)
        gate = None
        if not self.clients.has_owner():
            if c.bootstrap_code is None and not c.open_bootstrap:
                raise ValueError("no owner client is enrolled: start the Core with a one-time bootstrap code")  # fail closed
            gate = BootstrapGate(c.bootstrap_code) if c.bootstrap_code is not None else None
        self.api = CoreApi(self.service, self.clients, c.log, c.clock, consent=self.consent, bootstrap=gate, mode=self.mode, ops=self.operations)
        self.server: UnixServer | None = None
        self._scanned: dict[str, datetime] = {}
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def _build_operations(self, c: CoreConfig) -> Operations | None:
        """The owner's own edits store, the Action Gateway over it and the sync service: present only when the Core was given a key for the store."""
        self.edits: RecordStore | None = None
        if c.edits_key is None:
            return None
        self.edits = RecordStore(c.data_dir / "edits.db", c.edits_key, frozenset({"calendar", "contacts", "notes"}), c.clock)
        gateway = ActionGateway(c.clock)
        register_record_actions(gateway, self.edits, c.outbox, c.erase)
        edits = self.edits

        def version_of(record_id: str) -> int | None:
            try:
                return edits.get(record_id, include_deleted=True).version
            except StoreError:
                return None

        return Operations(gateway, SyncService(gateway, self.clients, version_of))

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

    def _release_lock(self) -> None:
        fd, self._lock_fd = self._lock_fd, -1
        if fd >= 0:
            os.close(fd)

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
        if self.edits is not None:
            self.edits.close()
        self.designation.close()
        self._release_lock()
